
from udptherbone.udptherbone import *
from scapy.all import *

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
    pkt = eb_read([addr])
    
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
    pkt = eb_read([addr])
    
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

def test_read_multi_sim():
    import random
    from nmigen.back.pysim import Simulator, Passive
    
    class Top(Elaboratable):
        def __init__(self, datas):
            self.dut = UDPTherbone()
            self.read = Signal(range(len(datas)))
            self.addr = Signal(32)
            self.datas = datas
            pass
        
        def elaborate(self, platform):
            
            m = Module()
            
            m.submodules.dut = dut = self.dut
            
            addr = self.addr
            
            m.d.sync += dut.interface.ack.eq(0)
            
            with m.If(dut.interface.stb & dut.interface.cyc & ~dut.interface.we):
                m.d.sync += addr.eq(dut.interface.adr)
                with m.Switch(self.read):
                    for i in range(len(datas)):
                        with m.Case(i):
                            m.d.sync += dut.interface.dat_r.eq(self.datas[i])
                m.d.sync += dut.interface.ack.eq(1)
                m.d.sync += self.read.eq(self.read + 1)
            
            return m
        
    count = 5
    
    addrs = [random.getrandbits(32) for _ in range(count)]
    print()
    print(list(map(hex, addrs)))
    pkts = [eb_read(addrs[i]) for i in range(count)]
    
    datas = [random.getrandbits(32) for _ in range(count)]
    print(list(map(hex, datas)))
    top = Top(datas)
    dut = top.dut
    i = top.dut.sink
    o = top.dut.source

    sim = Simulator(top)
    sim.add_clock(1e-6)
    
    def transmit_proc():
        yield
        for pkt in pkts:
            g = 0
            while g < len(pkt):
                c = pkt[g]
                yield i.sop.eq(0)
                yield i.eop.eq(0)
                if g == 0:
                    yield i.sop.eq(1)
                if g == len(pkt)-1:
                    yield i.eop.eq(1)
                yield i.data.eq(c)
                yield i.valid.eq(1)
                yield
                if (yield i.ready) == 1:
                    g += 1
            print("sent pkt")
        
    def receive_proc():
        import struct
        for g in range(0, 16):
            yield
        recv = bytearray()
        yield o.ready.eq(1)
        yield
        recv = [bytearray() for _ in range(count)]
        for g in range(count):
            while not (yield o.sop):
                yield
            while not (yield o.eop):
                if (yield o.valid) == 1:
                    recv[g].append((yield o.data))
                yield
            if (yield o.valid) == 1:
                recv[g].append((yield o.data))
        
        for g in range(count):
            print(list(map(hex, recv[g])))
            assert struct.unpack("!L", recv[g][8:12])[0] == 0xdeadbeef
            assert struct.unpack("!L", recv[g][12:16])[0] == datas[g]
        
    sim.add_sync_process(transmit_proc)
    sim.add_sync_process(receive_proc)
    
    with sim.write_vcd("wb_rd_multi.vcd", "wb_rd_multi.gtkw"):
        sim.run()

def test_full_sim():
    import random
    from nmigen.back.pysim import Simulator, Passive
    from ipaddress import IPv4Address
    from udptherbone.slip import SLIPUnframer, SLIPFramer, slip_encode, slip_decode
    from udptherbone.uart import UARTTx, UARTRx
    
    class Top(Elaboratable):
        def __init__(self):
            self.addr = Signal(32)
            self.data = Signal(32, reset=0xCAFEBABE)
            
            host_addr = IPv4Address("127.0.0.1")
            host_port = 2574
            dest_addr = IPv4Address("127.0.0.2")
            dest_port = 7777
            self.i = i = StreamSource(Layout([("data", 8, DIR_FANOUT)]), name="input", sop=False, eop=False)
            self.tx1 = tx1 = UARTTx(divisor = 4)
            self.rx = rx = UARTRx(divisor = 4)
            self.u = u = SLIPUnframer(rx.source)
            self.d = d = UDPDepacketizer(u.source, dest_addr, port = dest_port)
            self.wb = wb = UDPTherbone()
            self.p = p = UDPPacketizer(wb.source, dest_addr, host_addr, source_port = dest_port, dest_port = host_port)
            self.f = f = SLIPFramer(p.source)
            self.tx = tx = UARTTx(divisor = 4)
            self.rx1 = rx1 = UARTRx(divisor = 4)
            self.o = o = rx1.source
        
        def elaborate(self, platform):
            
            m = Module()
            
            m.submodules.tx1 = self.tx1
            m.submodules.rx = self.rx
            m.submodules.u = self.u
            m.submodules.d = self.d
            m.submodules.wb = self.wb
            m.submodules.p = self.p
            m.submodules.f = self.f
            m.submodules.tx = self.tx
            m.submodules.rx1 = self.rx1
            
            m.d.comb += self.rx.rx_i.eq(self.tx1.tx_o)
            m.d.comb += self.rx1.rx_i.eq(self.tx.tx_o)
            
            m.d.comb += self.tx1.sink.connect(self.i)
            m.d.comb += self.tx.sink.connect(self.f.source)
            
            m.d.comb += self.wb.sink.connect(self.d.source)
            
            dut = self.wb
            
            addr = self.addr
            
            m.d.sync += dut.interface.ack.eq(0)
            
            with m.If(dut.interface.stb & dut.interface.cyc & dut.interface.we):
                m.d.sync += addr.eq(dut.interface.adr)
                m.d.sync += self.data.eq(dut.interface.dat_w)
                m.d.sync += dut.interface.ack.eq(1)
            
            with m.If(dut.interface.stb & dut.interface.cyc & ~dut.interface.we):
                m.d.sync += addr.eq(dut.interface.adr)
                m.d.sync += dut.interface.dat_r.eq(self.data)
                m.d.sync += dut.interface.ack.eq(1)
            
            return m
    
    addr = random.getrandbits(32)
    data = random.getrandbits(32)
    w_pkt = slip_encode(raw(IP(src='127.0.0.1', dst='127.0.0.2', flags='DF')/UDP(dport=7777, sport=2574)/eb_write(addr, [data])))
    r_pkt = slip_encode(raw(IP(src='127.0.0.1', dst='127.0.0.2', flags='DF')/UDP(dport=7777, sport=2574)/eb_read([addr])))
    
    top = Top()
    i = top.i
    o = top.o
    
    read = Signal()

    sim = Simulator(top)
    sim.add_clock(1e-6)
    
    def transmit_proc():
        yield
        g = 0
        while g < len(w_pkt):
            c = w_pkt[g]
            yield i.data.eq(c)
            yield i.valid.eq(1)
            yield
            if (yield i.ready) == 1:
                g += 1
        yield
        
        g = 0
        while g < len(r_pkt):
            c = r_pkt[g]
            yield i.data.eq(c)
            yield i.valid.eq(1)
            yield
            if (yield i.ready) == 1:
                g += 1
        yield
        
    def receive_proc():
        import struct
        for g in range(0, 16):
            yield
        recv = bytearray()
        yield o.ready.eq(1)
        yield
        while True:
            if (yield o.valid) == 1:
                recv.append((yield o.data))
                if (yield o.data) == 0xc0:
                    break
            yield
        yield
        
        print(list(map(hex, recv)))
        i = IP(slip_decode(recv))
        i.show()
        print(list(map(hex, i.load)))
        assert struct.unpack("!L", i.load[8:12])[0] == 0xdeadbeef
        assert struct.unpack("!L", i.load[12:16])[0] == data
        
    sim.add_sync_process(transmit_proc)
    sim.add_sync_process(receive_proc)
    
    with sim.write_vcd("wb_full.vcd", "wb_full.gtkw"):
        sim.run()

