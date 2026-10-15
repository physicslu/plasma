// Simulation-only structural wrapper; assertions never enter Vivado source sets.
module swd_command_axi_tb #(
    parameter logic [31:0] AXI_BASE_ADDRESS = 32'h40002000
) (

    input  logic         s_axi_aclk,

    input  logic         s_axi_aresetn,

    input  logic [31:0]  s_axi_awaddr,
    input  logic [2:0]   s_axi_awprot,
    input  logic         s_axi_awvalid,
    output logic         s_axi_awready,
    input  logic [31:0]  s_axi_wdata,
    input  logic [3:0]   s_axi_wstrb,
    input  logic         s_axi_wvalid,
    output logic         s_axi_wready,
    output logic [1:0]   s_axi_bresp,
    output logic         s_axi_bvalid,
    input  logic         s_axi_bready,
    input  logic [31:0]  s_axi_araddr,
    input  logic [2:0]   s_axi_arprot,
    input  logic         s_axi_arvalid,
    output logic         s_axi_arready,
    output logic [31:0]  s_axi_rdata,
    output logic [1:0]   s_axi_rresp,
    output logic         s_axi_rvalid,
    input  logic         s_axi_rready
);
    swd_command_axi_lite #(.AXI_BASE_ADDRESS(AXI_BASE_ADDRESS)) core (
        .s_axi_aclk(s_axi_aclk),
        .s_axi_aresetn(s_axi_aresetn),
        .s_axi_awaddr(s_axi_awaddr),
        .s_axi_awprot(s_axi_awprot),
        .s_axi_awvalid(s_axi_awvalid),
        .s_axi_awready(s_axi_awready),
        .s_axi_wdata(s_axi_wdata),
        .s_axi_wstrb(s_axi_wstrb),
        .s_axi_wvalid(s_axi_wvalid),
        .s_axi_wready(s_axi_wready),
        .s_axi_bresp(s_axi_bresp),
        .s_axi_bvalid(s_axi_bvalid),
        .s_axi_bready(s_axi_bready),
        .s_axi_araddr(s_axi_araddr),
        .s_axi_arprot(s_axi_arprot),
        .s_axi_arvalid(s_axi_arvalid),
        .s_axi_arready(s_axi_arready),
        .s_axi_rdata(s_axi_rdata),
        .s_axi_rresp(s_axi_rresp),
        .s_axi_rvalid(s_axi_rvalid),
        .s_axi_rready(s_axi_rready)
    );
    pl_axi_waveform_checks checks (
        .clk(s_axi_aclk), .rst_n(s_axi_aresetn),
        .rvalid(s_axi_rvalid), .rready(s_axi_rready), .rdata(s_axi_rdata), .rresp(s_axi_rresp),
        .bvalid(s_axi_bvalid), .bready(s_axi_bready), .bresp(s_axi_bresp),
        .busy(core.engine_busy), .done(core.engine_done), .start(core.engine_start),
        .swclk(core.swclk), .oe(core.swdio_oe)
    );
endmodule
