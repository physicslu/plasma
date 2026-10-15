// Executed immediate assertions, separate from synthesizable production RTL.
module swd_transaction_checks (
    input logic clk, rst_n, busy, cmd_ready, resp_valid, resp_ready,
    input logic [3:0] resp_status,
    input logic [2:0] resp_ack,
    input logic [31:0] resp_rdata,
    input logic resp_data_valid,
    input logic [8:0] resp_attempts,
    input logic swclk, swdio_oe, phy_start, phy_busy,
    input logic [31:0] elapsed, deadline
);
    logic held;
    logic [48:0] previous_response;
    wire [48:0] response = {resp_status,resp_ack,resp_rdata,resp_data_valid,resp_attempts};
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            held <= 0;
            previous_response <= 0;
        end else begin
            assert (!(busy && resp_valid)) else $fatal(1,"BUSY/response overlap");
            assert (!(cmd_ready && (busy || resp_valid))) else $fatal(1,"Command overwritten");
            assert (!(phy_start && phy_busy)) else $fatal(1,"PHY START while BUSY");
            assert (!busy || (deadline != 0 && elapsed < deadline)) else $fatal(1,"Deadline exceeded");
            assert (!resp_data_valid || (resp_status == 0 && resp_ack == 1)) else $fatal(1,"Invalid data exposed");
            if (!busy) assert (!swclk && !swdio_oe) else $fatal(1,"Idle ownership/clock violation");
            if (held) assert (resp_valid && response == previous_response) else $fatal(1,"Response changed under backpressure");
            held <= resp_valid && !resp_ready;
            previous_response <= response;
        end
    end
endmodule
