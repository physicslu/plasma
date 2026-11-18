// Host-only Cocotb harness: two physically separate AXI4-Lite slave IPs.
// AXI crossbar address routing is a Vivado BD integration task, not
// implemented in this simulation. No clocks/pads shared between Sites except
// the source FPGA fabric clock. No target power/NRST or physical HIL.
module swd_two_site_axi_tb (
    input wire clk, rst_n,
    input wire [63:0] awaddr,
    input wire [5:0] awprot,
    input wire [1:0] awvalid,
    output wire [1:0] awready,
    input wire [63:0] wdata,
    input wire [7:0] wstrb,
    input wire [1:0] wvalid,
    output wire [1:0] wready,
    output wire [3:0] bresp,
    output wire [1:0] bvalid,
    input wire [1:0] bready,
    input wire [63:0] araddr,
    input wire [5:0] arprot,
    input wire [1:0] arvalid,
    output wire [1:0] arready,
    output wire [63:0] rdata,
    output wire [3:0] rresp,
    output wire [1:0] rvalid,
    input wire [1:0] rready,
    output wire [1:0] swclk_io,
    inout wire [1:0] swdio_io,
    output wire [1:0] site_irq
);
    for(genvar s=0; s<2; s=s+1) begin : g_sites
        plasma_swd_site_axi_lite #(
            .SITE_ID(s+1),
            .SITE_BASE_ADDRESS(s==0 ? 32'h43C01000 : 32'h43C02000)
        ) u_site (
            .s_axi_aclk(clk), .s_axi_aresetn(rst_n),
            .s_axi_awaddr(awaddr[s*32 +: 32]),
            .s_axi_awprot(awprot[s*3 +: 3]),
            .s_axi_awvalid(awvalid[s]), .s_axi_awready(awready[s]),
            .s_axi_wdata(wdata[s*32 +: 32]),
            .s_axi_wstrb(wstrb[s*4 +: 4]),
            .s_axi_wvalid(wvalid[s]), .s_axi_wready(wready[s]),
            .s_axi_bresp(bresp[s*2 +: 2]), .s_axi_bvalid(bvalid[s]),
            .s_axi_bready(bready[s]),
            .s_axi_araddr(araddr[s*32 +: 32]),
            .s_axi_arprot(arprot[s*3 +: 3]),
            .s_axi_arvalid(arvalid[s]), .s_axi_arready(arready[s]),
            .s_axi_rdata(rdata[s*32 +: 32]),
            .s_axi_rresp(rresp[s*2 +: 2]),
            .s_axi_rvalid(rvalid[s]), .s_axi_rready(rready[s]),
            .swclk_io(swclk_io[s]), .swdio_io(swdio_io[s]),
            .site_irq(site_irq[s])
        );
        // Verification-only per-Site rule checker (pl/verification/sva).
        plasma_swd_site_checks u_checks (
            .clk(clk), .rst_n(rst_n),
            .mode_q(u_site.mode_q), .normal_enable_q(u_site.normal_enable_q),
            .fault_q(u_site.fault_q), .idle_cycles_q(u_site.idle_cycles_q),
            .half_q(u_site.half_q), .cmd_level_q(u_site.cmd_level_q),
            .resp_level_q(u_site.resp_level_q), .cmd_enqueue(u_site.cmd_enqueue),
            .cmd_dequeue(u_site.cmd_dequeue), .cmd_flush(u_site.cmd_flush),
            .resp_enqueue(u_site.resp_enqueue), .resp_dequeue(u_site.resp_dequeue),
            .data_w(u_site.data_w), .active_tag(u_site.active_tag),
            .resp_head(u_site.resp_head), .drive_clk(u_site.drive_clk),
            .drive_oe(u_site.drive_oe),
            .busy(u_site.u_transaction.busy), .resp_valid(u_site.u_transaction.resp_valid),
            .resp_ready(u_site.u_transaction.resp_ready), .cmd_ready(u_site.u_transaction.cmd_ready),
            .resp_status(u_site.u_transaction.resp_status), .resp_ack(u_site.u_transaction.resp_ack),
            .resp_rdata(u_site.u_transaction.resp_rdata), .resp_data_valid(u_site.u_transaction.resp_data_valid),
            .resp_attempts(u_site.u_transaction.resp_attempts),
            .cmd_idle_cycles(u_site.u_transaction.cmd_idle_cycles),
            .cmd_half_period(u_site.u_transaction.cmd_half_period), .phase(u_site.u_transaction.phase),
            .engine_idle_q(u_site.u_transaction.idle_q), .engine_half_q(u_site.u_transaction.half_q),
            .elapsed(u_site.u_transaction.elapsed), .timeout_q(u_site.u_transaction.timeout_q),
            .swclk(u_site.u_transaction.swclk), .swdio_oe(u_site.u_transaction.swdio_oe),
            .swdio_out(u_site.u_transaction.swdio_out)
        );
    end
endmodule
