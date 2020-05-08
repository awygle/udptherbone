from nmigen import *
from .stream import *

import enum

# TODO support parity, stop bits
class UARTParity(enum.Enum):
    NONE = 0
    ODD  = 1
    EVEN = 2

class UARTTx(Elaboratable):
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

        self.layout = Layout([("data", data_bits)])
        self.sink = StreamSink(self.layout, False, False, name="tx_sink")
        
    def elaborate(self, platform):
        m = Module()
        
        tx_phase = Signal(range(self.divisor))
        tx_shreg = Signal(1 + self.data_bits + 1, reset=-1)
        tx_count = Signal(range(len(tx_shreg)))
        
        # could wrap this into tx.ready
        tx_active = Signal()
        
        m.d.comb += self.sink.ready.eq(~tx_active)
        m.d.comb += self.tx_o.eq(tx_shreg[0])
        
        # could drop this since tx.we implies we're not active
        with m.If(~tx_active):
            with m.If(self.sink.we):
                # start bit 0, data, stop bit 1
                m.d.sync += tx_shreg.eq(Cat(C(0, 1), self.sink.data, C(1, 1)))
                # reset phase counter - update every divisor clocks
                m.d.sync += tx_phase.eq(self.divisor - 1)
                # reset bit counter
                m.d.sync += tx_count.eq(len(tx_shreg) - 1)
                m.d.sync += tx_active.eq(1)
        with m.If(tx_active):
            m.d.sync += tx_phase.eq(tx_phase - 1)
            with m.If(tx_phase == 0):
                # advance shreg
                m.d.sync += tx_shreg.eq(Cat(tx_shreg[1:], C(1, 1)))
                # decrease count
                m.d.sync += tx_count.eq(tx_count - 1)
                # reset phase (for non-Po2 divisors)
                m.d.sync += tx_phase.eq(self.divisor - 1)
                with m.If(tx_count == 0):
                    # ready for more inputs
                    m.d.sync += tx_active.eq(0)
        
        return m
                
class UARTRx(Elaboratable):
    """
    Parameters
    ----------
    divisor : int
        Set to ``round(clk-rate / baud-rate)``.
        E.g. ``12e6 / 115200`` = ``104``.
        
    NOTE rx_i must be synchronized externally
    """
    def __init__(self, divisor, data_bits=8):
        assert divisor >= 4

        self.data_bits = data_bits
        self.divisor   = divisor

        self.rx_i    = Signal()

        self.layout = Layout([("data", data_bits)])
        self.source = StreamSource(self.layout, False, False, name="rx")
        
    def elaborate(self, platform):
        m = Module()
        
        rx_phase = Signal(range(self.divisor))
        rx_shreg = Signal(1 + self.data_bits + 1, reset=-1)
        rx_count = Signal(range(len(rx_shreg)))
        
        m.d.sync += self.source.valid.eq(0) # overridden in some states
        
        m.d.comb += self.source.data.eq(rx_shreg[1:-1])

        with m.FSM():
            with m.State("IDLE"):
                with m.If(~self.rx_i):
                    m.d.sync += rx_count.eq(len(rx_shreg) - 1)
                    m.d.sync += rx_phase.eq(self.divisor // 2) # sample mid-bit
                    m.next = "SAMPLING"
            with m.State("SAMPLING"):
                m.d.sync += rx_phase.eq(rx_phase - 1)
                with m.If(rx_phase == 0):
                    # sample
                    m.d.sync += rx_shreg.eq(Cat(rx_shreg[1:], self.rx_i))
                    # decrease count
                    m.d.sync += rx_count.eq(rx_count - 1)
                    # reset phase (for non-Po2 divisors)
                    m.d.sync += rx_phase.eq(self.divisor - 1)
                    with m.If(rx_count == 0):
                        # ready to be read out
                        m.d.sync += self.source.valid.eq(1)
                        m.next = "HOLDING"
            with m.State("HOLDING"):
                m.d.sync += self.source.valid.eq(1)
                with m.If(self.source.re):
                    m.d.sync += self.source.valid.eq(0)
                    m.next = "IDLE"

        return m
