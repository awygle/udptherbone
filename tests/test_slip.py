
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
            print("writing " + str(hex((yield f.sink.data))) + \
                ", ready is " + str((yield f.sink.ready)) + \
                ", valid is " + str((yield f.sink.valid)))
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
                print("reading " + str(hex((yield f.source.data))) + \
                    ", ready is " + str((yield f.source.ready)) + \
                    ", valid is " + str((yield f.source.valid)))
            if ((yield f.source.eop) == 1) and ((yield f.source.valid == 1)):
                packets += 1
            yield
        
        print(list(map(hex, data)))
        print(list(map(chr, data)))
        
        assert list(map(hex, data)) == list(map(hex, b"hello \xdb\xc0world\xdb"))

    sim.add_sync_process(transmit_proc)
    sim.add_sync_process(receive_proc)
    
    with sim.write_vcd("slip_unframe.vcd", "slip_unframe.gtkw"):
        sim.run()

