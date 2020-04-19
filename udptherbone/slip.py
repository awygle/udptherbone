
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
        self.sink = StreamSink.from_source(input, name="unslip_sink")
        self.source = StreamSource(Layout([("data", 8, DIR_FANOUT)]), sop=False, eop=False, name="slip_source")
        
        self.err  = Signal()
        
    def elaborate(self, platform):
        sink = self.sink
        source = self.source
        
        m = Module()
        
        stalled = Signal()
        
        m.submodules.buffer = buff = SyncFIFO(width=8, depth=4)
        
        m.d.comb += sink.ready.eq(buff.w_rdy & ~stalled)
        m.d.comb += buff.w_en.eq(sink.we)
        
        # this should be a "connect" call
        m.d.comb += [
                sink.eop.eq(self._input.eop),
                sink.sop.eq(self._input.sop),
                sink.valid.eq(self._input.valid),
                self._input.ready.eq(self.sink.ready),
                sink.data.eq(self._input.data),
                ]
        
        m.d.comb += [
                source.data.eq(buff.r_data),
                source.valid.eq(buff.r_rdy),
                buff.r_en.eq(source.re)
                ]
        
        escapable = Signal()
        m.d.comb += escapable.eq((sink.data == SLIP_END) | (sink.data == SLIP_ESC))
        
        escaped = Signal(8)
        
        with m.FSM():
            with m.State("ACTIVE"):
                m.d.sync += stalled.eq(0)
                m.d.comb += buff.w_data.eq(Mux(escapable, SLIP_ESC, sink.data))
                with m.If(sink.we):
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
                            m.d.sync += escaped.eq(sink.data)
                            m.d.sync += stalled.eq(1)
                            m.next = "ESC"
                        with m.Case(0b11):
                            # EOP, escapable
                            # escape, dump to skid, stall for two cycles while ending packet
                            m.d.sync += escaped.eq(self._input.data)
                            m.d.sync += stalled.eq(1)
                            m.next = "ESC_END"
                        
            with m.State("END"):
                # end only
                m.d.comb += buff.w_data.eq(SLIP_END)
                m.d.comb += buff.w_en.eq(1)
                with m.If(buff.w_rdy):
                    m.d.sync += stalled.eq(0)
                    m.next = "ACTIVE"
                
            with m.State("ESC"):
                # escape only
                with m.If(escaped == SLIP_END):
                    m.d.comb += buff.w_data.eq(SLIP_ESC_END)
                with m.If(escaped == SLIP_ESC):
                    m.d.comb += buff.w_data.eq(SLIP_ESC_ESC)
                with m.Else():
                    # TODO assert this can't happen?
                    m.d.sync += self.err.eq(1)
                    m.next = "ACTIVE"
                m.d.comb += buff.w_en.eq(1)
                with m.If(buff.w_rdy):
                    m.d.sync += stalled.eq(0)
                    m.next = "ACTIVE"
                
            with m.State("ESC_END"):
                # escape, then end
                with m.If(escaped == SLIP_END):
                    m.d.comb += buff.w_data.eq(SLIP_ESC_END)
                with m.If(escaped == SLIP_ESC):
                    m.d.comb += buff.w_data.eq(SLIP_ESC_ESC)
                with m.Else():
                    # TODO assert this can't happen?
                    m.d.sync += self.err.eq(1)
                    m.next = "ACTIVE"
                m.d.comb += buff.w_en.eq(1)
                with m.If(buff.w_rdy):
                    m.d.sync += stalled.eq(1) # remain stalled
                    m.next = "END"
                        
        return m

class SLIPUnframer(Elaboratable):
    """
    TODO formal docstring
    Input: stream with framing
    Output: stream without framing
    Parameter: none?
    Control signals: error
    """
    def __init__(self, input: StreamSource):
        assert Record(input.payload_type).shape().width == 8
        assert not input.sop_enabled
        assert not input.eop_enabled
        
        self._input = input
        self.sink = StreamSink.from_source(input, name="slip_sink")
        self.source = StreamSource(Layout([("data", 8, DIR_FANOUT)]), sop=True, eop=True, name="unslip_source")
        
        self.err  = Signal()
        
    def elaborate(self, platform):
        sink = self.sink
        source = self.source
        
        m = Module()
        
        # input <-> sink <-> buff <-> source
        m.submodules.buff = buff = SyncFIFO(width=8, depth=2, fwft=True)
        
        stalled = Signal()
        
        # input <-> sink
        m.d.comb += [
                sink.valid.eq(self._input.valid),
                self._input.ready.eq(sink.ready),
                sink.data.eq(self._input.data),
                ]
        
        # sink <-> buff
        m.d.comb += [
                sink.ready.eq(buff.w_rdy),
                buff.w_data.eq(sink.data),
                buff.w_en.eq(sink.we),
                ]
        
        # buff <-> source
        m.d.comb += [
                source.valid.eq(buff.r_rdy & ~stalled),
                buff.r_en.eq(source.re | stalled),
                ]
            
        escape = Signal()
        escaped = Signal()
        end = Signal()
        input_end = Signal()
        m.d.comb += [
                escape.eq(buff.r_data == SLIP_ESC),
                end.eq(buff.r_data == SLIP_END),
                input_end.eq(buff.w_data == SLIP_END),
                ]
        
        m.d.sync += self.err.eq(0)
        
        with m.FSM():
            with m.State("INIT"):
                m.d.comb += source.data.eq(buff.r_data) # no case where this isn't OK
                with m.Switch(buff.r_data):
                    with m.Case(SLIP_ESC.value):
                        m.d.comb += source.eop.eq(0)
                        with m.If((buff.w_data == SLIP_ESC_ESC) | (buff.w_data == SLIP_ESC_END)):
                            # legal. go to escape state, drop this input
                            m.d.comb += stalled.eq(1)
                            with m.If(sink.we):
                                m.next = "ESCAPED_INIT"
                        with m.Else():
                            # illegal. pulse error, stay here
                            m.d.comb += stalled.eq(1)
                            m.d.sync += self.err.eq(1)
                            with m.If(sink.we):
                                m.next = "INIT" # for clarity
                    with m.Case(SLIP_END.value):
                        # we can ignore this, it's an empty packet
                        m.d.comb += source.eop.eq(0)
                        m.d.comb += stalled.eq(1)
                        with m.If(sink.we):
                            m.next = "INIT" # for clarity
                    with m.Default():
                        # normal stuff, set SOP, advance to ACTIVE
                        m.d.comb += source.sop.eq(1)
                        with m.If(buff.w_data == SLIP_END):
                            m.d.comb += source.eop.eq(1)
                        with m.Else():
                            m.d.comb += source.eop.eq(0)
                        with m.If(sink.we):
                            m.next = "ACTIVE"
            with m.State("ACTIVE"):
                m.d.comb += source.data.eq(buff.r_data) # no case where this isn't OK
                m.d.comb += source.sop.eq(0)
                with m.Switch(buff.r_data):
                    with m.Case(SLIP_ESC.value):
                        m.d.comb += source.eop.eq(0)
                        with m.If((buff.w_data == SLIP_ESC_ESC) | (buff.w_data == SLIP_ESC_END)):
                            # legal. go to escape state, drop this input
                            m.d.comb += stalled.eq(1)
                            with m.If(sink.we):
                                m.next = "ESCAPED"
                        with m.Else():
                            # illegal. pulse error, reset
                            m.d.comb += stalled.eq(1)
                            m.d.sync += self.err.eq(1)
                            with m.If(sink.we):
                                m.next = "INIT"
                    with m.Case(SLIP_END.value):
                        # we already set EOP last time through, skip + reset
                        m.d.comb += source.eop.eq(0)
                        m.d.comb += stalled.eq(1)
                        with m.If(sink.we):
                            m.next = "INIT"
                    with m.Default():
                        # normal stuff, stay here
                        with m.If(buff.w_data == SLIP_END):
                            m.d.comb += source.eop.eq(1)
                        with m.Else():
                            m.d.comb += source.eop.eq(0)
                        with m.If(sink.we):
                            m.next = "ACTIVE" # for clarity
            with m.State("ESCAPED"):
                m.d.comb += stalled.eq(0)
                m.d.comb += source.sop.eq(0)
                m.d.comb += source.eop.eq(0)
                with m.If(sink.we):
                    m.next = "ACTIVE" # always true
                with m.Switch(buff.r_data):
                    with m.Case(SLIP_ESC_ESC.value):
                        m.d.comb += source.data.eq(SLIP_ESC)
                    with m.Case(SLIP_ESC_END.value):
                        m.d.comb += source.data.eq(SLIP_END)
                    with m.Default():
                        # should never happen but pulse err anyway i guess
                        m.d.sync += self.err.eq(1)
                with m.If(buff.w_data == SLIP_END):
                    m.d.comb += source.eop.eq(1)
                with m.Else():
                    m.d.comb += source.eop.eq(0)
            with m.State("ESCAPED_INIT"):
                # same as Escaped except sets SOP
                m.d.comb += stalled.eq(0)
                m.d.comb += source.sop.eq(1)
                with m.If(sink.we):
                    m.next = "ACTIVE" # always true
                with m.Switch(buff.r_data):
                    with m.Case(SLIP_ESC_ESC.value):
                        m.d.comb += source.data.eq(SLIP_ESC)
                    with m.Case(SLIP_ESC_END.value):
                        m.d.comb += source.data.eq(SLIP_END)
                    with m.Default():
                        # should never happen but pulse err anyway i guess
                        m.d.sync += self.err.eq(1)
                        
        return m

