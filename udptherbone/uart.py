from nmigen import *
from .stream import *

import enum

# TODO support parity, stop bits
class UARTParity(enum.Enum):
    NONE = 0
    ODD  = 1
    EVEN = 2

class UART(Elaboratable):
    """
    Parameters
    ----------
    divisor : int
        Set to ``round(clk-rate / baud-rate)``.
        E.g. ``12e6 / 115200`` = ``104``.
    """
    def __init__(self, divisor, data_bits=8):
        assert divisor >= 4

        self.data_bits = data_bits
        self.divisor   = divisor

        self.tx_o    = Signal()
        self.rx_i    = Signal()

        self.layout = Layout([("data", data_bits)])
        self.tx = StreamSink(self.layout, False, False, name="tx")
        self.rx = StreamSource(self.layout, False, False, name="rx")
        
        self.rx_err  = Signal()
        self.rx_ovf  = Signal()

    def elaborate(self, platform):
        m = Module()
        
        tx_phase = Signal(range(self.divisor))
        tx_shreg = Signal(1 + self.data_bits + 1, reset=-1)
        tx_count = Signal(range(len(tx_shreg) + 1))

        m.d.comb += self.tx_o.eq(tx_shreg[0])
        with m.If(tx_count == 0):
            m.d.comb += self.tx.ready.eq(1)
            with m.If(self.tx.valid):
                m.d.sync += [
                    tx_shreg.eq(Cat(C(0, 1), self.tx.data, C(1, 1))),
                    tx_count.eq(len(tx_shreg)),
                    tx_phase.eq(self.divisor - 1),
                ]
        with m.Else():
            with m.If(tx_phase != 0):
                m.d.sync += tx_phase.eq(tx_phase - 1)
            with m.Else():
                m.d.sync += [
                    tx_shreg.eq(Cat(tx_shreg[1:], C(1, 1))),
                    tx_count.eq(tx_count - 1),
                    tx_phase.eq(self.divisor - 1),
                ]

        rx_phase = Signal(range(self.divisor))
        rx_shreg = Signal(1 + self.data_bits + 1, reset=-1)
        rx_count = Signal(range(len(rx_shreg) + 1))

        m.d.comb += self.rx.data.eq(rx_shreg[1:-1])
        with m.If(rx_count == 0):
            m.d.comb += self.rx_err.eq(~(~rx_shreg[0] & rx_shreg[-1]))
            with m.If(~self.rx_i):
                with m.If(~self.rx.valid):
                    m.d.sync += [
                        self.rx.valid.eq(0),
                        self.rx_ovf.eq(0),
                        rx_count.eq(len(rx_shreg)),
                        rx_phase.eq(self.divisor // 2),
                    ]
                with m.Else():
                    m.d.sync += self.rx_ovf.eq(1)
        with m.Else():
            with m.If(rx_phase != 0):
                m.d.sync += rx_phase.eq(rx_phase - 1)
            with m.Else():
                m.d.sync += [
                    rx_shreg.eq(Cat(rx_shreg[1:], self.rx_i)),
                    rx_count.eq(rx_count - 1),
                    rx_phase.eq(self.divisor - 1),
                ]
                with m.If(rx_count == 1):
                    m.d.sync += self.rx.valid.eq(1)
                    
        with m.If(self.rx.valid & self.rx.ready):
            m.d.sync += self.rx.valid.eq(0)

        return m


if __name__ == "__main__":
    uart = UART(divisor=4)
    ports = [
        uart.tx_o, uart.rx_i,
        uart.tx.data, uart.tx.valid, uart.tx.ready,
        uart.rx.data, uart.rx.valid, uart.rx_err, uart.rx_ovf, uart.rx.ready
    ]

    import argparse

    parser = argparse.ArgumentParser()
    p_action = parser.add_subparsers(dest="action")
    p_action.add_parser("simulate")
    p_action.add_parser("generate")

    args = parser.parse_args()
    if args.action == "simulate":
        from nmigen.back.pysim import Simulator, Passive

        sim = Simulator(uart)
        sim.add_clock(1e-6)

        def loopback_proc():
            yield Passive()
            while True:
                yield uart.rx_i.eq((yield uart.tx_o))
                yield
        sim.add_sync_process(loopback_proc)

        def transmit_proc():
            for i in range(0, 4):
                #assert (yield uart.tx.ready)
                #assert not (yield uart.rx.valid)

                yield uart.tx.data.eq(ord('A'))
                yield uart.tx.valid.eq(1)
                yield
                #yield uart.tx.valid.eq(0)
                yield
                #assert not (yield uart.tx.ready)

                for _ in range(uart.divisor * 12): yield

                #assert (yield uart.tx.ready)
                #assert (yield uart.rx.valid)
                #assert not (yield uart.rx_err)
                #assert (yield uart.rx.data) == ord('A')

                yield uart.rx.ready.eq(1)
                yield
        sim.add_sync_process(transmit_proc)

        with sim.write_vcd("uart.vcd", "uart.gtkw"):
            sim.run()

    if args.action == "generate":
        from nmigen.back import verilog

        print(verilog.convert(uart, ports=ports))
        
    if args.action == "program":
        platform = VersaECP5Platform()
        platform.build(uart, do_program=True)
    

