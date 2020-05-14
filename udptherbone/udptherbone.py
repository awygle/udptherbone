
from .udp import *
from .stream import *
from nmigen_soc.wishbone.bus import *

import math

def eb_write(addr, datas):
    import struct
    
    magic = struct.pack("!H", 0x4E6F)
    flags = struct.pack("!H", 0x1444) # no reads, 32-bit address, 32-bit data
    # 32-bit alignment yo
    moreflags = struct.pack("!H", 0x08FF) # CYC (end of cycle), use all byte enable bits
    counts = struct.pack("!H", 0x0100) # one write zero reads
    # 32-bit alignment yo
    addr = struct.pack("!L", addr)
    result = magic + flags + moreflags + counts + addr 
    for data in datas:
        d = struct.pack("!L", data)
        result += d
        
    return result

def eb_read(addr):
    import struct
    
    magic = struct.pack("!H", 0x4E6F)
    flags = struct.pack("!H", 0x1044) # 32-bit address, 32-bit data
    # 32-bit alignment yo
    moreflags = struct.pack("!H", 0x08FF) # CYC (end of cycle), use all byte enable bits
    counts = struct.pack("!H", 0x0001) # one read zero writes
    # 32-bit alignment yo
    ret_addr = struct.pack("!L", 0xDEADBEEF) # we're not gonna use this
    addr = struct.pack("!L", addr)
    
    return magic + flags + moreflags + counts + ret_addr + addr

class UDPTherbone(Elaboratable):
    def __init__(self, mtu=1500, addr_width=32, data_width=32, granularity=8, features=["stall"]):
        self.interface = Interface(addr_width=addr_width, data_width=data_width, granularity=granularity, features=features)
        self._mtu = mtu
        self._features = features
        self._addr_width = addr_width
        self._data_width = data_width
        self.sink = StreamSink(Layout([("data", 8, DIR_FANIN)]), sop=True, eop=True)
        self.source = StreamSource(Layout([("data", 8, DIR_FANOUT)]), sop=True, eop=True)
    
    def elaborate(self, platform):
        m = Module()
        
        sink = self.sink
        source = self.source
        sink_we = Signal()
        m.d.comb += sink_we.eq(sink.valid & sink.ready)
        source_we = Signal()
        m.d.comb += source_we.eq(source.valid & source.ready)
        interface = self.interface
        
        # STEP 1: Capture the packet input
        # Write data into the memory from SOP to EOP
        alignment = max(16, self._data_width, self._addr_width)
        nr = Signal()
        rf = Signal()
        wf = Signal()
        wcount = Signal(8)
        rcount = Signal(8)
        tcount = Signal(9)
        val = Signal(alignment)
        pad_count = Signal(range(4))
        if alignment == 16:
            m.submodules.fifo = fifo = SyncFIFOBuffered(width=alignment+2, depth=self._mtu)
        else:
            m.submodules.fifo = fifo = SyncFIFOBuffered(width=alignment, depth=self._mtu)
        m.d.comb += sink.ready.eq(fifo.w_rdy)
        m.d.sync += fifo.w_en.eq(0)
        with m.FSM(name="capture"):
            with m.State("IDLE"):
                # wait for sop
                with m.If(sink_we & sink.sop):
                    # TODO handle if eop is also set
                    # TODO error on invalid magic value (error generally)
                    with m.If(sink.data == 0x4E):
                        m.next = "MAGIC1"
            with m.State("MAGIC1"):
                # TODO handle eop
                with m.If(sink_we):
                    with m.If(sink.data == 0x6F):
                        m.next = "VERSION"
                    with m.Else():
                        # TODO handle error
                        m.next = "IDLE"
            with m.State("VERSION"):
                # TODO handle eop
                with m.If(sink_we):
                    with m.If(sink.data[4:] == 1):
                        # TODO handle PF - for now, assumed 0
                        # TODO handle PR - for now, assumed 0
                        # capture nr
                        m.d.sync += nr.eq(sink.data[2])
                        m.next = "SIZES"
                    with m.Else():
                        # TODO handle error
                        m.next = "IDLE"
            with m.State("SIZES"):
                # TODO handle eop
                with m.If(sink_we):
                    with m.If((sink.data[4:] == self._addr_width // 8) & (sink.data[:4] == self._data_width // 8)):
                        if alignment == 64:
                            m.d.sync += pad_count.eq(3)
                            m.next = "PADDING"
                        else:
                            m.next = "FLAGS"
                    with m.Else():
                        # TODO handle error
                        m.next = "IDLE"
            with m.State("PADDING"):
                # TODO handle eop
                with m.If(sink_we):
                    m.d.sync += pad_count.eq(pad_count - 1)
                    with m.If(pad_count == 0):
                        m.next = "FLAGS"
            with m.State("FLAGS"):
                # TODO handle eop
                # Assume CYC set, BCA RCA and WCA unset. Capture others
                with m.If(sink_we):
                    m.d.sync += rf.eq(sink.data[5])
                    m.d.sync += wf.eq(sink.data[1])
                    m.next = "BYTEEN"
            with m.State("BYTEEN"):
                # TODO handle eop
                # TODO figure out what this does and... deal with it somehow i guess
                with m.If(sink_we):
                    m.next = "WCOUNT"
            with m.State("WCOUNT"):
                # TODO handle eop
                with m.If(sink_we):
                    m.d.sync += wcount.eq(sink.data)
                    m.next = "RCOUNT"
            with m.State("RCOUNT"):
                # TODO handle eop
                with m.If(sink_we):
                    m.d.sync += rcount.eq(sink.data)
                    if alignment == 64:
                        m.d.sync += pad_count.eq(3)
                        m.next = "PADDING2"
                    else:
                        m.d.sync += fifo.w_data.eq(Cat((sink.data), wcount, Repl(0, alignment - 16)))
                        m.d.sync += fifo.w_en.eq(1)
                        #m.d.sync += tcount.eq(wcount + rcount)
                        m.d.sync += tcount.eq(wcount + (sink.data) + (wcount > 0) + ((sink.data) > 0))
                        m.d.sync += pad_count.eq((alignment//8)-1)
                        with m.If(wcount + (sink.data) > 0):
                            m.next = "BLOCK"
                        with m.Else():
                            m.next = "IDLE"
            with m.State("PADDING2"):
                # TODO handle eop
                with m.If(sink_we):
                    m.d.sync += pad_count.eq(pad_count - 1)
                    with m.If(pad_count == 0):
                        if alignment == 16:
                            m.d.sync += fifo.w_data.eq(Cat(rcount, wcount, rf))
                        else:
                            m.d.sync += fifo.w_data.eq(Cat(rcount, wcount, rf, wf, Repl(0, alignment - 18)))
                        m.d.sync += fifo.w_en.eq(1)
                        m.d.sync += tcount.eq(wcount + rcount + (wcount > 0) + (rcount > 0))
                        m.d.sync += pad_count.eq((alignment//8)-1)
                        with m.If(wcount + rcount > 0):
                            m.next = "BLOCK"
                        with m.Else():
                            m.next = "IDLE"
            with m.State("BLOCK"):
                # TODO handle eop
                with m.If(sink_we):
                    m.d.sync += val.word_select(pad_count, 8).eq(sink.data)
                    m.d.sync += pad_count.eq(pad_count - 1)
                    with m.If(pad_count == 0):
                        m.d.sync += fifo.w_data.eq(Cat(sink.data, val[8:]))
                        m.d.sync += fifo.w_en.eq(1)
                        m.d.sync += tcount.eq(tcount - 1)
                        m.d.sync += pad_count.eq((alignment//8)-1)
                        with m.If(tcount == 0):
                            with m.If(sink.eop):
                                m.next = "IDLE"
                            with m.Else():
                                m.next = "FLAGS"
            
        # STEP 2: Extract the Wishbone transactions, one at a time
        # First get the flags and counts. Then do writes, then reads, address, then data.
        read_inc = Signal()
        write_inc = Signal()
        read_count = Signal(8)
        write_count = Signal(8)
        address = Signal(self._addr_width)
        value = Signal(self._data_width)
        write_start = Signal()
        read_start = Signal()
        m.submodules.output_fifo = output_fifo = SyncFIFO(width=alignment, depth=self._mtu)
        m.d.sync += output_fifo.w_en.eq(0) # unless overridden
        with m.FSM(name="extract"):
            with m.State("IDLE"):
                # wait for data
                with m.If(fifo.r_rdy):
                    m.d.comb += fifo.r_en.eq(1)
                    rcount_cur = fifo.r_data[:8]
                    m.d.sync += read_count.eq(rcount_cur)
                    wcount_cur = fifo.r_data[8:16]
                    m.d.sync += write_count.eq(wcount_cur)
                    m.d.sync += read_inc.eq(~fifo.r_data[16])
                    m.d.sync += write_inc.eq(~fifo.r_data[17])
                    with m.If(rcount_cur > 0):
                        # we need RFF and RCount in the response section
                        m.d.sync += output_fifo.w_data.eq(Cat(rcount_cur, ~read_inc))
                        m.d.sync += output_fifo.w_en.eq(1)
                        m.next = "RADDR"
                    with m.If(wcount_cur > 0):
                        m.next = "WADDR"
            with m.State("WADDR"):
                with m.If(fifo.r_rdy):
                    m.d.comb += fifo.r_en.eq(1)
                    m.d.sync += address.eq(fifo.r_data[:self._addr_width])
                    m.next = "WVAL"
            with m.State("WVAL"):
                with m.If(fifo.r_rdy & ~write_start):
                    m.d.comb += fifo.r_en.eq(1)
                    m.d.sync += value.eq(fifo.r_data)
                    m.d.sync += write_start.eq(1)
                    m.d.sync += write_count.eq(write_count - 1)
                    with m.If(write_count == 0):
                        with m.If(read_count > 0):
                            m.next = "RADDR"
                        with m.Else():
                            m.next = "IDLE"
            with m.State("RADDR"):
                with m.If(fifo.r_rdy):
                    m.d.comb += fifo.r_en.eq(1)
                    m.d.sync += address.eq(fifo.r_data[:self._addr_width])
                    # we need the read address in the response section
                    m.d.sync += output_fifo.w_data.eq(fifo.r_data[:self._addr_width])
                    m.d.sync += output_fifo.w_en.eq(1)
                    m.next = "RVAL"
            with m.State("RVAL"):
                with m.If(fifo.r_rdy & ~read_start):
                    m.d.comb += fifo.r_en.eq(1)
                    m.d.sync += value.eq(fifo.r_data)
                    m.d.sync += read_start.eq(1)
                    m.d.sync += read_count.eq(read_count - 1)
                    with m.If(read_count == 0):
                        m.next = "IDLE"
                    
        # STEP 3: Do the Wishbone transactions
        # This is very sub-optimal from a throughput perspective but honestly, who cares
        response = Signal(self._data_width)
        with m.FSM(name="wishbone"):
            with m.State("IDLE"):
                with m.If(write_start):
                    m.d.sync += interface.dat_w.eq(value)
                    m.d.sync += interface.adr.eq(address)
                    m.d.sync += interface.we.eq(1)
                    m.d.sync += interface.sel.eq(~0)
                    m.d.sync += interface.cyc.eq(1)
                    m.d.sync += interface.stb.eq(1)
                    m.d.sync += write_start.eq(0)
                    m.next = "WRITE"
                with m.If(read_start):
                    m.d.sync += interface.adr.eq(value)
                    m.d.sync += interface.we.eq(0)
                    m.d.sync += interface.sel.eq(~0)
                    m.d.sync += interface.cyc.eq(1)
                    m.d.sync += interface.stb.eq(1)
                    m.d.sync += read_start.eq(0)
                    m.next = "READ"
            with m.State("WRITE"):
                # single write
                # if pipelined, drop strobe and write enable
                if "stall" in self._features:
                    m.d.sync += interface.stb.eq(0)
                    m.d.sync += interface.we.eq(0)
                with m.If(interface.ack):
                    # drop cyc, and also stb and we if not dropped earlier
                    m.d.sync += interface.cyc.eq(0)
                    m.d.sync += interface.stb.eq(0)
                    m.d.sync += interface.we.eq(0)
                    with m.If(write_inc):
                        m.d.sync += address.eq(address + 1)
                    m.next = "IDLE"
            with m.State("READ"):
                # TODO this is all basically wrong actually
                # if pipelined, drop strobe
                if "stall" in self._features:
                    m.d.sync += interface.stb.eq(0)
                with m.If(interface.ack):
                    # drop cyc, and also stb if not dropped earlier
                    m.d.sync += interface.cyc.eq(0)
                    m.d.sync += interface.stb.eq(0)
                    # latch value into output FIFO
                    m.d.sync += output_fifo.w_data.eq(interface.dat_r)
                    m.d.sync += output_fifo.w_en.eq(1)
                    with m.If(read_inc):
                        m.d.sync += address.eq(address + 1)
                    m.next = "IDLE"
                
        # STEP 4: Return any read responses
        # Need RFF and RCount in this chunk - make that the first word
        output_count = Signal(8)
        output_rff = Signal()
        output_value = Signal(alignment)
        if alignment == 64:
            output_header = Signal(128)
            m.d.comb += [
                    output_header[:8].eq(C(0x4E, 8)),
                    output_header[8:16].eq(C(0x6F, 8)),
                    output_header[16:24].eq(C(0x14, 8)), # version == 1, NR = 1
                    output_header[24:32].eq(Cat(C(self._data_width / 8, 4), C(self._addr_width / 8, 4))),
                    output_header[32:64].eq(C(0, 32)),
                    output_header[64:72].eq(C(0x08, 8) | (output_rff << 5)), # CYC is always set
                    output_header[72:80].eq(C(0xFF, 8)), # byte enable, who knows
                    output_header[80:88].eq(C(0x00, 8)),
                    output_header[88:96].eq(output_count),
                    output_header[96:128].eq(C(0, 32)),
                ]
            output_offset = Signal(range(128 // 8))
        else:
            output_header = Signal(64)
            m.d.comb += [
                    output_header[:8].eq(C(0x4E, 8)),
                    output_header[8:16].eq(C(0x6F, 8)),
                    output_header[16:24].eq(C(0x14, 8)), # version == 1, NR = 1
                    output_header[24:32].eq(Cat(C(self._data_width / 8, 4), C(self._addr_width / 8, 4))),
                    output_header[32:40].eq(C(0x08, 8) | (output_rff << 5)), # CYC is always set
                    output_header[40:48].eq(C(0xFF, 8)), # byte enable, who knows
                    output_header[48:56].eq(C(0x00, 8)),
                    output_header[56:64].eq(output_count)
                ]
            output_offset = Signal(range(64 // 8))
        m.d.sync += output_fifo.r_en.eq(0)
        with m.FSM(name="respond"):
            with m.State("IDLE"):
                with m.If(output_fifo.r_rdy):
                    m.d.sync += output_count.eq(output_fifo.r_data[:8])
                    m.d.sync += output_rff.eq(output_fifo.r_data[8])
                    m.d.sync += output_fifo.r_en.eq(1)
                    m.d.sync += source.data.eq(output_header[:8])
                    m.d.sync += source.valid.eq(1)
                    m.d.sync += output_offset.eq(1)
                    m.d.sync += source.sop.eq(1)
                    m.next = "HEADER"
            with m.State("HEADER"):
                with m.If(source_we):
                    m.d.sync += source.sop.eq(0)
                    m.d.sync += output_offset.eq(output_offset + 1)
                    m.d.sync += source.data.eq(output_header.word_select(output_offset, 8))
                    with m.If(output_offset == 0):
                        m.d.sync += source.valid.eq(output_fifo.r_rdy)
                        with m.If(output_fifo.r_rdy):
                            m.d.sync += output_value.eq(output_fifo.r_data)
                            m.d.sync += output_fifo.r_en.eq(1)
                            m.d.sync += source.data.eq(output_fifo.r_data.word_select((alignment // 8) - 1, 8))
                            m.d.sync += output_offset.eq((alignment // 8) - 1)
                            m.next = "ADDR"
            with m.State("ADDR"):
                m.d.sync += source.data.eq(output_value.word_select(output_offset, 8))
                with m.If(source_we):
                    m.d.sync += output_offset.eq(output_offset - 1)
                    m.d.sync += source.data.eq(output_value.word_select(output_offset - 1, 8))
                    with m.If(output_offset == 0):
                        m.d.sync += source.valid.eq(output_fifo.r_rdy)
                        with m.If(output_fifo.r_rdy):
                            m.d.sync += output_count.eq(output_count - 1)
                            m.d.sync += output_value.eq(output_fifo.r_data)
                            m.d.sync += output_fifo.r_en.eq(1)
                            m.d.sync += source.data.eq(output_fifo.r_data.word_select((alignment // 8) - 1, 8))
                            m.d.sync += output_offset.eq((alignment // 8) - 1)
                            m.next = "DATA"
            with m.State("DATA"):
                m.d.sync += source.data.eq(output_value.word_select(output_offset, 8))
                with m.If(source_we):
                    m.d.sync += output_offset.eq(output_offset - 1)
                    m.d.sync += source.data.eq(output_value.word_select(output_offset - 1, 8))
                    m.d.sync += source.eop.eq((output_offset == 1) & (output_count == 0))
                    with m.If(output_offset == 0):
                        with m.If(output_count > 0):
                            m.d.sync += source.valid.eq(output_fifo.r_rdy)
                            with m.If(output_fifo.r_rdy):
                                m.d.sync += output_count.eq(output_count - 1)
                                m.d.sync += output_value.eq(output_fifo.r_data)
                                m.d.sync += output_fifo.r_en.eq(1)
                                m.d.sync += source.data.eq(output_value.word_select((alignment // 8) - 1, 8))
                                m.d.sync += output_offset.eq((alignment // 8) - 1)
                                m.next = "DATA"
                        with m.Else():
                            m.next = "IDLE"

        return m

if __name__ == "__main__":
    input = i = StreamSource(Layout([("data", 8, DIR_FANOUT)]))
    
    ports = []

    import argparse

    parser = argparse.ArgumentParser()
    p_action = parser.add_subparsers(dest="action")
    p_action.add_parser("simulate")
    p_action.add_parser("generate")

    args = parser.parse_args()
    if args.action == "simulate":
        from nmigen.back.pysim import Simulator, Passive
        
        source = UDPTherboneSource()

        sim = Simulator(source)
        sim.add_clock(1e-6)
        
        def transmit_proc():
            yield
        
        def receive_proc():
            yield

        sim.add_sync_process(transmit_proc)
        sim.add_sync_process(receive_proc)
        
        with sim.write_vcd("udp_pa.vcd", "udp_pa.gtkw"):
            sim.run()

    if args.action == "generate":
        from nmigen.back import verilog

        print(verilog.convert(packetizer, ports=ports))
        
    if args.action == "program":
        platform = VersaECP5Platform()
        platform.build(packetizer, do_program=True)
    

