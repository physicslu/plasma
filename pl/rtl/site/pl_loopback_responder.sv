// Dedicated synchronous digital fixture, NOT a physical SWD target responder.
// Mode 0 echoes driven TX, or 1 when output ownership is released.
// Mode 1 returns an independently latched pattern, LSB first.
module pl_loopback_responder (
    input logic clk,
    input logic rst_n,
    input logic start,
    input logic [31:0] pattern,
    input logic pattern_mode,
    input logic swclk,
    input logic swdio_out,
    input logic swdio_oe,
    output logic swdio_in
);
    logic [31:0] pattern_q;
    logic mode_q;
    logic [4:0] index_q;
    logic previous_clock;
    assign swdio_in = mode_q ? pattern_q[index_q] : (swdio_oe ? swdio_out : 1'b1);
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            pattern_q <= '0;
            mode_q <= 1'b0;
            index_q <= '0;
            previous_clock <= 1'b0;
        end else begin
            previous_clock <= swclk;
            if (start) begin
                pattern_q <= pattern;
                mode_q <= pattern_mode;
                index_q <= '0;
                previous_clock <= 1'b0;
            end else if (previous_clock && !swclk && index_q != 31) begin
                // Engine samples before its falling-edge update; advance on
                // the following FCLK edge, safely within the >=2-cycle low phase.
                index_q <= index_q + 5'd1;
            end
        end
    end
endmodule
