
from udptherbone.slip import *

def test_framer_sim():
    from nmigen.back.pysim import Simulator, Passive
    
    input = i = StreamSource(Layout([("data", 8, DIR_FANOUT)]), name="input")
    framer = f = SLIPFramer(input)

    sim = Simulator(framer)
    sim.add_clock(1e-6)
    
    def transmit_proc():
        yield
        g = 0
        d = "hello world\xdb"
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
            yield
        
        assert list(map(hex, data)) == list(map(hex, b"hello \xc0world\xdb\xdd\xc0"))

    sim.add_sync_process(transmit_proc)
    sim.add_sync_process(receive_proc)
    
    with sim.write_vcd("slip.vcd", "slip.gtkw"):
        sim.run()


def test_unframer_sim():
    from nmigen.back.pysim import Simulator, Passive
    
    input = i = StreamSource(Layout([("data", 8, DIR_FANOUT)]), name="input", sop=False, eop=False)
    framer = f = SLIPUnframer(input)

    sim = Simulator(framer)
    sim.add_clock(1e-6)
    
    def transmit_proc():
        yield
        g = 0
        d = "hello \xdb\xdd\xdb\xdc\xc0\xc0world\xdb\xdd\xc0"
        m = len(d)
        while g < m:
            c = d[g]
            yield i.data.eq(ord(c))
            yield i.valid.eq(1)
            yield
            if (yield f.sink.ready) == 1:
                g += 1
        for g in range(0, 16):
            yield i.valid.eq(0)
            yield
    
    def receive_proc():
        yield f.source.ready.eq(0)
        for g in range(0, 16):
            yield
        data = []
        yield f.source.ready.eq(1)
        yield
        packets = 0
        while packets < 2:
        #for g in range(512):
            if (yield f.source.valid) == 1:
                data.append((yield f.source.data))
            if ((yield f.source.eop) == 1) and ((yield f.source.valid == 1)):
                packets += 1
            yield
        
        assert list(map(hex, data)) == list(map(hex, b"hello \xdb\xc0world\xdb"))

    sim.add_sync_process(transmit_proc)
    sim.add_sync_process(receive_proc)
    
    with sim.write_vcd("slip_unframe.vcd", "slip_unframe.gtkw"):
        sim.run()


def test_loopback_sim():
    from nmigen.back.pysim import Simulator, Passive
    
    class Top(Elaboratable):
        def __init__(self):
            self.i = i = StreamSource(Layout([("data", 8, DIR_FANOUT)]), name="input", sop=True, eop=True)
            self.f = f = SLIPFramer(i)
            self.u = u = SLIPUnframer(f.source)
            self.o = o = u.source
        
        def elaborate(self, platform):
            m = Module()
            
            m.submodules.f = self.f
            m.submodules.u = self.u
            
            return m
    
    
    d = b"hello \xdb\xddworld\xdb\xdd\xc0"

    t = Top()
    sim = Simulator(t)
    sim.add_clock(1e-6)
    
    def transmit_proc():
        yield
        g = 0
        m = len(d)
        while g < m:
            c = d[g]
            yield t.i.data.eq(c)
            yield t.i.sop.eq(0)
            yield t.i.eop.eq(0)
            if c == 'h':
                yield t.i.sop.eq(1)
            elif c == ' ':
                yield t.i.eop.eq(1)
            elif c == 'w':
                yield t.i.sop.eq(1)
            elif c == '\xdb':
                yield t.i.eop.eq(1)
            yield t.i.valid.eq(1)
            yield
            if (yield t.f.sink.ready) == 1:
                g += 1
        for g in range(0, 16):
            yield t.i.valid.eq(0)
            yield
    
    def receive_proc():
        yield t.u.source.ready.eq(0)
        for g in range(0, 16):
            yield
        data = []
        yield t.u.source.ready.eq(1)
        yield
        packets = 0
        #while packets < 2:
        for g in range(512):
            if (yield t.u.source.valid) == 1:
                data.append((yield t.u.source.data))
            if ((yield t.u.source.eop) == 1) and ((yield t.u.source.valid == 1)):
                packets += 1
            yield
        
        assert list(map(hex, data)) == list(map(hex, d))

    sim.add_sync_process(transmit_proc)
    sim.add_sync_process(receive_proc)
    
    with sim.write_vcd("slip_loopback.vcd", "slip_loopback.gtkw"):
        sim.run()

def test_reverse_loopback_sim():
    from nmigen.back.pysim import Simulator, Passive
    
    class Bottom(Elaboratable):
        def __init__(self):
            self.i = i = StreamSource(Layout([("data", 8, DIR_FANOUT)]), name="input", sop=False, eop=False)
            self.u = u = SLIPUnframer(i)
            self.f = f = SLIPFramer(u.source)
            self.o = o = f.source
        
        def elaborate(self, platform):
            m = Module()
            
            m.submodules.f = self.f
            m.submodules.u = self.u
            
            return m
    
    
    d = b"hello \xdb\xddworld\xdb\xdd\xc0"

    t = Bottom()
    sim = Simulator(t)
    sim.add_clock(1e-6)
    
    def transmit_proc():
        yield
        g = 0
        m = len(d)
        while g < m:
            c = d[g]
            yield t.i.data.eq(c)
            yield t.i.valid.eq(1)
            yield
            if (yield t.u.sink.ready) == 1:
                g += 1
        for g in range(0, 16):
            yield t.i.valid.eq(0)
            yield

    def receive_proc():
        yield t.f.source.ready.eq(0)
        for g in range(0, 16):
            yield
        data = []
        yield t.f.source.ready.eq(1)
        yield
        #for g in range(0, 128):
        while not (yield t.f.source.valid) == 0:
            if (yield t.f.source.valid) == 1:
                data.append((yield t.f.source.data))
            yield
        
        assert list(map(hex, data)) == list(map(hex, d))

    sim.add_sync_process(transmit_proc)
    sim.add_sync_process(receive_proc)
    
    with sim.write_vcd("slip_reverse.vcd", "slip_reverse.gtkw"):
        sim.run()

