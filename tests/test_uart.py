from udptherbone.uart import *

def test_loop_sim():
    uart = UART(divisor=4)
    ports = [
        uart.tx_o, uart.rx_i,
        uart.tx.data, uart.tx.valid, uart.tx.ready,
        uart.rx.data, uart.rx.valid, uart.rx_err, uart.rx_ovf, uart.rx.ready
    ]

    from nmigen.back.pysim import Simulator, Passive

    sim = Simulator(uart)
    sim.add_clock(1e-6)

    import random
    data = bytearray(random.getrandbits(8) for _ in range(16))
    def transmit_proc():
        yield uart.tx.valid.eq(0)
        for _ in range(uart.divisor * 12):
            yield
        for i in range(len(data)):
            b = data[i]
            yield uart.tx.data.eq(b)
            yield uart.tx.valid.eq(1)
            if (yield uart.tx.ready.eq(1)):
                i += 1
            yield
        for _ in range(uart.divisor * 12):
            yield
    
    def loopback_proc():
        yield Passive()
        while True:
            yield uart.rx_i.eq((yield uart.tx_o))
            yield
            
    def receive_proc():
        yield uart.rx.ready.eq(0)
        for _ in range(uart.divisor * 6):
            yield
        yield uart.rx.ready.eq(1)
        rec = bytearray()
        while len(rec) < len(data):
            if (yield uart.rx.valid):
                rec.append((yield uart.rx.data))
            yield
        
        print(list(map(hex, data)))
        print(list(map(hex, rec)))
        #assert rec == data
    sim.add_sync_process(transmit_proc)
    sim.add_sync_process(receive_proc)
    sim.add_sync_process(loopback_proc)

    with sim.write_vcd("uart.vcd", "uart.gtkw"):
        sim.run()

