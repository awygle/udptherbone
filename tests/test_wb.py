
from udptherbone.udptherbone import *

def test_write_sim():
    import random
    from nmigen.back.pysim import Simulator, Passive
    
    class Top(Elaboratable):
        def __init__(self):
            self.dut = UDPTherbone()
            self.done = Signal()
            self.addr = Signal(32)
            self.data = Signal(32)
            pass
        
        def elaborate(self, platform):
            
            m = Module()
            
            m.submodules.dut = dut = self.dut
            
            m.d.comb += dut.interface.ack.eq(1)
            
            addr = self.addr
            data = self.data
            done = self.done
            
            with m.If(dut.interface.stb & dut.interface.cyc):
                m.d.sync += addr.eq(dut.interface.adr)
                m.d.sync += data.eq(dut.interface.dat_w)
                m.d.sync += done.eq(1)
            
            return m
    
    addr = random.getrandbits(32)
    data = random.getrandbits(32)
    pkt = eb_write(addr, data)
    
    top = Top()
    dut = top.dut
    i = top.dut.sink

    sim = Simulator(top)
    sim.add_clock(1e-6)
    
    def transmit_proc():
        yield dut.interface.ack.eq(1)
        yield
        g = 0
        while g < len(pkt):
            c = pkt[g]
            if g == 0:
                yield i.sop.eq(1)
            elif g == len(pkt)-1:
                yield i.eop.eq(1)
            else:
                yield i.sop.eq(0)
                yield i.eop.eq(0)
            yield i.data.eq(c)
            yield i.valid.eq(1)
            yield
            if (yield i.ready) == 1:
                g += 1
        while not (yield top.done):
            yield i.eop.eq(0)
            yield i.valid.eq(0)
            yield
        
        assert (yield top.addr) == addr
        assert (yield top.data) == data
        
    sim.add_sync_process(transmit_proc)
    
    with sim.write_vcd("wb.vcd", "wb.gtkw"):
        sim.run()
