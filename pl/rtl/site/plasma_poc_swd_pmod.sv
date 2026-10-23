// Isolated PYNQ-Z2 Site 1 external SWD pads for the Blue Pill PoC.
// No target power, reset drive or voltage translation. NOT HIL qualified.
// The remote-bitbang AXI slave resets SWDIO_OE=0 and SWCLK=0.
module plasma_poc_swd_pmod (
    input  logic swclk,
    input  logic swdio_out,
    input  logic swdio_oe,
    output wire  swdio_in,
    output wire  swclk_io,
    inout  wire  swdio_io
);
    OBUF swclk_pad (.I(swclk), .O(swclk_io));
    // Xilinx IOBUF.T=1 disables output. Never synthesize push-pull
    // onto SWDIO during the target-to-host SWD turnaround.
    IOBUF swdio_pad (
        .I(swdio_out), .T(~swdio_oe), .O(swdio_in), .IO(swdio_io)
    );
endmodule
