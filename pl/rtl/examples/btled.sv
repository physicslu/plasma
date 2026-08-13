`timescale 1ns / 1ps

//------------------------------------------------------------------------------
// PYNQ-Z2 button-to-LED example
//
// This small design verifies the RTL -> synthesis -> implementation ->
// bitstream -> board programming development flow.
//------------------------------------------------------------------------------
module btled (
    input  logic [3:0] btn,
    output logic [3:0] led
);

    // Each push button directly controls the LED with the same index.
    assign led = btn;

endmodule
