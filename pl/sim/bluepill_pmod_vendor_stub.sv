// Simulation-only ideal Xilinx primitives. NEVER include in Vivado synthesis.
module OBUF(input wire I, output wire O);
    assign O = I;
endmodule
module IOBUF(input wire I, input wire T, output wire O, inout wire IO);
    assign IO = T ? 1'bz : I;
    assign O = IO;
endmodule
module bluepill_pmod_tb (
    input logic swclk,
    input logic swdio_out,
    input logic swdio_oe,
    input logic target_oe,
    input logic target_out,
    output wire sample_swdio,
    output wire sample_swclk
);
    tri swdio_wire;
    assign swdio_wire = target_oe ? target_out : 1'bz;
    plasma_poc_swd_pmod pads (
        .swclk(swclk), .swdio_out(swdio_out), .swdio_oe(swdio_oe),
        .swdio_in(sample_swdio), .swclk_io(sample_swclk),
        .swdio_io(swdio_wire)
    );
endmodule
