// Test-only Xilinx IOBUF functional model.
// Covers 0/1/Z and contention as resolved by the 4-state simulator.
// Does not model analog levels, slew, voltage compatibility or timing.
module IOBUF (
    input wire I,
    input wire T,
    output wire O,
    inout wire IO
);
    assign IO = T ? 1'bz : I;
    assign O = IO;
endmodule
