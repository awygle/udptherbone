
from nmigen import *
from nmigen.lib.fifo import SyncFIFO
from .stream import *

SLIP_END = C(0xC0, 8)
SLIP_ESC = C(0xDB, 8)
SLIP_ESC_END = C(0xDC, 8)
SLIP_ESC_ESC = C(0xDD, 8)

class SLIPFramer(Elaboratable):
    """
    TODO formal docstring
    Input: stream with framing
    Output: stream without framing
    Parameter: none?
    Control signals: error
    """
    def __init__(self, input: StreamSource):
        assert Record(input.payload_type).shape().width == 8
        assert input.sop_enabled
        assert input.eop_enabled
        
        self._input = input
        self.sink = StreamSink.from_source(input, name="slip_sink")
        self.source = StreamSource(Layout([("data", 8, DIR_FANOUT)]), sop=False, eop=False, name="slip_source")
        
        self.err  = Signal()
        
    def elaborate(self, platform):
        sink = self.sink
        source = self.source
        
        m = Module()
        
        we = Signal()
        m.d.comb += we.eq(sink.valid & sink.ready)
        re = Signal()
        m.d.comb += re.eq(source.valid & source.ready)
        
        stalled = Signal()
        
        m.submodules.buffer = buff = SyncFIFOStream(payload_type=Layout([("data", 8)]), depth=4)
        m.d.comb += self.sink.ready.eq(buff.sink.ready & ~stalled)
        m.d.comb += buff.sink.valid.eq(self.sink.valid)
        
        m.d.comb += self.sink.connect(self._input)
        m.d.comb += [
                buff.sink.data.eq(self.sink.data),
                ]
        m.d.comb += [
                self.source.data.eq(buff.source.data),
                self.source.valid.eq(buff.source.valid),
                buff.source.ready.eq(self.source.ready)
                ]
        
        escapable = Signal()
        m.d.comb += escapable.eq((sink.data == SLIP_END) | (sink.data == SLIP_ESC))
        
        escaped = Signal(8)
        
        with m.FSM():
            with m.State("ACTIVE"):
                m.d.sync += stalled.eq(0)
                with m.If(we):
                    with m.Switch(Cat(self.sink.eop, escapable)):
                        with m.Case(0b00):
                            # not EOP, not escapable
                            # simply pass through
                            m.d.sync += stalled.eq(0)
                        with m.Case(0b01):
                            # EOP, not escapable
                            # write out and then transition to END state - stall for one cycle
                            m.d.sync += stalled.eq(1)
                            m.next = "END"
                        with m.Case(0b10):
                            # not EOP, escapable
                            # escape, dump to skid, stall for one cycle
                            m.d.sync += escaped.eq(self._input.data)
                            m.d.comb += buff.sink.data.eq(SLIP_ESC)
                            m.d.sync += stalled.eq(1)
                            m.next = "ESC"
                        with m.Case(0b11):
                            # EOP, escapable
                            # escape, dump to skid, stall for two cycles while ending packet
                            m.d.sync += escaped.eq(self._input.data)
                            m.d.comb += buff.sink.data.eq(SLIP_ESC)
                            m.d.sync += stalled.eq(1)
                            m.next = "ESC_END"
                        
            with m.State("END"):
                # end only
                m.d.comb += buff.sink.data.eq(SLIP_END)
                m.d.comb += buff.sink.valid.eq(1)
                with m.If(buff.sink.ready):
                    m.d.sync += stalled.eq(0)
                    m.next = "ACTIVE"
                
            with m.State("ESC"):
                # escape only
                with m.If(escaped == SLIP_END):
                    m.d.comb += buff.sink.data.eq(SLIP_ESC_END)
                with m.If(escaped == SLIP_ESC):
                    m.d.comb += buff.sink.data.eq(SLIP_ESC_ESC)
                with m.Else():
                    # TODO assert this can't happen
                    pass
                m.d.comb += buff.sink.valid.eq(1)
                with m.If(buff.sink.ready):
                    m.d.sync += stalled.eq(0)
                    m.next = "ACTIVE"
                
            with m.State("ESC_END"):
                # escape, then end
                with m.If(escaped == SLIP_END):
                    m.d.comb += buff.sink.data.eq(SLIP_ESC_END)
                with m.If(escaped == SLIP_ESC):
                    m.d.comb += buff.sink.data.eq(SLIP_ESC_ESC)
                with m.Else():
                    # TODO assert this can't happen
                    pass
                m.d.comb += buff.sink.valid.eq(1)
                with m.If(buff.sink.ready):
                    m.d.sync += stalled.eq(1) # remain stalled
                    m.next = "END"
                        
        return m
    
if __name__ == "__main__":
    input = i = StreamSource(Layout([("data", 8, DIR_FANOUT)]), name="input")
    wiggle = Signal()
    framer = f = SLIPFramer(input)
    
    ports = []

    import argparse

    parser = argparse.ArgumentParser()
    p_action = parser.add_subparsers(dest="action")
    p_action.add_parser("simulate")
    p_action.add_parser("generate")

    args = parser.parse_args()
    if args.action == "simulate":
        from nmigen.back.pysim import Simulator, Passive

        sim = Simulator(framer)
        sim.add_clock(1e-6)
        
        def transmit_proc():
            yield
            g = 0
            d = "hel\xc0\xc0lo world\xdb"
            m = len(d)
            while g < m:
                c = d[g]
                yield i.data.eq(ord(c))
                yield i.sop.eq(0)
                yield i.eop.eq(0)
                if c == 'h':
                    yield i.sop.eq(1)
                elif c == ' ':
                    yield i.eop.eq(1)
                elif c == 'w':
                    yield i.sop.eq(1)
                elif c == '\xdb':
                    yield i.eop.eq(1)
                yield i.valid.eq(1)
                yield
                print("writing " + str(hex((yield f.sink.data))) + \
                    ", ready is " + str((yield f.sink.ready)) + \
                    ", valid is " + str((yield f.sink.valid)))
                if (yield f.sink.ready) == 1:
                    g += 1
            for g in range(0, 16):
                yield i.valid.eq(0)
                yield
        
        def receive_proc():
            for g in range(0, 16):
                yield
            data = []
            yield f.source.ready.eq(1)
            yield
            #for g in range(0, 128):
            while not (yield f.source.valid) == 0:
                if (yield f.source.valid) == 1:
                    data.append((yield f.source.data))
                    print("reading " + str(hex((yield f.source.data))) + \
                        ", ready is " + str((yield f.source.ready)) + \
                        ", valid is " + str((yield f.source.valid)))
                yield
            
            print(list(map(hex, data)))
            print(list(map(chr, data)))

        sim.add_sync_process(transmit_proc)
        sim.add_sync_process(receive_proc)
        
        with sim.write_vcd("slip.vcd", "slip.gtkw"):
            sim.run()

    if args.action == "generate":
        from nmigen.back import verilog

        print(verilog.convert(packetizer, ports=ports))
        
    if args.action == "program":
        platform = VersaECP5Platform()
        platform.build(packetizer, do_program=True)
    

