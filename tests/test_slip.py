
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
        #while not (yield f.source.valid) == 0:
        counter = 0
        while counter < 3:
            if (yield f.source.valid) == 1:
                data.append((yield f.source.data))
            if (yield f.source.data) == 0xC0:
                counter += 1
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
        d = "hello, \xdb\xdc world\xc0"
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
        while packets < 1:
        #for g in range(512):
            if (yield f.source.valid) == 1:
                data.append((yield f.source.data))
            if ((yield f.source.eop) == 1) and ((yield f.source.valid == 1)):
                packets += 1
            yield
        
        assert list(map(hex, data)) == list(map(hex, b"hello, \xc0 world"))

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
            if c == ord('h'):
                yield t.i.sop.eq(1)
            elif c == ord(' '):
                yield t.i.eop.eq(1)
            elif c == ord('w'):
                yield t.i.sop.eq(1)
            elif c == ord('\xdb'):
                yield t.i.eop.eq(1)
            elif c == ord('\xdd'):
                yield t.i.sop.eq(1)
            elif c == ord('\xc0'):
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
        while packets < 4:
        #for g in range(512):
            if (yield t.u.source.valid) == 1:
                data.append((yield t.u.source.data))
            if ((yield t.u.source.eop) == 1) and ((yield t.u.source.valid == 1)):
                packets += 1
            yield
        
        #print(list(map(hex, data)))
        #print(list(map(hex, d)))
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
    
    
    d = b"hello, \xdb\xdc\xc0 world\xc0"

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
        counter = 0
        while counter < 2:
            if (yield t.f.source.valid) == 1:
                data.append((yield t.f.source.data))
                if (yield t.f.source.data) == 0xc0:
                    counter += 1
            yield
        
        assert list(map(hex, data)) == list(map(hex, d))

    sim.add_sync_process(transmit_proc)
    sim.add_sync_process(receive_proc)
    
    with sim.write_vcd("slip_reverse.vcd", "slip_reverse.gtkw"):
        sim.run()

def test_unframer_uart_in_loop():
    from nmigen.back.pysim import Simulator, Passive
    from udptherbone.uart import UARTTx, UARTRx
    
    class Top(Elaboratable):
        def __init__(self):
            self.i = i = StreamSource(Layout([("data", 8, DIR_FANOUT)]), name="input", sop=False, eop=False)
    #def __init__(self, divisor, data_bits=8):
            self.tx = tx = UARTTx(divisor=4)
            self.rx = rx = UARTRx(divisor=4)
            self.u = u = SLIPUnframer(rx.source)
            self.o = o = u.source
        
        def elaborate(self, platform):
            m = Module()
            
            m.submodules.tx = self.tx
            m.submodules.rx = self.rx
            m.submodules.u = self.u
            
            m.d.comb += self.rx.rx_i.eq(self.tx.tx_o)
            
            m.d.comb += self.tx.sink.connect(self.i)
            
            return m
    
    top = Top()
    
    sim = Simulator(top)
    sim.add_clock(1e-6)
    
    import random
    data_source = b'hello, \xc0 world'
    #data = bytearray(random.getrandbits(8) for _ in range(16))
    data = slip_encode(data_source)
    
    def transmit_proc():
        tx = top.tx
        i = top.i
        yield i.valid.eq(0)
        for _ in range(tx.divisor * 12):
            yield
        g = 0
        while g < len(data):
            b = data[g]
            yield i.data.eq(b)
            yield i.valid.eq(1)
            yield
            if (yield i.ready) == 1:
                g += 1
        for _ in range(tx.divisor * 12):
            yield
            
    def receive_proc():
        o = top.o
        yield o.ready.eq(0)
        for g in range(0, 16):
            yield
        data = bytearray()
        yield o.ready.eq(1)
        yield
        packets = 0
        while packets < 1:
        #for g in range(512):
            if (yield o.valid) == 1:
                data.append((yield o.data))
            if ((yield o.eop) == 1) and ((yield o.valid == 1)):
                packets += 1
            yield
        
        #print()
        #print(data_source)
        #print(data)
        #print(list(map(hex, data_source)))
        #print(list(map(hex, data)))
        assert list(map(hex, data)) == list(map(hex, b"hello, \xc0 world"))
        
    sim.add_sync_process(transmit_proc)
    sim.add_sync_process(receive_proc)
    
    with sim.write_vcd("uart_in_loop.vcd", "uart_in_loop.gtkw"):
        sim.run()

def test_loopback_uart_in_loop():
    from nmigen.back.pysim import Simulator, Passive
    from udptherbone.uart import UARTTx, UARTRx
    
    class Top(Elaboratable):
        def __init__(self):
            self.i = i = StreamSource(Layout([("data", 8, DIR_FANOUT)]), name="input", sop=False, eop=False)
            self.tx1 = tx1 = UARTTx(divisor=868)
            self.rx = rx = UARTRx(divisor=868)
            self.u = u = SLIPUnframer(rx.source)
            self.f = f = SLIPFramer(u.source)
            self.tx = tx = UARTTx(divisor=868)
            self.rx1 = rx1 = UARTRx(divisor=868)
            self.o = o = rx1.source
        
        def elaborate(self, platform):
            m = Module()
            
            m.submodules.tx = self.tx
            m.submodules.rx = self.rx
            m.submodules.tx1 = self.tx1
            m.submodules.rx1 = self.rx1
            m.submodules.u = self.u
            m.submodules.f = self.f
            
            m.d.comb += self.rx.rx_i.eq(self.tx1.tx_o)
            
            m.d.comb += self.tx1.sink.connect(self.i)
            
            m.d.comb += self.tx.sink.connect(self.f.source)
            
            m.d.comb += self.rx1.rx_i.eq(self.tx.tx_o)
            
            return m
    
    top = Top()
    
    sim = Simulator(top)
    sim.add_clock(1e-6)
    
    import random
    #data_source = b'hello, \xc0 world'
    num_pkts = 4
    pkt_lens = [random.getrandbits(4) for _ in range(4)]
    data_source = bytearray()
    for l in pkt_lens:
        if l == 0:
            num_pkts -= 1
            continue
        pkt = bytearray(random.getrandbits(8) for _ in range(l))
        pkt = slip_encode(pkt)
        data_source += pkt
    
    def transmit_proc():
        tx = top.tx
        i = top.i
        yield i.valid.eq(0)
        for _ in range(tx.divisor * 12):
            yield
        g = 0
        while g < len(data_source):
            b = data_source[g]
            yield i.data.eq(b)
            yield i.valid.eq(1)
            yield
            if (yield i.ready) == 1:
                g += 1
        for _ in range(tx.divisor * 12):
            yield
            
    def receive_proc():
        o = top.o
        yield o.ready.eq(0)
        for g in range(0, 16):
            yield
        data = bytearray()
        yield o.ready.eq(1)
        yield
        packets = 0
        while packets < num_pkts:
        #for g in range(512):
            if (yield o.valid) == 1:
                data.append((yield o.data))
            if ((yield o.data) == 0xc0) and ((yield o.valid == 1)):
                packets += 1
            yield
        
        assert list(map(hex, data)) == list(map(hex, data_source))
        
    sim.add_sync_process(transmit_proc)
    sim.add_sync_process(receive_proc)
    
    with sim.write_vcd("uart_in_loop.vcd", "uart_in_loop.gtkw"):
        sim.run()

