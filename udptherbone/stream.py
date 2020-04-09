from nmigen import *
from nmigen.hdl.rec import *
from nmigen.lib.fifo import SyncFIFO, AsyncFIFO

from typing import *

OutputSignal = NewType('OutputSignal', Signal)
InputSignal = NewType('InputSignal', Signal)

def convert_direction(layout: Layout, indir: Direction, outdir: Direction):
    newlayout = Layout([x for x in layout])
    for fieldname in newlayout.fields:
        if newlayout.fields[fieldname][1] == indir:
            newlayout.fields[fieldname] = (newlayout.fields[fieldname][0], outdir)
    
    return newlayout


class StreamSource:
    @classmethod
    def from_sink(cls, sink, name: str = "source"): # should be typed to take StreamSink and return StreamSource
        payload_type = convert_direction(sink.payload_type, Direction.FANIN, Direction.FANOUT)
        return StreamSource(payload_type, sink.sop_enabled, sink.eop_enabled, name=name)
    
    def __init__(self, payload_type: Layout, sop: bool = True, eop: bool = True, name: str = "source"):
        self.payload_type = convert_direction(payload_type, Direction.NONE, Direction.FANOUT)
        
        data_name = name + ".data"
        ready_name = name + ".ready"
        valid_name = name + ".valid"
        sop_name = name + ".sop"
        eop_name = name + ".eop"
        
        for (name, shape, dir) in self.payload_type:
            if dir != DIR_FANOUT:
                raise TypeError("Field {!r} of StreamSource payload type has invalid direction: should be "
                        "Direction.FANOUT, is {!s}".format(name, dir))

        self.sop_enabled = sop
        self.eop_enabled = eop
        
        self.ready: InputSignal = InputSignal(Signal(name=ready_name))
        self.valid: OutputSignal = OutputSignal(Signal(name=valid_name))
        
        if sop:
            self.sop: OutputSignal = OutputSignal(Signal(name=sop_name))
        
        if eop:
            self.eop: OutputSignal = OutputSignal(Signal(name=eop_name))
        
        self.data: Record = Record(self.payload_type, name=data_name)
        
        
class StreamSink:
    @classmethod
    def from_source(cls, source: StreamSource, name: str = "sink"): # should be typed to return StreamSink
        payload_type = convert_direction(source.payload_type, Direction.FANOUT, Direction.FANIN)
        return StreamSink(payload_type, sop = source.sop_enabled, eop = source.eop_enabled, name=name)
        
    def __init__(self, payload_type: Layout, sop: bool = True, eop: bool = True, name: str = "sink"):
        self.payload_type = convert_direction(payload_type, Direction.NONE, Direction.FANIN)
        
        ready_name = name + ".ready"
        valid_name = name + ".valid"
        
        for (name, shape, dir) in self.payload_type:
            if dir != DIR_FANIN:
                raise TypeError("Field {!r} of StreamSource payload type has invalid direction: should be "
                        "Direction.FANIN, is {!s}".format(name, dir))
        
        self.sop_enabled = sop
        self.eop_enabled = eop
        
        self.ready: OutputSignal = OutputSignal(Signal(name=ready_name))
        self.valid: InputSignal = InputSignal(Signal(name=valid_name))
        
        if sop:
            self.sop: InputSignal = InputSignal(Signal())
        
        if eop:
            self.eop: InputSignal = InputSignal(Signal())
        
        self.data: Record = Record(self.payload_type)
    
    def connect(self, source: StreamSource):
        # fields is an OrderedDict so this should work
        for ((sinkname, sinkshape, sinkdir), (sourcename, sourceshape, sourcedir)) in zip(self.payload_type, source.payload_type):
            if sinkname != sourcename or sinkshape != sourceshape or sinkdir != DIR_FANIN or sourcedir != DIR_FANOUT:
                raise TypeError("Stream source payload type {!s} does not match stream sink payload type {!s}"
                        .format(self.payload_type, source.payload_type))
                
        ops = []
        
        ops += [
                source.ready.eq(self.ready),
                self.valid.eq(source.valid),
               ]
        
        if self.sop_enabled and source.sop_enabled:
            ops.append(self.sop.eq(source.sop))
        
        if self.eop_enabled and source.eop_enabled:
            ops.append(self.eop.eq(source.eop))
        
        ops.append(self.data.eq(source.data))

        return ops


class SyncFIFOStream(Elaboratable):
    def __init__(self, input: StreamSource, depth: int, fwft: bool = True):
        self._input = input
        self.sink = StreamSink.from_source(input)
        self.source = StreamSource(input.payload_type, input.sop_enabled, input.eop_enabled)
        
        width = self.source.data.shape().width
        if input.sop_enabled:
            width += 1
        if input.eop_enabled:
            width += 1
        
        self.fifo = SyncFIFO(width=width, depth=depth, fwft=fwft)
        
    def elaborate(self, platform):
        m = Module()
        
        m.submodules.fifo = self.fifo
        
        m.d.comb += self.sink.connect(self._input)
        
        m.d.comb += self.sink.ready.eq(self.fifo.w_rdy)
        m.d.comb += self.source.valid.eq(self.fifo.r_rdy)
        m.d.comb += self.source.data.eq(self.fifo.r_data)
        m.d.comb += self.fifo.w_data.eq(self.sink.data)
        
        m.d.comb += self.fifo.w_en.eq(self.sink.ready & self.sink.valid)
        m.d.comb += self.fifo.r_en.eq(self.source.valid & self.source.ready)
        
        return m


class AsyncFIFOStream(Elaboratable):
    def __init__(self, payload_type: Layout, depth: int, sop: bool = True, eop: bool = True):
        self.source = StreamSource(payload_type, sop, eop)
        self.sink = StreamSink(payload_type, sop, eop)
        
        width = self.source.data.shape().width
        if sop:
            width += 1
        if eop:
            width += 1
        
        self.fifo = AsyncFIFO(width=width, depth=depth)
        
    def elaborate(self, platform):
        m = Module()
        
        m.submodules.fifo = self.fifo
        
        m.d.comb += self.sink.ready.eq(self.fifo.w_rdy)
        m.d.comb += self.source.valid.eq(self.fifo.r_rdy)
        m.d.comb += self.source.data.eq(self.fifo.r_data)
        m.d.comb += self.fifo.w_data.eq(self.sink.data)
        
        m.d.comb += self.fifo.w_en.eq(self.sink.ready & self.sink.valid)
        m.d.comb += self.fifo.r_en.eq(self.source.valid & self.source.ready)
        
        return m


class StreamBuffer(Elaboratable):
    def __init__(self, upstream: StreamSource, downstream: StreamSink):
        self.sink = StreamSink.from_source(upstream)
        self.source = StreamSource.from_sink(downstream)
        
        self._upstream = upstream
        self._downstream = downstream
        
        self._storage = Signal.like(self.sink.data)
        self._valid = Signal()
        self._ready = Signal(reset=1)
    
    def elaborate(self, platform):
        m = Module()
        
        # Connect to buffered streams
        m.d.comb += self.sink.connect(self._upstream)
        m.d.comb += self._downstream.connect(self.source)
        
        data_we = self.sink.valid & self.sink.ready
        data_re = self.source.valid & self.source.ready
        
        # Data path
        with m.If(data_we):
            m.d.sync += self._storage.eq(self.sink.data)
        m.d.comb += self.source.data.eq(self._storage)
        
        # Upstream Ready
        # Three variables: writing, reading, signaling
        # If writing but not reading, stop signaling
        with m.If(data_we & ~data_re):
            m.d.sync += self._ready.eq(0)
        # If reading but not writing, start signaling
        with m.If(~data_we & data_re):
            m.d.sync += self._ready.eq(1)
        # Otherwise, stay the same
        m.d.comb += self.sink.ready.eq(self._ready)
        
        # Downstream Valid
        # Three variables: writing, reading, signaling
        # If writing but not reading, start signaling
        with m.If(data_we & ~data_re):
            m.d.sync += self._valid.eq(1)
        # If reading but not writing, stop signaling
        with m.If(~data_we & data_re):
            m.d.sync += self._valid.eq(0)
        # Otherwise, stay the same
        m.d.comb += self.source.valid.eq(self._valid)
        
        return m

class StreamJoiner(Elaboratable):
    def __init__(self, inputs: List[StreamSource]):
        self.sinks = []
        payload_layout = []
        for (i, source) in enumerate(inputs):
            self.sinks.append(StreamSink(
                convert_direction(source.payload_type, Direction.FANOUT, Direction.FANIN),
                source.sop_enabled,
                source.eop_enabled)
            )
            payload_layout.append(("source" + str(i), [x for x in source.payload_type]))
            
        self.payload_type = Layout(payload_layout)
        self.source = StreamSource(self.payload_type, 
                any([x.sop_enabled for x in inputs]), 
                any([x.eop_enabled for x in inputs]))
        
    def elaborate(self, platform):
        m = Module()
        
        # output is valid when all inputs are valid
        m.d.comb += self.source.valid.eq(Cat([x.valid for x in self.sinks]).all())
        
        # inputs stop being ready when output is valid but hasn't been read yet
        with m.If(self.source.valid):
            for sink in self.sinks:
                m.d.sync += sink.ready.eq(0)
        
        # inputs are ready again after each output has been consumed (output.valid and output.ready)
        with m.If(self.source.ready & self.source.valid):
            for sink in self.sinks:
                m.d.sync += sink.ready.eq(1)
        
        return m


class StreamSplitter(Elaboratable):
    pass


class StreamReducer(Elaboratable):
    def __init__(self, input: StreamSource, width: int):
        self.sink = StreamSink(
                convert_direction(input.payload_type, Direction.FANOUT, Direction.FANIN),
                input.sop_enabled,
                input.eop_enabled
            )
        
        self.width = width
        
        self.source = StreamSink(
                Layout([("data", width, DIR_FANOUT)]),
                input.sop_enabled,
                input.eop_enabled
            )
        
    def elaborate(self, platform):
        m = Module()
        
        # standard stream write enable signal
        we = self.sink.valid & self.sink.ready
        re = self.source.valid & self.source.ready
        
        input_width = self.sink.layout.shape().width
        
        # need one storage element equal to the input width
        storage = Signal(input_width)
        # need one storage element each for SOP and EOP, if enabled
        if self.sink.sop_enabled:
            sop_storage = Signal()
        if self.sink.eop_enabled:
            eop_storage = Signal()
        
        # need a counter able to store ceil(input width / output width)
        from math import ceil
        counter_max = ceil(input_width / self.width)
        counter = Signal(range(counter_max + 1))
        
        # we are ready whenever the counter is at 0
        m.d.comb += self.sink.ready.eq(counter == 0)
        # we are valid whenever the counter is not at 0
        m.d.sync += self.source.valid.eq(counter != 0)
        
        # on a write: 
        # store the input to storage
        # update the counter to its max value
        # set the source output to the first output bits
        # update SOP and EOP storage
        with m.If(we):
            slice_size = min(self.width, counter_max)
            m.d.sync += storage.eq(self.sink.data)
            m.d.sync += counter.eq(counter_max)
            m.d.sync += self.source.data.eq(self.sink.data[0:slice_size])
            if self.sink.sop_enabled:
                m.d.sync += sop_storage.eq(self.sink.sop)
            if self.sink.eop_enabled:
                m.d.sync += eop_storage.eq(self.sink.eop)
        
        # on a read, carve off a slice of the storage and decrement the counter
        with m.If(re):
            slice_size = min(self.width, counter)
            next_counter = counter - slice_size
            start_idx = counter_max - next_counter
            m.d.sync += self.counter.eq(next_counter)
            m.d.sync += self.source.data.eq(self.sink.data[start_idx:slice_size])
        
        # sop is true on the first slice of a record for whom sop was true
        m.d.comb += self.sink.sop.eq(sop_storage & (counter == counter_max))
        
        # eop is true on the last slice of a record for whom eop was true
        m.d.comb += self.sink.sop.eq(sop_storage & (counter <= self.width))
        
        return m
