
from udptherbone.udp import *

def test_packetizer_sim():
    from nmigen.back.pysim import Simulator, Passive
    
    input = i = StreamSource(Layout([("data", 8, DIR_FANOUT)]))
    packetizer = p = UDPPacketizer(input, ipaddress.IPv4Address("127.0.0.1"), ipaddress.IPv4Address("127.0.0.2"), source_port = 2574, dest_port = 7777)

    sim = Simulator(packetizer)
    sim.add_clock(1e-6)
    
    def transmit_proc():
        yield
        for c in "hello world":
            if c == "h":
                yield i.sop.eq(1)
            elif c == "d":
                yield i.eop.eq(1)
            else:
                yield i.sop.eq(0)
                yield i.eop.eq(0)
            yield i.data.eq(ord(c))
            yield i.valid.eq(1)
            yield
        for g in range(0, 16):
            yield i.eop.eq(0)
            yield i.valid.eq(0)
            yield
    
    def receive_proc():
        for g in range(0, 16):
            yield
        data = []
        #for g in range(0, 128):
        yield p.source.ready.eq(1)
        yield
        while not (yield p.source.valid) == 0:
            if (yield p.source.valid) == 1:
                data.append((yield p.source.data))
            yield
        
        r = IP(data)
        
        assert r.load == b"hello world"
        
        i = IP(data)
        del i.chksum
        i = IP(raw(i))
        assert r.chksum == i.chksum

    sim.add_sync_process(transmit_proc)
    sim.add_sync_process(receive_proc)
    
    with sim.write_vcd("udp_pa.vcd", "udp_pa.gtkw"):
        sim.run()
        
def test_depacketizer_sim():
    from nmigen.back.pysim import Simulator, Passive
    
    input = i = StreamSource(Layout([("data", 8, DIR_FANOUT)]))
    depacketizer = d = UDPDepacketizer(input, ipaddress.IPv4Address("127.0.0.1"), port = 2574)

    sim = Simulator(depacketizer)
    sim.add_clock(1e-6)
    
    def de_input_proc():
        yield
        for b in b'E\x00\x00\x13\x00\x00@\x00\xff\x11}\xd6\x7f\x00\x00\x02\x7f\x00\x00\x01\x1ea\n\x0e\x00\x13\xc40hello world':
            if b == 'E':
                yield i.sop.eq(1)
            elif b == 'd':
                yield i.eop.eq(1)
            else:
                yield i.sop.eq(1)
                yield i.eop.eq(1)
            yield i.data.eq(b)
            yield i.valid.eq(1)
            yield
        for g in range(0, 16):
            yield i.sop.eq(0)
            yield i.eop.eq(0)
            yield i.valid.eq(0)
            yield
        
    
    def de_output_proc():
        data = []
        yield
        yield d.source.ready.eq(1)
        yield
        #for g in range(0, 512):
        #    yield
        while (yield d.source.valid) == 0:
            yield
        while not (yield d.source.valid) == 0:
            if (yield d.source.valid) == 1:
                data.append((yield d.source.data))
            yield
        
        assert "".join(list(map(chr, data))) == "hello world"
    
    sim.add_sync_process(de_input_proc)
    sim.add_sync_process(de_output_proc)
    
    with sim.write_vcd("udp_de.vcd", "udp_de.gtkw"):
        sim.run()

def test_loopback_sim():
    from nmigen.back.pysim import Simulator, Passive
    from ipaddress import IPv4Address
    
    class Top(Elaboratable):
        def __init__(self):
            host_addr = IPv4Address("127.0.0.1")
            dest_addr = IPv4Address("127.0.0.2")
            host_port = 2574
            dest_port = 7777
            self.i = i = StreamSource(Layout([("data", 8, DIR_FANOUT)]), name="input", sop=True, eop=True)
            self.p = p = UDPPacketizer(i, host_addr, dest_addr, source_port = host_port, dest_port = dest_port)
            self.d = d = UDPDepacketizer(p.source, dest_addr, port = dest_port)
            self.o = o = d.source
        
        def elaborate(self, platform):
            m = Module()
            
            m.submodules.p = self.p
            m.submodules.d = self.d
            
            return m
    
    t = Top()

    sim = Simulator(t)
    sim.add_clock(1e-6)
    
    def transmit_proc():
        yield
        for c in "hello world":
            if c == "h":
                yield t.i.sop.eq(1)
            elif c == "d":
                yield t.i.eop.eq(1)
            else:
                yield t.i.sop.eq(0)
                yield t.i.eop.eq(0)
            yield t.i.data.eq(ord(c))
            yield t.i.valid.eq(1)
            yield
        for g in range(0, 16):
            yield t.i.eop.eq(0)
            yield t.i.valid.eq(0)
            yield
    
    def receive_proc():
        data = []
        yield
        yield t.d.source.ready.eq(1)
        yield
        #for g in range(0, 512):
        #    yield
        while (yield t.d.source.valid) == 0:
            yield
        while not (yield t.d.source.valid) == 0:
            if (yield t.d.source.valid) == 1:
                data.append((yield t.d.source.data))
            yield
        
        assert "".join(list(map(chr, data))) == "hello world"

    sim.add_sync_process(transmit_proc)
    sim.add_sync_process(receive_proc)
    
    with sim.write_vcd("udp_loop.vcd", "udp_loop.gtkw"):
        sim.run()
        
