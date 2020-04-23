
from nmigen import *
from nmigen.lib.fifo import SyncFIFO
from .stream import *

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

class UDPDepacketizer(Elaboratable):
    """
    TODO formal docstring
    Input: stream with framing
    Output: stream with framing
    Parameter: IP, port
    """
    def __init__(self, input: StreamSource, ip: ipaddress.IPv4Address, port: int, mtu: int = 1500, in_flight: int = 2):
        assert port <= 65535

        assert Record(input.payload_type).shape().width == 8
        # these come from the SLIP decoder
        assert input.sop_enabled
        assert input.eop_enabled
        self._input = input

        self.sink = StreamSink.from_source(input)
        self.source = StreamSource(Layout([("data", 8, DIR_FANOUT)]), sop=True, eop=True)
        
        self._ip = C(int.from_bytes(ip.packed, byteorder='big'), 32)
        self._port = C(port, 16)
        self._mtu = mtu
        self._in_flight = in_flight
        
    def elaborate(self, platform):
        sink = self.sink
        source = self.source
        
        m = Module()
        
        m.submodules.fifo = fifo = SyncFIFO(width=8, depth=self._mtu)
        m.submodules.counter_fifo = counter_fifo = SyncFIFO(width=16, depth=self._in_flight, fwft = True)
        
        counter = Signal(16)
        input_counter = Signal(16)
        
        we = Signal()
        m.d.comb += we.eq(sink.valid & sink.ready)
        
        m.d.comb += fifo.w_data.eq(sink.data)
        m.d.comb += fifo.w_en.eq(0)
        m.d.comb += counter_fifo.w_data.eq(input_counter)
        m.d.comb += counter_fifo.w_en.eq(0)
        
        input_active = Signal()
        
        m.d.comb += self.sink.connect(self._input)
        m.d.comb += sink.ready.eq((fifo.level == 0) | input_active)
        
        # input FSM
        with m.FSM(name='input_fsm') as fsm:
            with m.State("IDLE"):
                with m.If(we):
                    with m.If(self._input.sop):
                        m.d.sync += input_active.eq(1)
                        with m.If(sink.data == Cat(IHL, IP_VERSION)):
                            # possible legal IPv4 packet, advance
                            m.next = "HEADER_BYTE1"
            with m.State("HEADER_BYTE1"):
                with m.If(we):
                    with m.If(sink.data == Cat(ECN, DSCP)):
                        m.next = "HEADER_BYTE2"
                    with m.Else():
                        # error - return to IDLE
                        m.d.sync += input_active.eq(0)
                        m.next = "IDLE"
            with m.State("HEADER_BYTE2"):
                with m.If(we):
                    m.d.sync += counter[8:].eq(sink.data)
                    m.next = "HEADER_BYTE3"
            with m.State("HEADER_BYTE3"):
                with m.If(we):
                    m.d.sync += counter[:8].eq(sink.data)
                    m.next = "HEADER_BYTE4"
            with m.State("HEADER_BYTE4"):
                with m.If(we):
                    with m.If(sink.data == ID[8:]):
                        m.next = "HEADER_BYTE5"
                    with m.Else():
                        m.d.sync += input_active.eq(0)
                        m.next = "IDLE"
            with m.State("HEADER_BYTE5"):
                with m.If(we):
                    with m.If(sink.data == ID[:8]):
                        m.next = "HEADER_BYTE6"
                    with m.Else():
                        m.d.sync += input_active.eq(0)
                        m.next = "IDLE"
            with m.State("HEADER_BYTE6"):
                with m.If(we):
                    with m.If(sink.data == Cat(FO[8:], FLAGS)):
                        m.next = "HEADER_BYTE7"
                    with m.Else():
                        m.d.sync += input_active.eq(0)
                        m.next = "IDLE"
            with m.State("HEADER_BYTE7"):
                with m.If(we):
                    with m.If(sink.data == FO[:8]):
                        m.next = "HEADER_BYTE8"
                    with m.Else():
                        m.d.sync += input_active.eq(0)
                        m.next = "IDLE"
            with m.State("HEADER_BYTE8"):
                with m.If(we):
                    # TTL is ignored
                    m.next = "HEADER_BYTE9"
            with m.State("HEADER_BYTE9"):
                with m.If(we):
                    with m.If(sink.data == IPProtocolNumber.UDP.value):
                        m.next = "HEADER_BYTE10"
                    with m.Else():
                        m.d.sync += input_active.eq(0)
                        m.next = "IDLE"
            with m.State("HEADER_BYTE10"):
                with m.If(we):
                    # TODO validate checksum
                    m.next = "HEADER_BYTE11"
            with m.State("HEADER_BYTE11"):
                with m.If(we):
                    # TODO validate checksum
                    m.next = "HEADER_BYTE12"
            with m.State("HEADER_BYTE12"):
                with m.If(we):
                    # source IP is ignored
                    m.next = "HEADER_BYTE13"
            with m.State("HEADER_BYTE13"):
                with m.If(we):
                    # source IP is ignored
                    m.next = "HEADER_BYTE14"
            with m.State("HEADER_BYTE14"):
                with m.If(we):
                    # source IP is ignored
                    m.next = "HEADER_BYTE15"
            with m.State("HEADER_BYTE15"):
                with m.If(we):
                    # source IP is ignored
                    m.next = "HEADER_BYTE16"
            with m.State("HEADER_BYTE16"):
                with m.If(we):
                    with m.If(sink.data == self._ip[24:]):
                        m.next = "HEADER_BYTE17"
                    with m.Else():
                        m.d.sync += input_active.eq(0)
                        m.next = "IDLE"
            with m.State("HEADER_BYTE17"):
                with m.If(we):
                    with m.If(sink.data == self._ip[16:24]):
                        m.next = "HEADER_BYTE18"
                    with m.Else():
                        m.d.sync += input_active.eq(0)
                        m.next = "IDLE"
            with m.State("HEADER_BYTE18"):
                with m.If(we):
                    with m.If(sink.data == self._ip[8:16]):
                        m.next = "HEADER_BYTE19"
                    with m.Else():
                        m.d.sync += input_active.eq(0)
                        m.next = "IDLE"
            with m.State("HEADER_BYTE19"):
                with m.If(we):
                    with m.If(sink.data == self._ip[:8]):
                        # assume no options
                        m.next = "UDP_HEADER_BYTE0"
                    with m.Else():
                        m.d.sync += input_active.eq(0)
                        m.next = "IDLE"
            with m.State("UDP_HEADER_BYTE0"):
                with m.If(we):
                    # source port is ignored
                    m.next = "UDP_HEADER_BYTE1"
            with m.State("UDP_HEADER_BYTE1"):
                with m.If(we):
                    # source port is ignored
                    m.next = "UDP_HEADER_BYTE2"
            with m.State("UDP_HEADER_BYTE2"):
                with m.If(we):
                    with m.If(sink.data == self._port[8:]):
                        m.next = "UDP_HEADER_BYTE3"
                    with m.Else():
                        m.d.sync += input_active.eq(0)
                        m.next = "IDLE"
            with m.State("UDP_HEADER_BYTE3"):
                with m.If(we):
                    with m.If(sink.data == self._port[:8]):
                        m.next = "UDP_HEADER_BYTE4"
                    with m.Else():
                        m.d.sync += input_active.eq(0)
                        m.next = "IDLE"
            with m.State("UDP_HEADER_BYTE4"):
                with m.If(we):
                    with m.If(sink.data == counter[8:]):
                        m.next = "UDP_HEADER_BYTE5"
                    with m.Else():
                        # length mismatch between IP and UDP headers - fragmented?
                        m.d.sync += input_active.eq(0)
                        m.next = "IDLE"
            with m.State("UDP_HEADER_BYTE5"):
                with m.If(we):
                    with m.If(sink.data == counter[:8]):
                        m.next = "UDP_HEADER_BYTE6"
                    with m.Else():
                        m.d.sync += input_active.eq(0)
                        m.next = "IDLE"
            with m.State("UDP_HEADER_BYTE6"):
                with m.If(we):
                    # TODO validate checksum
                    m.next = "UDP_HEADER_BYTE7"
            with m.State("UDP_HEADER_BYTE7"):
                with m.If(we):
                    # TODO validate checksum
                    m.d.sync += input_counter.eq(counter - 8)
                    m.next = "PAYLOAD"
            with m.State("PAYLOAD"):
                with m.If(we):
                    # TODO handle a too-early EOP correctly (or at all)
                    m.d.sync += counter.eq(counter - 1)
                    m.d.comb += fifo.w_en.eq(1)
                    with m.If(counter == 9):
                        # latch counter and re-set
                        m.d.comb += counter_fifo.w_en.eq(1)
                        m.d.sync += input_active.eq(0)
                        m.next = "IDLE"
        
        re = Signal()
        m.d.comb += re.eq(source.valid & source.ready)
        
        m.d.comb += fifo.r_en.eq(0)
        m.d.comb += counter_fifo.r_en.eq(0)
        
        output_counter = Signal(16)
        
        m.d.comb += source.data.eq(fifo.r_data)
        m.d.comb += source.valid.eq(counter_fifo.r_rdy)
        m.d.comb += source.sop.eq(0)
        m.d.comb += source.sop.eq(1)
        
        # output FSM
        with m.FSM(name='output_fsm') as fsm:
            with m.State("IDLE"):
                with m.If(re):
                    m.d.comb += source.sop.eq(1)
                    m.d.sync += output_counter.eq(counter_fifo.r_data - 1)
                    m.d.comb += fifo.r_en.eq(1)
                    m.next = "PAYLOAD"
            with m.State("PAYLOAD"):
                with m.If(re):
                    m.d.sync += output_counter.eq(output_counter - 1)
                    m.d.comb += fifo.r_en.eq(1)
                    with m.If(output_counter == 1):
                        m.d.comb += source.eop.eq(1)
                        m.d.comb += counter_fifo.r_en.eq(1)
                        m.next = "IDLE"
                
        return m
    

class UDPPacketizer(Elaboratable):
    """
    TODO formal docstring
    Input: stream with framing
    Output: stream with framing
    Parameter: MTU (FIFO depth), # in flight at once, source IP, dest IP, source port, dest port
    """
    def __init__(self, input: StreamSource, source_ip: ipaddress.IPv4Address, dest_ip: ipaddress.IPv4Address, 
            source_port: int, dest_port: int, mtu: int = 1500, in_flight: int = 2):
        assert mtu >= 68
        assert mtu < 65535
        assert source_port <= 65535
        assert dest_port <= 65535
        
        assert Record(input.payload_type).shape().width == 8
        assert input.sop_enabled
        assert input.eop_enabled

        self._mtu = mtu
        self._input = input
        self.sink = StreamSink.from_source(input)
        
        self.source = StreamSource(Layout([("data", 8, DIR_FANOUT)]), sop=True, eop=True)
        
        self._in_flight = in_flight
        self._proto = C(IPProtocolNumber.UDP.value, 8)
        self._source_ip = C(int.from_bytes(source_ip.packed, byteorder='big'), 32)
        self._dest_ip = C(int.from_bytes(dest_ip.packed, byteorder='big'), 32)
        self._source_port = C(source_port, 16)
        self._dest_port = C(dest_port, 16)
        
        
        
    def _partial_ip_checksum(self):
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
            
    def _partial_udp_checksum(self):
        full_sum = self._source_ip[16:] + \
            self._source_ip[:16] + \
            self._dest_ip[16:] + \
            self._dest_ip[:16] + \
            Cat(C(0, 8), self._proto) + \
            self._source_port + \
            self._dest_port
        
        full_sum = full_sum[:16] + full_sum[16:]
        return (full_sum[:16] + full_sum[16:])[:16]
            

    def elaborate(self, platform):
        sink = self.sink
        source = self.source
        
        m = Module()
        # TODO figure out a _useful_ stream abstraction that can handle this use case
        m.submodules.fifo = fifo = SyncFIFO(width=8, depth=self._mtu)
        
        # input side
        m.d.comb += self.sink.connect(self._input)
        
        counter = Signal(16)
        active = Signal()
        
        m.submodules.counter_fifo = counter_fifo = SyncFIFO(width=16, depth=self._in_flight, fwft = True)
        m.submodules.checksum_fifo = checksum_fifo = SyncFIFO(width=16, depth=self._in_flight, fwft = True)
        
        # gotta stall if _either_ FIFO is full, means sink can't be exactly fifo's sink
        m.d.comb += sink.ready.eq(fifo.w_rdy & counter_fifo.w_rdy)
        
        we = Signal()
        m.d.comb += we.eq(sink.valid & sink.ready)

        udp_checksum = Signal(16)
        
        m.d.comb += fifo.w_data.eq(self.sink.data)
        m.d.comb += fifo.w_en.eq(we)
        
        with m.If(we):
            with m.If(self._input.sop):
                m.d.sync += counter.eq(1)
                m.d.sync += udp_checksum.eq(self._partial_udp_checksum() + sink.data)
                m.d.sync += active.eq(1)
            
            with m.If(active):
                m.d.sync += udp_checksum.eq(udp_checksum + sink.data)
                m.d.sync += counter.eq(counter + 1)
            
            with m.If(self._input.eop):
                # write counter + 1 and checksum to FIFOs, become inactive
                m.d.comb += counter_fifo.w_data.eq(counter + 1)
                m.d.comb += counter_fifo.w_en.eq(1)
                m.d.comb += checksum_fifo.w_data.eq(udp_checksum + sink.data)
                m.d.comb += checksum_fifo.w_en.eq(1)
                m.d.sync += active.eq(0)
            with m.Else():
                m.d.comb += counter_fifo.w_en.eq(0)
                m.d.comb += checksum_fifo.w_en.eq(0)
        
        
        # output side
        output_active = Signal()
        m.d.comb += source.valid.eq(counter_fifo.r_rdy | output_active)
        
        re = Signal()
        m.d.comb += re.eq(source.valid & source.ready)
                    
        header_idx = Signal(range(4), reset=0)
        pkt_len = Signal(16)
        ip_checksum = Signal(16)
        udp_checksum_out = Signal(16)
        
        # normally don't advance these (ticked below in FSM)
        m.d.comb += fifo.r_en.eq(0)
        m.d.sync += counter_fifo.r_en.eq(0)
        m.d.sync += checksum_fifo.r_en.eq(0)
        
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
                    m.d.sync += counter_fifo.r_en.eq(1)
                    m.d.sync += pkt_len.eq(counter_fifo.r_data + 8)
                    
                    # advance checksum FIFO
                    m.d.sync += checksum_fifo.r_en.eq(1)
                    
                    # calculate full checksums from counter value
                    checksum_intermediate = self._partial_ip_checksum() + counter_fifo.r_data + 8
                    checksum_intermediate = checksum_intermediate[:16] + checksum_intermediate[16:]
                    checksum_intermediate = checksum_intermediate[:16] + checksum_intermediate[16:]
                    m.d.sync += ip_checksum.eq(checksum_intermediate[:16])
                    
                    checksum_intermediate = checksum_fifo.r_data + counter_fifo.r_data + 8
                    checksum_intermediate = checksum_intermediate[:16] + checksum_intermediate[16:]
                    checksum_intermediate = checksum_intermediate[:16] + checksum_intermediate[16:]
                    m.d.sync += udp_checksum_out.eq(checksum_intermediate[:16])
                    
                    # advance state
                    m.next = "IP_HEADER_BYTE2"
                
            with m.State("IP_HEADER_BYTE2"):
                # send second header byte
                m.d.comb += source.data.eq(Cat(ECN, DSCP))
                
                with m.If(re):
                    # set index for Length
                    m.d.sync += header_idx.eq(1)
                    # advance state
                    m.next = "IP_LENGTH"
                
            with m.State("IP_LENGTH"):
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
                    m.next = "IP_CHECKSUM"
                
            with m.State("IP_CHECKSUM"):
                # send current checksum byte
                m.d.comb += source.data.eq(~ip_checksum.word_select(header_idx, 8))
                
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
                        # set index for source port
                        m.d.sync += header_idx.eq(1)
                        
                        # advance state
                        m.next = "PORT_SOURCE"
            
            with m.State("PORT_SOURCE"):
                # send current source port byte
                m.d.comb += source.data.eq(self._source_port.word_select(header_idx, 8))
                
                with m.If(re):
                    # decrement index
                    m.d.sync += header_idx.eq(header_idx - 1)
                    with m.If(header_idx == 0):
                        # set index for dest port
                        m.d.sync += header_idx.eq(1)
                        
                        # advance state
                        m.next = "PORT_DEST"
            
            with m.State("PORT_DEST"):
                # send current dest port byte
                m.d.comb += source.data.eq(self._dest_port.word_select(header_idx, 8))
                
                with m.If(re):
                    # decrement index
                    m.d.sync += header_idx.eq(header_idx - 1)
                    with m.If(header_idx == 0):
                        # set index for UDP length
                        m.d.sync += header_idx.eq(1)
                        
                        # advance state
                        m.next = "UDP_LENGTH"
            
            with m.State("UDP_LENGTH"):
                # send current length byte
                m.d.comb += source.data.eq(pkt_len.word_select(header_idx, 8))
                
                with m.If(re):
                    # decrement index
                    m.d.sync += header_idx.eq(header_idx - 1)
                    with m.If(header_idx == 0):
                        # set index for UDP checksum
                        m.d.sync += header_idx.eq(1)
                    
                        # advance state
                        m.next = "UDP_CHECKSUM"
                        
            with m.State("UDP_CHECKSUM"):
                # send current checksum byte
                m.d.comb += source.data.eq(~udp_checksum.word_select(header_idx, 8))
                
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
                    
                    with m.If(pkt_len - 1 == 8): # sizeof(UDP header)
                        # set EOP
                        m.d.comb += self.source.eop.eq(1)
                        # mark output inactive
                        m.d.sync += output_active.eq(0)
                        # packet complete
                        m.next = "INIT"
                    
        return m

