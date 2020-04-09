
from nmigen import *
from nmigen.lib.fifo import SyncFIFO
from nmigen.lib.stream import *

import enum
import ipaddress
import math

from scapy.all import *
            
class IPProtocolNumber(enum.Enum):
    TCP = 0x06
    UDP = 0x11
    SCTP = 0x84
    UDPLite = 0x88
    NA = 0xFD

# TODO some of these might want to be configurable
IP_VERSION = C(4, 4)
IHL = C(5, 4)
DSCP = C(0, 6)
ECN = C(0, 2)
ID = C(0, 16)
FLAGS = C(0b010, 3)
FO = C(0, 13)
TTL = C(255, 8)

class IPv4Packetizer(Elaboratable):
    """
    TODO formal docstring
    Input: stream with framing
    Output: stream with framing
    Parameter: MTU (FIFO depth), proto (protocol number), source IP, dest IP
    Control signals: Overflow error
    """
    def __init__(self, input: StreamSource, source_ip: ipaddress.IPv4Address, dest_ip: ipaddress.IPv4Address, 
            mtu: int = 1500, in_flight: int = 2, proto: IPProtocolNumber = IPProtocolNumber.NA):
        assert mtu >= 68
        assert mtu < 65535
        
        assert Record(input.payload_type).shape().width == 8
        assert input.sop_enabled
        assert input.eop_enabled

        self._input = input
        self.sink = StreamSink.from_source(input)
        self.source = StreamSource(Layout([("data", 8, DIR_FANOUT)]), sop=True, eop=True)
        
        self._mtu = mtu
        self._in_flight = in_flight
        self._proto = C(proto.value, 8)
        self._source_ip = C(int.from_bytes(source_ip.packed, byteorder='big'), 32)
        self._dest_ip = C(int.from_bytes(dest_ip.packed, byteorder='big'), 32)
        
        self._partial_checksum = self._calc_partial_checksum()
        
        self.overflow  = Signal()
        self.err  = Signal()
        
    def _calc_partial_checksum(self):
        full_sum = Cat(ECN, DSCP, IHL, IP_VERSION) + \
            ID + \
            Cat(FO, FLAGS) +  \
            Cat(self._proto, TTL) +  \
            self._source_ip[16:] +  \
            self._source_ip[:16] + \
            self._dest_ip[16:] + \
            self._dest_ip[:16]
        
        full_sum = full_sum[:16] + full_sum[16:]
        return (full_sum[:16] + full_sum[16:])[:16]
            

    def elaborate(self, platform):
        sink = self.sink
        source = self.source
        
        m = Module()
        
        m.d.comb += self.sink.connect(self._input)
        
        counter = Signal(16)
        
        # TODO this should be a FIFO stream, why am I reimplementing it here?
        m.submodules.fifo = fifo = SyncFIFO(width=8, depth=self._mtu)
        m.submodules.counter_fifo = counter_fifo = SyncFIFO(width=16, depth=self._in_flight)
        self.counter_fifo = counter_fifo
        
        stall = Signal()
        m.d.comb += sink.ready.eq(fifo.w_rdy & ~stall)
        
        output_active = Signal()
        m.d.comb += source.valid.eq(counter_fifo.r_rdy | output_active)
        
        we = Signal()
        m.d.comb += we.eq(sink.valid & sink.ready)
        re = Signal()
        m.d.comb += re.eq(source.valid & source.ready)
        
        # clear error signals every clock
        m.d.sync += self.overflow.eq(0)
        m.d.sync += self.err.eq(0)
                    
        # data plugs directly into FIFO
        m.d.comb += fifo.w_data.eq(sink.data)
        
        with m.If(we):
            # input FSM
            # each state needs to handle four cases: 0, SOP, EOP, SOP&EOP.
            with m.FSM() as fsm:
                with m.State("IDLE"):
                    # between packets
                    with m.If(sink.sop & sink.eop):
                        # store input data
                        m.d.comb += fifo.w_en.eq(1)
                        
                        with m.If(counter_fifo.w_rdy):
                            # write counter of 1 to counter fifo if space exists
                            m.d.comb += counter_fifo.w_data.eq(1)
                            m.d.comb += counter_fifo.w_en.eq(1)
                        with m.Else():
                            # otherwise, stall until space is available
                            m.next = "STALL"
                            m.d.sync += counter.eq(1)
                            m.d.sync += stall.eq(0)
                            
                    with m.If(sink.sop & ~sink.eop):
                        # store input data
                        m.d.comb += fifo.w_en.eq(1)
                        
                        # start counter
                        m.d.sync += counter.eq(1)
                        
                        # advance to packet state
                        m.next = "PKT"
                        
                    with m.If(~sink.sop): # action independent of eop state
                        # write between packets but not SOP - illegal
                        m.d.sync += self.err.eq(1)
                        
                with m.State("PKT"):
                    # processing a packet
                    with m.If(sink.sop): # action independent of eop state
                        # new SOP without corresponding EOP - illegal
                        m.d.sync += self.err.eq(1)
                        # return to idle state
                        m.next = "IDLE"
                        
                    with m.If(~sink.sop & sink.eop):
                        with m.If(counter >= self._mtu):
                            # this state should not be accessible but is included for safety/completeness
                            # signal overflow
                            m.d.sync += self.overflow.eq(1)
                            # return to idle state
                            m.next = "IDLE"
                            
                        with m.Else():
                            # store input data
                            m.d.comb += fifo.w_en.eq(1)
                            
                            with m.If(counter_fifo.w_rdy):
                                # write counter value to counter fifo if space exists
                                m.d.comb += counter_fifo.w_data.eq(counter + 1)
                                m.d.comb += counter_fifo.w_en.eq(1)
                                
                                # reset input counter
                                m.d.sync += counter.eq(0)
                            
                                # return to idle state
                                m.next = "IDLE"
                                
                            with m.Else():
                                # otherwise, stall until space is available
                                m.next = "STALL"
                                m.d.sync += counter.eq(counter + 1)
                                m.d.sync += stall.eq(0)
                            
                    with m.If(~sink.sop & ~sink.eop):
                        with m.If(counter >= self._mtu):
                            # signal overflow
                            m.d.sync += self.overflow.eq(1)
                            # return to idle state
                            m.next = "IDLE"
                        with m.Else():
                            # store input data
                            m.d.comb += fifo.w_en.eq(1)
                            # advance counter
                            m.d.sync += counter.eq(counter + 1)
                with m.State("STALL"):
                    pass # TODO this doesn't actually work oops, needs to be outside the FSM
            
        header_idx = Signal(range(4), reset=0)
        pkt_len = Signal(16)
        checksum = Signal(16)

        # output FSM
        with m.FSM() as fsm:
            with m.State("INIT"):
                # send first header byte
                m.d.comb += source.data.eq(Cat(IHL, IP_VERSION))
                
                with m.If(re):
                    # set SOP
                    m.d.comb += self.source.sop.eq(1)
                    
                    # mark output active
                    m.d.sync += output_active.eq(1)
                    
                    # latch out counter value
                    m.d.comb += counter_fifo.r_en.eq(1)
                    m.d.sync += pkt_len.eq(counter_fifo.r_data)
                    
                    # calculate full checksum from counter value
                    checksum_intermediate = self._partial_checksum + counter_fifo.r_data
                    checksum_intermediate = checksum_intermediate[:16] + checksum_intermediate[16:]
                    checksum_intermediate = checksum_intermediate[:16] + checksum_intermediate[16:]
                    m.d.sync += checksum.eq(checksum_intermediate[:16])
                    
                    # advance state
                    m.next = "HEADER_BYTE1"
                
            with m.State("HEADER_BYTE1"):
                # send second header byte
                m.d.comb += source.data.eq(Cat(ECN, DSCP))
                
                with m.If(re):
                    # set index for Length
                    m.d.sync += header_idx.eq(1)
                    # advance state
                    m.next = "LENGTH"
                
            with m.State("LENGTH"):
                # send current length byte
                m.d.comb += source.data.eq(pkt_len.word_select(header_idx, 8))
                
                with m.If(re):
                    # decrement index
                    m.d.sync += header_idx.eq(header_idx - 1)
                    with m.If(header_idx == 0):
                        # set index for ID
                        m.d.sync += header_idx.eq(1)
                    
                        # advance state
                        m.next = "ID"
                
            with m.State("ID"):
                # send current id byte
                m.d.comb += source.data.eq(ID.word_select(header_idx, 8))
                
                with m.If(re):
                    # decrement index
                    m.d.sync += header_idx.eq(header_idx - 1)
                    with m.If(header_idx == 0):
                        # advance state
                        m.next = "FLAGS"

            with m.State("FLAGS"):
                # send flags
                m.d.comb += source.data.eq(Cat(FO[8:], FLAGS))
                
                with m.If(re):
                    # advance state
                    m.next = "FO"
                
            with m.State("FO"):
                # send fragment offset low bits
                m.d.comb += source.data.eq(FO[:8])
                
                with m.If(re):
                    # advance state
                    m.next = "TTL"
                
            with m.State("TTL"):
                # send time-to-live
                m.d.comb += source.data.eq(TTL)
                
                with m.If(re):
                    # advance state
                    m.next = "PROTOCOL"
                
            with m.State("PROTOCOL"):
                # send protocol number
                m.d.comb += source.data.eq(self._proto)
                
                with m.If(re):
                    # set index for checksum
                    m.d.sync += header_idx.eq(1)
                    
                    # advance state
                    m.next = "CHECKSUM"
                
            with m.State("CHECKSUM"):
                # send current checksum byte
                m.d.comb += source.data.eq(~checksum.word_select(header_idx, 8))
                
                with m.If(re):
                    # decrement index
                    m.d.sync += header_idx.eq(header_idx - 1)
                    with m.If(header_idx == 0):
                        # set index for source address
                        m.d.sync += header_idx.eq(3)
                    
                        # advance state
                        m.next = "ADDR_SOURCE"
                
            with m.State("ADDR_SOURCE"):
                # send current source address byte
                m.d.comb += source.data.eq(self._source_ip.word_select(header_idx, 8))
                
                with m.If(re):
                    # decrement index
                    m.d.sync += header_idx.eq(header_idx - 1)
                    with m.If(header_idx == 0):
                        # set index for dest address
                        m.d.sync += header_idx.eq(3)
                    
                        # advance state
                        m.next = "ADDR_DEST"
                        
            with m.State("ADDR_DEST"):
                # send current destination address byte
                m.d.comb += source.data.eq(self._dest_ip.word_select(header_idx, 8))
                
                with m.If(re):
                    # decrement index
                    m.d.sync += header_idx.eq(header_idx - 1)
                    with m.If(header_idx == 0):
                        # advance state
                        m.next = "PAYLOAD"
            
            with m.State("PAYLOAD"):
                # send current payload byte
                m.d.comb += source.data.eq(fifo.r_data)
                
                with m.If(re):
                    # advance FIFO
                    m.d.comb += fifo.r_en.eq(1)
                    
                    # decrement length
                    m.d.sync += pkt_len.eq(pkt_len - 1)
                    
                    with m.If(pkt_len - 1 == 0):
                        # set EOP
                        m.d.comb += self.source.eop.eq(1)
                        # mark output inactive
                        m.d.sync += output_active.eq(0)
                        # packet complete
                        m.next = "INIT"
                    
        return m

if __name__ == "__main__":
    input = i = StreamSource(Layout([("data", 8, DIR_FANOUT)]))
    packetizer = p = IPv4Packetizer(input, ipaddress.IPv4Address("127.0.0.1"), ipaddress.IPv4Address("127.0.0.2"))
    
    ports = []

    import argparse

    parser = argparse.ArgumentParser()
    p_action = parser.add_subparsers(dest="action")
    p_action.add_parser("simulate")
    p_action.add_parser("generate")

    args = parser.parse_args()
    if args.action == "simulate":
        from nmigen.back.pysim import Simulator, Passive

        sim = Simulator(packetizer)
        sim.add_clock(1e-6)
        
        def transmit_proc():
            yield
            for c in "hello world":
                if c == "h":
                    yield i.sop.eq(1)
                elif c == "d":
                    yield i.eop.eq(1)
                else:
                    yield i.sop.eq(0)
                    yield i.eop.eq(0)
                yield i.data.eq(ord(c))
                yield i.valid.eq(1)
                yield
            for g in range(0, 16):
                yield i.eop.eq(0)
                yield i.valid.eq(0)
                yield
        
        def receive_proc():
            for g in range(0, 16):
                yield
            data = []
            #for g in range(0, 128):
            yield p.source.ready.eq(1)
            yield
            while not (yield p.source.valid) == 0:
                if (yield p.source.valid) == 1:
                    data.append((yield p.source.data))
                yield
            
            r = IP(data)
            assert r.load == b"hello world"
            
            i = IP(data)
            del i.chksum
            i = IP(raw(i))
            assert r.chksum == i.chksum

        sim.add_sync_process(transmit_proc)
        sim.add_sync_process(receive_proc)
        
        with sim.write_vcd("ipv4.vcd", "ipv4.gtkw"):
            sim.run()

    if args.action == "generate":
        from nmigen.back import verilog

        print(verilog.convert(packetizer, ports=ports))
        
    if args.action == "program":
        platform = VersaECP5Platform()
        platform.build(packetizer, do_program=True)
    

