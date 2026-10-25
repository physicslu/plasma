// Blue Pill single-Site remote_bitbang SWD GPIO candidate (HOST SIM ONLY).
// This independent AXI4-Lite component is NOT connected to a Z2 top,
// not a replacement for the versioned fixed-image PPU ABI, and has no
// pin constraints, voltage regulation or DUT power/reset authority.
// Physical mapping/owner, FPGA image, pinmux and Hi-Z need separate review.
module plasma_poc_swd_gpio_axi_lite #(
    parameter logic [31:0] AXI_BASE_ADDRESS = 32'h40008000
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aclk, ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET s_axi_aresetn, FREQ_HZ 100000000" *)
    input  logic         s_axi_aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 s_axi_aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aresetn, POLARITY ACTIVE_LOW" *)
    input  logic         s_axi_aresetn,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWADDR" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 32, FREQ_HZ 100000000" *)
    input  logic [31:0]  s_axi_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *)
    input  logic [2:0]   s_axi_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *)
    input  logic         s_axi_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *)
    output logic         s_axi_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *)
    input  logic [31:0]  s_axi_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *)
    input  logic [3:0]   s_axi_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *)
    input  logic         s_axi_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *)
    output logic         s_axi_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *)
    output logic [1:0]   s_axi_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *)
    output logic         s_axi_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *)
    input  logic         s_axi_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *)
    input  logic [31:0]  s_axi_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *)
    input  logic [2:0]   s_axi_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *)
    input  logic         s_axi_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *)
    output logic         s_axi_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *)
    output logic [31:0]  s_axi_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *)
    output logic [1:0]   s_axi_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *)
    output logic         s_axi_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RREADY" *)
    input  logic         s_axi_rready,
    input  logic         swdio_in,
    output logic         swclk,
    output logic         swdio_out,
    output logic         swdio_oe
);
    localparam logic [1:0] OKAY=2'b00, SLVERR=2'b10;
    localparam logic [31:0] MAGIC=32'h50425357, VERSION=32'h00010000;
    logic aw_hold, w_hold;
    logic [31:0] aw_q, wd_q;
    logic [3:0] strb_q;
    wire aw_take=s_axi_awvalid && s_axi_awready;
    wire w_take=s_axi_wvalid && s_axi_wready;
    wire ar_take=s_axi_arvalid && s_axi_arready;
    wire [31:0] waddr=aw_take ? s_axi_awaddr : aw_q;
    wire [31:0] wdata=w_take ? s_axi_wdata : wd_q;
    wire [3:0] wstrb=w_take ? s_axi_wstrb : strb_q;
    wire committing=!s_axi_bvalid && (aw_hold||aw_take) && (w_hold||w_take);
    assign s_axi_awready=s_axi_aresetn && !aw_hold && !s_axi_bvalid;
    assign s_axi_wready=s_axi_aresetn && !w_hold && !s_axi_bvalid;
    assign s_axi_arready=s_axi_aresetn && !s_axi_rvalid;

    always_ff @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            aw_hold<=0; w_hold<=0; aw_q<=0; wd_q<=0; strb_q<=0;
            s_axi_bvalid<=0; s_axi_bresp<=OKAY;
            s_axi_rvalid<=0; s_axi_rresp<=OKAY; s_axi_rdata<=0;
            swclk<=0; swdio_out<=1; swdio_oe<=0;
        end else begin
            if (s_axi_bvalid && s_axi_bready)
                s_axi_bvalid<=0;
            if (s_axi_rvalid && s_axi_rready)
                s_axi_rvalid<=0;
            if (aw_take) begin aw_hold<=1; aw_q<=s_axi_awaddr; end
            if (w_take) begin w_hold<=1; wd_q<=s_axi_wdata; strb_q<=s_axi_wstrb; end
            if (committing) begin
                aw_hold<=0; w_hold<=0; s_axi_bvalid<=1;
                s_axi_bresp<=SLVERR;
                if (waddr==AXI_BASE_ADDRESS+32'h8 && wstrb==4'hF &&
                        wdata[31:3]==0) begin
                    swclk<=wdata[0]; swdio_out<=wdata[1]; swdio_oe<=wdata[2];
                    s_axi_bresp<=OKAY;
                end
            end
            if (ar_take) begin
                s_axi_rvalid<=1;
                s_axi_rresp<=OKAY;
                case (s_axi_araddr)
                    AXI_BASE_ADDRESS: s_axi_rdata<=MAGIC;
                    AXI_BASE_ADDRESS+32'h4: s_axi_rdata<=VERSION;
                    AXI_BASE_ADDRESS+32'hC:
                        s_axi_rdata<={28'd0,swdio_out,swdio_oe,swclk,swdio_in};
                    default: begin
                        s_axi_rdata<=0;
                        s_axi_rresp<=SLVERR;
                    end
                endcase
            end
        end
    end
endmodule
