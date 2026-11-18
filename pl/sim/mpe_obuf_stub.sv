// Verification-only combinational Xilinx OBUF model for MPE pad simulation.
// Do not include this module in Vivado synthesis/source sets.
module OBUF (
    input wire I,
    output wire O
);
    assign O = I;
endmodule
