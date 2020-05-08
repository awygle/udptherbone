from udptherbone.uart import *
from nmigen.back.pysim import Simulator

def test_loop_sim():
    class Top(Elaboratable):
        def __init__(self):
            self.tx = tx = UARTTx(divisor = 4)
            self.rx = rx = UARTRx(divisor = 4)
        
        def elaborate(self, platform):
            m = Module()
            
            m.submodules.tx = self.tx
            m.submodules.rx = self.rx
            
            m.d.comb += self.rx.rx_i.eq(self.tx.tx_o)
            
            return m
    
    top = Top()
    
    sim = Simulator(top)
    sim.add_clock(1e-6)
    
    import random
    data = bytearray(random.getrandbits(8) for _ in range(16))
    def transmit_proc():
        tx = top.tx
        yield tx.sink.valid.eq(0)
        for _ in range(tx.divisor * 12):
            yield
        i = 0
        while i < len(data):
            b = data[i]
            yield tx.sink.data.eq(b)
            yield tx.sink.valid.eq(1)
            yield
            if (yield tx.sink.ready) == 1:
                i += 1
        for _ in range(tx.divisor * 12):
            yield
            
    def receive_proc():
        rx = top.rx
        yield rx.source.ready.eq(0)
        for _ in range(rx.divisor * 6):
            yield
        yield rx.source.ready.eq(1)
        rec = bytearray()
        while len(rec) < len(data):
            if (yield rx.source.valid):
                rec.append((yield rx.source.data))
            yield
        
        assert data == rec
        
    sim.add_sync_process(transmit_proc)
    sim.add_sync_process(receive_proc)
    
    with sim.write_vcd("uart.vcd", "uart.gtkw"):
        sim.run()
