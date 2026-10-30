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
    end
endmodule
