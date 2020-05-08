from nmigen.test.utils import *
from udptherbone.slip import *
from nmigen.asserts import *

class SLIPFramerSafetyProperties(Elaboratable):
    def __init__(self):
        pass
    
    def elaborate(m, platform):
        assert platform == "formal"
        
        m = Module()
        
        i = StreamSource(Layout([("data", 8, DIR_FANOUT)]), name="input", sop=True, eop=True)
        
        m.submodules.dut = f = SLIPFramer(i)
        
        f_last_read = Signal(8)
        f_eop = Signal()
        f_esc = Signal(2)
        f_escaped = Signal(8, reset=SLIP_ESC.value)
        
        # Error signal only indicates impossible states - should never be set
        m.d.comb += Assert(~f.err)
        
        # if SLIP_ESC or SLIP_END is specified, SLIP_ESC and the corresponding escape
        # value must be written out before the next value is written in
        with m.If(f.sink.we):
            with m.If((f.sink.data == SLIP_ESC) | (f.sink.data == SLIP_END)):
                m.d.sync += f_esc.eq(2)
                m.d.sync += f_escaped.eq(f.sink.data)
        with m.If(f.source.re & (f_esc == 2)):
            m.d.comb += Assert(f.source.data == SLIP_ESC)
            m.d.sync += f_esc.eq(1)
        with m.If(f.source.re & (f_escaped == SLIP_ESC) & (f_esc == 1)):
            m.d.comb += Assert(f.source.data == SLIP_ESC_ESC)
            m.d.sync += f_esc.eq(0)
        with m.If(f.source.re & (f_escaped == SLIP_END) & (f_esc == 1)):
            m.d.comb += Assert(f.source.data == SLIP_ESC_END)
            m.d.sync += f_esc.eq(0)
        m.d.comb += Assert((f_escaped == SLIP_ESC) | (f_escaped == SLIP_END))
        
        # if EOP is signaled, SLIP_END must be written before the next value is written
        with m.If(f.sink.we & f.sink.eop):
            m.d.sync += f_eop.eq(1)
        with m.If(f.source.re & (f.source.data == SLIP_END)):
            m.d.sync += f_eop.eq(0)
        with m.If(f.sink.we):
            m.d.comb += Assert(~f_eop)
        
        # SLIP_ESC can only be followed by SLIP_ESC_ESC or SLIP_ESC_END
        with m.If(f.source.re):
            m.d.sync += f_last_read.eq(f.source.data)
            with m.If(f_last_read == SLIP_ESC):
                m.d.comb += Assert((f.source.data == SLIP_ESC_ESC) | (f.source.data == SLIP_ESC_END))
        
        return m

class SLIPFramerLivenessProperties(Elaboratable):
    def __init__(self):
        pass
    
    def elaborate(self, platform):
        assert platform == "formal"
        
        m = Module()
        
        i = StreamSource(Layout([("data", 8, DIR_FANOUT)]), name="input", sop=True, eop=True)
        
        m.submodules.dut = f = SLIPFramer(i)
        
        # These should be shown without reset occuring
        f_past_rst = Signal(reset_less = True)
        with m.If(ResetSignal()):
            m.d.sync += f_past_rst.eq(1)
        f_rst = Signal(reset_less = True)
        m.d.comb += f_rst.eq(ResetSignal() | f_past_rst)
        
        # Any output should be possible
        m.d.comb += Cover(f.source.data == AnyConst(8))
        
        # ESC escaping
        f_last_read = Signal(8)
        with m.If(f.source.re):
            m.d.sync += f_last_read.eq(f.source.data)
        m.d.comb += Cover((f.source.data == SLIP_ESC_ESC) & (f_last_read == SLIP_ESC) & ~f_rst)
        
        # END escaping
        m.d.comb += Cover((f.source.data == SLIP_ESC_END) & (f_last_read == SLIP_ESC) & ~f_rst)
        
        # END
        m.d.comb += Cover(f.source.data == SLIP_END & ~f_rst)
        
        # ESC followed by END
        f_two_ago = Signal(8)
        with m.If(f.source.re):
            m.d.sync += f_two_ago.eq(f_last_read)
        m.d.comb += Cover((f.source.data == SLIP_END) & (f_last_read == SLIP_ESC_ESC) & (f_two_ago == SLIP_ESC) & ~f_rst)
        
        # END followed by END
        f_two_ago = Signal(8)
        with m.If(f.source.re):
            m.d.sync += f_two_ago.eq(f_last_read)
        m.d.comb += Cover((f.source.data == SLIP_END) & (f_last_read == SLIP_ESC_END) & (f_two_ago == SLIP_ESC))
        
        # Throughput - must be able to handle 4 back-to-back writes
        #f_w_en = Signal()
        #m.d.comb += f_w_en.eq(f.sink.we)
        #m.d.comb += Cover(f_w_en & Past(f_w_en) & Past(f_w_en, 2) & Past(f_w_en, 3) & ~f_rst)
        
        # Throughput - must be able to handle 2 writes in 4 where every write is escapable
        #f_escapable = Signal()
        #m.d.comb += f_escapable.eq((f.sink.data == SLIP_END) | (f.sink.data == SLIP_ESC))
        #
        #m.d.comb += Cover(f_escapable & Past(f_escapable) & Past(f_escapable, 2) & Past(f_escapable, 3) 
        #        & f_w_en &  Past(f_w_en, 2)
        #        & ~ResetSignal() & ~Past(ResetSignal()) & ~Past(ResetSignal(), 2) & ~Past(ResetSignal(), 3))
        
        return m

class SLIPUnframerSafetyProperties(Elaboratable):
    def __init__(self):
        pass
    
    def elaborate(self, platform):
        assert platform == "formal"
        
        m = Module()
        
        i = StreamSource(Layout([("data", 8, DIR_FANOUT)]), name="input", sop=False, eop=False)
        
        m.submodules.dut = u = SLIPUnframer(i)
        
        # if we get an ESC, shouldn't output anything until we get another input
        # have to delay by 1 because of internal buffering
        f_last_written = Signal(8)
        f_esc = Signal()
        with m.If(u.sink.we):
            m.d.sync += f_last_written.eq(u.sink.data)
            with m.If(f_last_written == SLIP_ESC):
                m.d.sync += f_esc.eq(1)
            with m.Else():
                m.d.sync += f_esc.eq(0)
        with m.If(f_esc):
            m.d.comb += Assert(~u.source.re)
        
        # under non-error conditions, if we get an END, next readout should be previous (possibly escaped) value + EOP
        f_two_ago = Signal(8)
        f_three_ago = Signal(8)
        f_ever_err = Signal()
        with m.If(u.err):
            m.d.sync += f_ever_err.eq(1)
        with m.If(u.sink.we):
            m.d.sync += f_two_ago.eq(f_last_written)
            m.d.sync += f_three_ago.eq(f_two_ago)
        with m.If(~f_ever_err):
            with m.If(f_last_written == SLIP_END):
                with m.If(u.source.re):
                    m.d.comb += Assert(u.source.eop)
                    with m.If(f_three_ago == SLIP_ESC):
                        with m.If(f_two_ago == SLIP_ESC_ESC):
                            m.d.comb += Assert(u.source.data == SLIP_ESC)
                        with m.Elif(f_two_ago == SLIP_ESC_END):
                            m.d.comb += Assert(u.source.data == SLIP_END)
                    with m.Else():
                        m.d.comb += Assert(u.source.data == f_two_ago)
        
        # if we get an ESC followed by an illegal value, we should raise err
        f_two_esc = Signal()
        with m.If(u.sink.we):
            m.d.sync += f_two_esc.eq(f_esc)
        with m.If(u.sink.we & f_esc & ~f_ever_err):
            m.d.comb += Assert((f_last_written == SLIP_ESC_ESC) | (f_last_written == SLIP_ESC_END) | u.err)
        
        return m
    
class SLIPUnframerLivenessProperties(Elaboratable):
    def __init__(self):
        pass
    
    def elaborate(self, platform):
        assert platform == "formal"
        
        m = Module()
        
        i = StreamSource(Layout([("data", 8, DIR_FANOUT)]), name="input", sop=False, eop=False)
        
        m.submodules.dut = u = SLIPUnframer(i)
        
        # error
        m.d.comb += Cover(u.err)

        # shouldn't be errors in any of the following
        f_past_err = Signal()
        with m.If(u.err):
            m.d.sync += f_past_err.eq(1)
        
        # every legal output
        m.d.comb += Cover(u.source.data == AnyConst(8) & ~f_past_err & u.source.re)
        
        # EOP
        m.d.comb += Cover(u.source.eop & ~f_past_err & u.source.re)
        
        # SOP
        m.d.comb += Cover(u.source.eop & ~f_past_err & u.source.re)
        
        # back to back SOP/EOP
        m.d.comb += Cover(u.source.sop & Past(u.source.eop) & ~f_past_err & u.source.re)
        m.d.comb += Cover(u.source.eop & Past(u.source.sop) & ~f_past_err & u.source.re)
        
        # simultaneous SOP/EOP
        m.d.comb += Cover(u.source.sop & u.source.eop & u.source.re & ~f_past_err)
        
        # multiple EOPs
        f_past_eop = Signal()
        with m.If(u.source.eop & u.source.re):
            m.d.sync += f_past_eop.eq(1)
        m.d.comb += Cover(u.source.eop & f_past_eop & ~f_past_err & u.source.re)
        
        # multiple SOPs
        f_past_sop = Signal()
        with m.If(u.source.sop & u.source.re):
            m.d.sync += f_past_sop.eq(1)
        m.d.comb += Cover(u.source.sop & f_past_sop & ~f_past_err & u.source.re)
        return m

class SLIPTestCase(FHDLTestCase):
    def test_framer_safety(self):
        self.assertFormal(SLIPFramerSafetyProperties(), mode="prove", depth=20, engine="abc pdr")
    
    def test_framer_liveness(self):
        self.assertFormal(SLIPFramerLivenessProperties(), mode="cover", depth=20, engine="smtbmc")
    
    def test_unframer_safety(self):
        self.assertFormal(SLIPUnframerSafetyProperties(), mode="prove", depth=20, engine="abc pdr")
        
    def test_unframer_liveness(self):
        self.assertFormal(SLIPUnframerLivenessProperties(), mode="cover", depth=20, engine="smtbmc")
