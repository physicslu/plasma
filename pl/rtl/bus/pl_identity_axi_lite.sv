// Versioned PL Identity AXI4-Lite read-only block, ABI v1.
// Only identity registers 0x00..0x1c are defined. Writes return SLVERR.
// Generated constants are derived from git commit + release manifest inputs.
module pl_identity_axi_lite (
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
    input  logic         s_axi_rready
);
    `include "plasma_identity_generated.vh"

    logic aw_pending;
    logic w_pending;
    wire accept_aw;
    wire accept_w;
    wire accept_ar;

    assign s_axi_awready = s_axi_aresetn && !aw_pending && !s_axi_bvalid;
    assign s_axi_wready  = s_axi_aresetn && !w_pending  && !s_axi_bvalid;
    assign s_axi_arready = s_axi_aresetn && !s_axi_rvalid;
    assign s_axi_bresp   = 2'b10; // SLVERR: this IP is read-only
    assign accept_aw = s_axi_awvalid && s_axi_awready;
    assign accept_w  = s_axi_wvalid  && s_axi_wready;
    assign accept_ar = s_axi_arvalid && s_axi_arready;

    always_ff @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            aw_pending <= 1'b0;
            w_pending <= 1'b0;
            s_axi_bvalid <= 1'b0;
            s_axi_rvalid <= 1'b0;
            s_axi_rresp <= 2'b00;
            s_axi_rdata <= 32'b0;
        end else begin
            if (s_axi_bvalid && s_axi_bready)
                s_axi_bvalid <= 1'b0;
            if (accept_aw)
                aw_pending <= 1'b1;
            if (accept_w)
                w_pending <= 1'b1;
            if (!s_axi_bvalid && (aw_pending || accept_aw) &&
                (w_pending || accept_w)) begin
                aw_pending <= 1'b0;
                w_pending <= 1'b0;
                s_axi_bvalid <= 1'b1;
            end

            if (s_axi_rvalid && s_axi_rready)
                s_axi_rvalid <= 1'b0;
            if (accept_ar) begin
                s_axi_rvalid <= 1'b1;
                s_axi_rresp <= 2'b00; // OKAY
                // An AXI interconnect decodes the peripheral base address,
                // but may forward its nonzero upper address bits unchanged.
                // Only the 4KB slave-local register offset is decoded here.
                // The 8 registers occupy the first 32 bytes of that window.
                if (s_axi_araddr[11:5] != 7'b0) begin
                    s_axi_rdata <= 32'b0;
                    s_axi_rresp <= 2'b10; // SLVERR
                end else begin
                    case (s_axi_araddr[4:0])
                        5'h00: s_axi_rdata <= 32'h504C534D; // "PLSM"
                        5'h04: s_axi_rdata <= PLSM_VERSION;
                        5'h08: s_axi_rdata <= 32'd1; // ABI 1
                        5'h0C: s_axi_rdata <= 32'h00000001; // swd_gpio only
                        5'h10: s_axi_rdata <= PLSM_BUILD_ID_0;
                        5'h14: s_axi_rdata <= PLSM_BUILD_ID_1;
                        5'h18: s_axi_rdata <= PLSM_BUILD_ID_2;
                        5'h1C: s_axi_rdata <= PLSM_BUILD_ID_3;
                        default: begin
                            s_axi_rdata <= 32'b0;
                            s_axi_rresp <= 2'b10;
                        end
                    endcase
                end
            end
        end
    end
endmodule
