// Test-only wrapper: ONE production ABI-v5 Site (Site 2 address window) with
// a flat AXI4-Lite port and a resolvable SWDIO net for an independent
// Python SWD target. Used to drive the RTL with the production C FIFO core.
// The pull-up models the board's released SWDIO level only; no electrical
// timing, voltage or PS7/AXI Interconnect behaviour is modelled.
`timescale 1ns/1ps
module swd_c_core_site_tb (
    input wire clk, rst_n,
    input wire [31:0] awaddr,
    input wire [2:0] awprot,
    input wire awvalid,
    output wire awready,
    input wire [31:0] wdata,
    input wire [3:0] wstrb,
    input wire wvalid,
    output wire wready,
    output wire [1:0] bresp,
    output wire bvalid,
    input wire bready,
    input wire [31:0] araddr,
    input wire [2:0] arprot,
    input wire arvalid,
    output wire arready,
    output wire [31:0] rdata,
    output wire [1:0] rresp,
    output wire rvalid,
    input wire rready,
    input wire target_oe,
    input wire target_out,
    output wire swclk_io,
    output wire swdio_line,
    output wire site_irq
);
    tri1 swdio;
    assign swdio = target_oe ? target_out : 1'bz;
    assign swdio_line = swdio;
    plasma_swd_site_axi_lite #(
        .SITE_ID(2),
        .SITE_BASE_ADDRESS(32'h43C02000)
    ) u_site (
        .s_axi_aclk(clk), .s_axi_aresetn(rst_n),
        .s_axi_awaddr(awaddr), .s_axi_awprot(awprot),
        .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb),
        .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arprot(arprot),
        .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp),
        .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .swclk_io(swclk_io), .swdio_io(swdio),
        .site_irq(site_irq)
    );
endmodule
