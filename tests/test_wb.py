
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
            
            with m.If(dut.interface.stb & dut.interface.cyc & dut.interface.we):
                m.d.sync += addr.eq(dut.interface.adr)
                m.d.sync += data.eq(dut.interface.dat_w)
                m.d.sync += done.eq(1)
            
            return m
    
    addr = random.getrandbits(32)
    data = random.getrandbits(32)
    pkt = eb_write(addr, [data])
    
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

def test_write_multi_sim():
    import random
    from nmigen.back.pysim import Simulator, Passive
    
    class Top(Elaboratable):
        def __init__(self):
            self.dut = UDPTherbone()
            self.done = Signal(2)
            self.addrs = [Signal(32), Signal(32)]
            self.datas = [Signal(32), Signal(32)]
            pass
        
        def elaborate(self, platform):
            
            m = Module()
            
            m.submodules.dut = dut = self.dut
            
            m.d.comb += dut.interface.ack.eq(1)
            
            #addr = Mux(self.done[0], self.addrs[0], self.addrs[1])
            #data = Mux(self.done[0], self.datas[0], self.datas[1])
            #addr = self.addrs[self.done]
            #data = self.datas[self.done]
            
            addrs = self.addrs
            datas = self.datas
            done = self.done
            
            with m.If(dut.interface.stb & dut.interface.cyc & dut.interface.we):
                with m.Switch(done):
                    with m.Case(0):
                        m.d.sync += addrs[0].eq(dut.interface.adr)
                        m.d.sync += datas[0].eq(dut.interface.dat_w)
                    with m.Case(1):
                        m.d.sync += addrs[1].eq(dut.interface.adr)
                        m.d.sync += datas[1].eq(dut.interface.dat_w)
                m.d.sync += done.eq(done + 1)
            
            return m
    
    addr = random.getrandbits(32)
    data0 = random.getrandbits(32)
    data1 = random.getrandbits(32)
    pkt = eb_write(addr, [data0, data1])
    
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
        while (yield top.done) < 2:
            yield i.eop.eq(0)
            yield i.valid.eq(0)
            yield
        
        assert (yield top.addrs[0]) == addr
        assert (yield top.addrs[1]) == addr +  1
        assert (yield top.datas[0]) == data0
        assert (yield top.datas[1]) == data1
        
    sim.add_sync_process(transmit_proc)
    
    with sim.write_vcd("wb_multi.vcd", "wb_multi.gtkw"):
        sim.run()

def test_read_noret_sim():
    import random
    from nmigen.back.pysim import Simulator, Passive
    
    class Top(Elaboratable):
        def __init__(self):
            self.dut = UDPTherbone()
            self.done = Signal()
            self.addr = Signal(32)
            pass
        
        def elaborate(self, platform):
            
            m = Module()
            
            m.submodules.dut = dut = self.dut
            
            m.d.comb += dut.interface.ack.eq(1)
            
            addr = self.addr
            done = self.done
            
            with m.If(dut.interface.stb & dut.interface.cyc & ~dut.interface.we):
                m.d.sync += addr.eq(dut.interface.adr)
                m.d.sync += done.eq(1)
            
            return m
    
    addr = random.getrandbits(32)
    #addr = 0xDEADBEEF
    pkt = eb_read(addr)
    
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
        yield
        
        assert (yield top.addr) == addr
        
    sim.add_sync_process(transmit_proc)
    
    with sim.write_vcd("wb_rd_noret.vcd", "wb_rd_noret.gtkw"):
        sim.run()

def test_read_sim():
    import random
    from nmigen.back.pysim import Simulator, Passive
    
    class Top(Elaboratable):
        def __init__(self, data):
            self.dut = UDPTherbone()
            self.done = Signal()
            self.addr = Signal(32)
            self.data = data
            pass
        
        def elaborate(self, platform):
            
            m = Module()
            
            m.submodules.dut = dut = self.dut
            
            addr = self.addr
            done = self.done
            
            m.d.sync += dut.interface.ack.eq(0)
            
            with m.If(dut.interface.stb & dut.interface.cyc & ~dut.interface.we):
                m.d.sync += addr.eq(dut.interface.adr)
                m.d.sync += dut.interface.dat_r.eq(self.data)
                m.d.sync += dut.interface.ack.eq(1)
                m.d.sync += done.eq(1)
            
            return m
    
    addr = random.getrandbits(32)
    print()
    print(hex(addr))
    pkt = eb_read(addr)
    
    data = random.getrandbits(32)
    #data = 0xBABECAFE
    print(hex(data))
    top = Top(data)
    dut = top.dut
    i = top.dut.sink
    o = top.dut.source

    sim = Simulator(top)
    sim.add_clock(1e-6)
    
    def transmit_proc():
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
        yield
        
        assert (yield top.addr) == addr
        
    def receive_proc():
        import struct
        for g in range(0, 16):
            yield
        recv = bytearray()
        yield o.ready.eq(1)
        yield
        while not (yield o.eop):
            if (yield o.valid) == 1:
                recv.append((yield o.data))
            yield
        if (yield o.valid) == 1:
            recv.append((yield o.data))
        yield
        
        assert struct.unpack("!L", recv[8:12])[0] == 0xdeadbeef
        assert struct.unpack("!L", recv[12:16])[0] == data
        
    sim.add_sync_process(transmit_proc)
    sim.add_sync_process(receive_proc)
    
    with sim.write_vcd("wb_rd.vcd", "wb_rd.gtkw"):
        sim.run()

