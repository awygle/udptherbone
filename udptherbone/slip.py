
from nmigen import *
from nmigen.lib.fifo import SyncFIFO
from .stream import *

SLIP_END = C(0xC0, 8)
SLIP_ESC = C(0xDB, 8)
SLIP_ESC_END = C(0xDC, 8)
SLIP_ESC_ESC = C(0xDD, 8)

def slip_encode(b):
    res = b.replace(b'\xdb', b'\xdb\xdd')
    res = res.replace(b'\xc0', b'\xdb\xdc')
    res += b'\xc0'
    return res

def slip_decode(b):
    res = b.replace(b'\xdb\xdd', b'\xdb')
    res = res.replace(b'\xdb\xdc', b'\xc0')
    return res[:-1]

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
        
        stalled = Signal(range(4))
        
        m.d.comb += sink.ready.eq(stalled == 0)
        
        # this should be a "connect" call
        m.d.comb += [
                sink.eop.eq(self._input.eop),
                sink.sop.eq(self._input.sop),
                sink.valid.eq(self._input.valid),
                self._input.ready.eq(self.sink.ready),
                sink.data.eq(self._input.data),
                ]
        
        m.d.comb += source.valid.eq(stalled > 0)
        
        escapable = Signal()
        m.d.comb += escapable.eq((sink.data == SLIP_END) | (sink.data == SLIP_ESC))
        
        escaped = Signal(8)
        held = Signal(8)
        
        with m.If(source.re):
            m.d.sync += stalled.eq(stalled - 1)
            
        with m.FSM():
            with m.State("ACTIVE"):
                with m.If(sink.we):
                    m.d.sync += held.eq(sink.data)
                    with m.Switch(Cat(self.sink.eop, escapable)):
                        with m.Case(0b00):
                            # not EOP, not escapable
                            # simply pass through
                            m.d.sync += stalled.eq(1)
                            m.d.sync += source.data.eq(sink.data)
                        with m.Case(0b01):
                            # EOP, not escapable
                            # write out and then transition to END state - stall for one additional cycle
                            m.d.sync += stalled.eq(2)
                            m.d.sync += source.data.eq(sink.data)
                            m.next = "END"
                        with m.Case(0b10):
                            # not EOP, escapable
                            # escape, stall for one additional cycle
                            m.d.sync += stalled.eq(2)
                            m.d.sync += source.data.eq(SLIP_ESC)
                            m.next = "ESC"
                        with m.Case(0b11):
                            # EOP, escapable
                            # stall for two additional cycles while ending packet
                            m.d.sync += stalled.eq(3)
                            m.d.sync += source.data.eq(SLIP_ESC)
                            m.next = "ESC_END"
                        
            with m.State("END"):
                # end only
                with m.If(source.re):
                    m.d.sync += source.data.eq(SLIP_END)
                    m.next = "ACTIVE"
                
            with m.State("ESC"):
                # escape only
                with m.If(source.re):
                    with m.Switch(held):
                        with m.Case(SLIP_END.value):
                            m.d.sync += source.data.eq(SLIP_ESC_END)
                        with m.Case(SLIP_ESC.value):
                            m.d.sync += source.data.eq(SLIP_ESC_ESC)
                        with m.Default():
                            # TODO assert this can't happen?
                            m.d.sync += self.err.eq(1)
                    m.next = "ACTIVE"
                
            with m.State("ESC_END"):
                # escape, then end
                with m.If(source.re):
                    with m.Switch(held):
                        with m.Case(SLIP_END.value):
                            m.d.sync += source.data.eq(SLIP_ESC_END)
                        with m.Case(SLIP_ESC.value):
                            m.d.sync += source.data.eq(SLIP_ESC_ESC)
                        with m.Default():
                            # TODO assert this can't happen?
                            m.d.sync += self.err.eq(1)
                            m.next = "ACTIVE"
                    m.next = "END"
                        
        return m

class SLIPUnframer(Elaboratable):
    """
    TODO formal docstring
    Input: stream without framing
    Output: stream with framing
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
        
        # connect input to sink
        m.d.comb += [
                sink.data.eq(self._input.data),
                self._input.ready.eq(sink.ready),
                sink.valid.eq(self._input.valid),
            ]
        
        future = sink.data
        current = Signal(8)
        
        init = Signal()
        read_en = Signal()
        
        with m.If(source.re):
            m.d.sync += read_en.eq(0) # may be overridden below
            m.d.sync += source.eop.eq(0)
        
        with m.If(sink.we):
            m.d.sync += current.eq(future)
            m.d.sync += init.eq(1) # have to skip first write, prime the pump
            with m.If(future == SLIP_END.value):
                m.d.sync += source.eop.eq(1)
            
        
        m.d.comb += self.err.eq(0)
        
        m.d.comb += sink.ready.eq(~read_en)
        m.d.comb += source.valid.eq(read_en)
        
        with m.If(sink.we & init):
            with m.FSM():
                with m.State("INIT"):
                    with m.Switch(current):
                        with m.Case(SLIP_ESC.value):
                            # go to escape state, wait for next input
                            m.d.sync += read_en.eq(0)
                            m.next = "ESCAPED_INIT"
                        with m.Case(SLIP_END.value):
                            # we can ignore this, it's an empty packet
                            m.d.sync += read_en.eq(0)
                            m.next = "INIT" # for clarity
                        with m.Default():
                            # normal stuff, output, set SOP, advance to ACTIVE
                            m.d.sync += source.data.eq(current)
                            m.d.sync += read_en.eq(1)
                            m.d.sync += source.sop.eq(1)
                            m.next = "ACTIVE"
                with m.State("ACTIVE"):
                    m.d.sync += source.sop.eq(0)
                    with m.Switch(current):
                        with m.Case(SLIP_ESC.value):
                            # legal. go to escape state, wait for input
                            m.d.sync += read_en.eq(0)
                            m.next = "ESCAPED"
                        with m.Case(SLIP_END.value):
                            # EOP handled above, wait + reset
                            m.d.sync += read_en.eq(0)
                            m.next = "INIT"
                        with m.Default():
                            # normal stuff, stay here
                            m.d.sync += source.data.eq(current)
                            m.d.sync += read_en.eq(1)
                            m.next = "ACTIVE" # for clarity
                with m.State("ESCAPED"):
                    with m.Switch(current):
                        with m.Case(SLIP_ESC_ESC.value):
                            m.d.sync += read_en.eq(1)
                            m.d.sync += source.data.eq(SLIP_ESC)
                            m.next = "ACTIVE"
                        with m.Case(SLIP_ESC_END.value):
                            m.d.sync += read_en.eq(1)
                            m.d.sync += source.data.eq(SLIP_END)
                            m.next = "ACTIVE"
                        with m.Default():
                            # pulse err, return to INIT
                            m.d.comb += self.err.eq(1)
                            m.d.sync += read_en.eq(0)
                            m.next = "INIT"
                with m.State("ESCAPED_INIT"):
                    # same as Escaped except sets SOP
                    m.d.sync += source.sop.eq(1)
                    with m.Switch(current):
                        with m.Case(SLIP_ESC_ESC.value):
                            m.d.sync += read_en.eq(1)
                            m.d.sync += source.data.eq(SLIP_ESC)
                            m.next = "ACTIVE"
                        with m.Case(SLIP_ESC_END.value):
                            m.d.sync += read_en.eq(1)
                            m.d.sync += source.data.eq(SLIP_END)
                            m.next = "ACTIVE"
                        with m.Default():
                            # pulse err, return to INIT
                            m.d.sync += read_en.eq(0)
                            m.d.comb += self.err.eq(1)
                            m.next = "INIT"
                        
        return m

