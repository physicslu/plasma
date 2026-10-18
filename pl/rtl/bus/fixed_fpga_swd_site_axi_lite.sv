// Gate 1 simulation-only SWD Site-1 v1 PIO AXI4-Lite vertical slice.
// Not a PPU image, not a real UIO device, not a universal multi-site endpoint.
// No power, OE, NRST, FPGA Manager, PL reload, external pin constraints or SPI.
// Reuses the established swd_transaction_master; master protocol has a narrower
// precisely 64 driven-high line-reset clocks; the ABI now requires 64.
// A synthesized fixed-image product must add global Identity and qualify
// timing/resource/AXI before any board or DUT operation.
module fixed_fpga_swd_site_axi_lite #(
    parameter logic [31:0] AXI_BASE_ADDRESS = 32'h40004000
) (
    input logic s_axi_aclk, s_axi_aresetn,
    input logic [31:0] s_axi_awaddr,
    input logic [2:0] s_axi_awprot,
    input logic s_axi_awvalid,
    output logic s_axi_awready,
    input logic [31:0] s_axi_wdata,
    input logic [3:0] s_axi_wstrb,
    input logic s_axi_wvalid,
    output logic s_axi_wready,
    output logic [1:0] s_axi_bresp,
    output logic s_axi_bvalid,
    input logic s_axi_bready,
    input logic [31:0] s_axi_araddr,
    input logic [2:0] s_axi_arprot,
    input logic s_axi_arvalid,
    output logic s_axi_arready,
    output logic [31:0] s_axi_rdata,
    output logic [1:0] s_axi_rresp,
    output logic s_axi_rvalid,
    input logic s_axi_rready,
    input logic swdio_in,
    output logic swclk, swdio_out, swdio_oe,
    output logic site_ready_o, site_fault_o
);
    localparam logic [1:0] OKAY=2'b00, SLVERR=2'b10;
    localparam logic [31:0] SITE_ID=32'd1, ABI=32'h00010000;
    localparam logic [31:0] CAP_SWD=32'd1;
    localparam logic [31:0] CMD_XFER=32'd1, CMD_RESET=32'd2;
    localparam logic [31:0] PROTO_SWD=32'd1;
    localparam logic [31:0] STATE_IDLE=1, STATE_BUSY=2, STATE_DONE=4, STATE_FAULT=8;

    logic aw_hold, w_hold;
    logic [31:0] aw_q, wd_q;
    logic [3:0] strb_q;
    wire aw_take=s_axi_awvalid && s_axi_awready;
    wire w_take=s_axi_wvalid && s_axi_wready;
    wire ar_take=s_axi_arvalid && s_axi_arready;
    wire [31:0] waddr=aw_take ? s_axi_awaddr : aw_q;
    wire [31:0] wdata=w_take ? s_axi_wdata : wd_q;
    wire [3:0] wstrb=w_take ? s_axi_wstrb : strb_q;
    wire committing=(!s_axi_bvalid && (aw_hold||aw_take) && (w_hold||w_take));

    logic [31:0] seq_q, proto_q, flags_q, count_q, arg_q, data_q;
    logic [31:0] timeout_q, div_q;
    logic [31:0] done_seq, done_status, done_data, counter_q;
    logic [31:0] swd_meta_q, swd_raw_status_q, last_seq;
    logic [31:0] active_seq;
    logic done_valid, fault_latched, launch_pending, abort_pulse, consume_pulse;
    logic [31:0] operation_q;
    wire master_ready, master_busy, master_resp_valid;
    wire [1:0] master_link;
    wire [3:0] master_status;
    wire [2:0] master_ack;
    wire [31:0] master_rdata;
    wire master_data_valid;
    wire [8:0] master_attempts;
    wire active=launch_pending || master_busy || master_resp_valid || done_valid || fault_latched;

    assign s_axi_awready=s_axi_aresetn && !aw_hold && !s_axi_bvalid;
    assign s_axi_wready=s_axi_aresetn && !w_hold && !s_axi_bvalid;
    assign s_axi_arready=s_axi_aresetn && !s_axi_rvalid;
    // Physical RTL Site 1 status, not a synthetic Global readiness constant.
    assign site_fault_o = fault_latched;
    assign site_ready_o = s_axi_aresetn && master_ready && !active;


    swd_transaction_master master (
        .clk(s_axi_aclk), .rst_n(s_axi_aresetn), .cmd_abort(abort_pulse),
        .cmd_valid(launch_pending), .cmd_ready(master_ready),
        .cmd_op(operation_q==CMD_RESET), .cmd_ap(arg_q[0]),
        .cmd_read(arg_q[1]), .cmd_addr({arg_q[3:2],2'b00}),
        .cmd_wdata(data_q), .cmd_half_period(div_q[15:0]),
        .cmd_turnaround(3'd1), .cmd_idle_cycles(8'd8),
        .cmd_max_retries(8'd0), .cmd_error_data_phase(1'b0),
        .cmd_timeout_cycles(timeout_q), .busy(master_busy),
        .link_state(master_link), .resp_valid(master_resp_valid),
        .resp_ready(consume_pulse), .resp_status(master_status),
        .resp_ack(master_ack), .resp_rdata(master_rdata),
        .resp_data_valid(master_data_valid), .resp_attempts(master_attempts),
        .swdio_in(swdio_in), .swclk(swclk), .swdio_out(swdio_out),
        .swdio_oe(swdio_oe)
    );

    function automatic logic [31:0] translate_status(input logic [3:0] status);
        case (status)
            4'd0: translate_status=32'd0;  // OK
            4'd3: translate_status=32'd1;  // SWD_WAIT
            4'd4: translate_status=32'd2;  // SWD_FAULT
            4'd5: translate_status=32'd3;  // SWD_NO_ACK
            4'd6: translate_status=32'd4;  // PARITY
            4'd7: translate_status=32'd5;  // TIMEOUT
            4'd8: translate_status=32'd6;  // ABORTED
            4'd1: translate_status=32'd7; // BAD_ARGUMENT
            4'd2: translate_status=32'd10; // NEED_RESET (not a bad argument)
            4'd9: translate_status=32'd11; // PHY_ERROR
            default: translate_status=32'd9; // INTERNAL_FAULT
        endcase
    endfunction

    function automatic logic valid_cmd(input logic [31:0] cmd);
        valid_cmd = !active && master_ready && seq_q != 0 && seq_q != last_seq &&
            proto_q==PROTO_SWD && flags_q==0 &&
            div_q>=2 && div_q<=65535 && timeout_q != 0 &&
            ((cmd==CMD_XFER && count_q==32 && arg_q<=15) ||
             (cmd==CMD_RESET && count_q==64 && arg_q==0 && data_q==0));
    endfunction

    always_ff @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            aw_hold<=0; w_hold<=0; aw_q<=0; wd_q<=0; strb_q<=0;
            s_axi_bvalid<=0; s_axi_bresp<=OKAY;
            s_axi_rvalid<=0; s_axi_rresp<=OKAY; s_axi_rdata<=0;
            seq_q<=0; proto_q<=PROTO_SWD; flags_q<=0;
            count_q<=32; arg_q<=2; data_q<=0;
            timeout_q<=32'd1000000; div_q<=2;
            done_seq<=0; done_status<=0; done_data<=0;
            swd_meta_q<=0; swd_raw_status_q<=0; last_seq<=0;
            counter_q<=0; active_seq<=0;
            done_valid<=0; fault_latched<=0; launch_pending<=0;
            abort_pulse<=0; consume_pulse<=0; operation_q<=0;
        end else begin
            abort_pulse<=0;
            consume_pulse<=0;
            if (launch_pending && master_ready)
                launch_pending<=0;
            if (master_resp_valid && !done_valid) begin
                done_seq<=active_seq;
                done_status<=translate_status(master_status);
                done_data <= (master_data_valid && master_status==0) ? master_rdata : 0;
                swd_meta_q <= {17'd0, master_link, master_attempts, master_data_valid, master_ack};
                swd_raw_status_q <= {28'd0, master_status};
                done_valid<=1;
                counter_q<=counter_q+32'd1;
                consume_pulse<=1;
                if (master_status==4'd7 || master_status==4'd8 || master_status==4'd9)
                    fault_latched<=1;
            end
            if (s_axi_bvalid && s_axi_bready)
                s_axi_bvalid<=0;
            if (s_axi_rvalid && s_axi_rready)
                s_axi_rvalid<=0;

            if (aw_take) begin aw_hold<=1; aw_q<=s_axi_awaddr; end
            if (w_take) begin w_hold<=1; wd_q<=s_axi_wdata; strb_q<=s_axi_wstrb; end

            if (committing) begin
                aw_hold<=0;
                w_hold<=0;
                s_axi_bvalid<=1;
                s_axi_bresp<=OKAY;
                if (waddr[31:12]!=AXI_BASE_ADDRESS[31:12] ||
                    waddr[11:0]>=12'h100 || waddr[1:0]!=0 ||
                    wstrb!=4'hf) begin
                    s_axi_bresp<=SLVERR;
                end else case (waddr[7:0])
                    8'h20: begin // COMMAND: commit only after all setup words
                        if (!valid_cmd(wdata)) s_axi_bresp<=SLVERR;
                        else begin
                            operation_q<=wdata;
                            active_seq<=seq_q;
                            last_seq<=seq_q;
                            launch_pending<=1;
                        end
                    end
                    8'h24: if (active || wdata==0) s_axi_bresp<=SLVERR;
                              else seq_q<=wdata;
                    8'h28: if (active || wdata!=PROTO_SWD) s_axi_bresp<=SLVERR;
                              else proto_q<=wdata;
                    8'h2c: if (active || wdata!=0) s_axi_bresp<=SLVERR;
                              else flags_q<=wdata;
                    8'h30: if (active || (wdata!=32 && wdata!=64)) s_axi_bresp<=SLVERR;
                              else count_q<=wdata;
                    8'h34: if (active || wdata>15) s_axi_bresp<=SLVERR;
                              else arg_q<=wdata;
                    8'h38: if (active) s_axi_bresp<=SLVERR;
                              else data_q<=wdata;
                    8'h3c: if (active || wdata==0) s_axi_bresp<=SLVERR;
                              else timeout_q<=wdata;
                    // Launch-window abort returns SLVERR. Never pretend it cancelled SWD.
                    8'h54: if (wdata!=1 || !master_busy) s_axi_bresp<=SLVERR;
                              else abort_pulse<=1;
                    8'h5c: if (active || wdata<2 || wdata>65535) s_axi_bresp<=SLVERR;
                              else div_q<=wdata;
                    8'h64: begin
                        // Fault ACK consumes the completion evidence but NEVER clears
                        // the latched FAULT. No in-band recovery is implemented.
                        if (!done_valid || wdata!=done_seq)
                            s_axi_bresp<=SLVERR;
                        else done_valid<=0;
                    end
                    default: s_axi_bresp<=SLVERR;
                endcase
            end

            if (ar_take) begin
                s_axi_rvalid<=1;
                s_axi_rresp<=OKAY;
                s_axi_rdata<=0;
                if (s_axi_araddr[31:12]!=AXI_BASE_ADDRESS[31:12] ||
                    s_axi_araddr[11:0]>=12'h100 || s_axi_araddr[1:0]!=0)
                    s_axi_rresp<=SLVERR;
                else case (s_axi_araddr[7:0])
                    8'h00: s_axi_rdata<=SITE_ID;
                    8'h04: s_axi_rdata<=ABI;
                    8'h08: s_axi_rdata<=CAP_SWD;
                    8'h0c: s_axi_rdata<=fault_latched ? STATE_FAULT :
                                           done_valid ? STATE_DONE :
                                           (launch_pending || master_busy ||
                                            master_resp_valid) ? STATE_BUSY : STATE_IDLE;
                    8'h10: s_axi_rdata<=fault_latched ? done_status : 0;
                    8'h14: s_axi_rdata<=(launch_pending||master_busy) ? active_seq : 0;
                    8'h18: s_axi_rdata<=0; // no SPI data FIFO in SWD-only slice
                    8'h1c: s_axi_rdata<=0; // no SPI data FIFO in SWD-only slice
                    8'h48: s_axi_rdata<=done_seq;
                    8'h4c: s_axi_rdata<=done_status;
                    8'h50: s_axi_rdata<=done_valid && done_status==0 && operation_q==CMD_XFER && arg_q[1] ? 1 : 0;
                    8'h58: s_axi_rdata<=0; // no SPI FIFO, do not claim capacity
                    8'h60: s_axi_rdata<=done_data;
                    8'h68: s_axi_rdata<=counter_q;
                    8'h6c: s_axi_rdata<=swd_meta_q;
                    8'h70: s_axi_rdata<=swd_raw_status_q;
                    default: s_axi_rresp<=SLVERR;
                endcase
            end
        end
    end
endmodule
