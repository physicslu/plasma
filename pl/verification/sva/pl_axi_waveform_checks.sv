// Verification-only immediate protocol assertions, executed by Icarus.
// Temporal SVA/bind support is not claimed by this checker.
module pl_axi_waveform_checks (
    input logic clk, rst_n,
    input logic rvalid, rready,
    input logic [31:0] rdata,
    input logic [1:0] rresp,
    input logic bvalid, bready,
    input logic [1:0] bresp,
    input logic busy, done, start, swclk, oe
);
    logic hold_r, hold_b;
    logic [31:0] previous_data;
    logic [1:0] previous_rresp, previous_bresp;
    always @(posedge clk) begin
        if (!rst_n) begin
            hold_r <= 1'b0;
            hold_b <= 1'b0;
            previous_data <= '0;
            previous_rresp <= '0;
            previous_bresp <= '0;
        end else begin
            if (hold_r) begin
                assert (rvalid && rdata == previous_data && rresp == previous_rresp)
                    else $fatal(1, "AXI R response changed under backpressure");
            end
            if (hold_b) begin
                assert (bvalid && bresp == previous_bresp)
                    else $fatal(1, "AXI B response changed under backpressure");
            end
            assert (!(start && busy)) else $fatal(1, "Active engine received START");
            assert (!(done && busy)) else $fatal(1, "DONE must terminate engine BUSY");
            if (!busy) begin
                assert (!swclk && !oe) else $fatal(1, "Idle engine must be clock-low/OE-low");
            end
            hold_r <= rvalid && !rready;
            hold_b <= bvalid && !bready;
            previous_data <= rdata;
            previous_rresp <= rresp;
            previous_bresp <= bresp;
        end
    end
endmodule
