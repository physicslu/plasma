// LT02: isolated 2KiB AXI4-Lite scratchpad and DATA transaction counters.
// No external PL IO; it does not generate or verify patterns or use SWD.
module pl_mmio_loopback_axi_lite #(
    parameter logic [31:0] AXI_BASE_ADDRESS = 32'h40004000
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aclk, ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET s_axi_aresetn, FREQ_HZ 100000000" *)
    input  logic        s_axi_aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 s_axi_aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aresetn, POLARITY ACTIVE_LOW" *)
    input  logic        s_axi_aresetn,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWADDR" *)
    input  logic [31:0] s_axi_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *)
    input  logic [2:0]  s_axi_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *)
    input  logic        s_axi_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *)
    output logic        s_axi_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *)
    input  logic [31:0] s_axi_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *)
    input  logic [3:0]  s_axi_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *)
    input  logic        s_axi_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *)
    output logic        s_axi_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *)
    output logic [1:0]  s_axi_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *)
    output logic        s_axi_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *)
    input  logic        s_axi_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *)
    input  logic [31:0] s_axi_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *)
    input  logic [2:0]  s_axi_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *)
    input  logic        s_axi_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *)
    output logic        s_axi_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *)
    output logic [31:0] s_axi_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *)
    output logic [1:0]  s_axi_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *)
    output logic        s_axi_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RREADY" *)
    input  logic        s_axi_rready
);
    localparam logic [31:0] MEM_START = AXI_BASE_ADDRESS + 32'h100;
    localparam logic [31:0] MEM_END   = AXI_BASE_ADDRESS + 32'h900;
    localparam logic [1:0] OKAY = 2'b00;
    localparam logic [1:0] SLVERR = 2'b10;

    // Uninitialized by design; caller writes before reading. AXI read port
    // samples a word synchronously when AR is accepted.
    logic [31:0] data_words [0:511];
    logic [31:0] writes_count, reads_count;
    logic aw_pending, w_pending;
    logic [31:0] aw_addr_q, w_data_q;
    logic [3:0] w_strb_q;

    wire accept_aw = s_axi_awvalid && s_axi_awready;
    wire accept_w = s_axi_wvalid && s_axi_wready;
    wire accept_ar = s_axi_arvalid && s_axi_arready;
    wire [31:0] write_addr = accept_aw ? s_axi_awaddr : aw_addr_q;
    wire [31:0] write_data = accept_w ? s_axi_wdata : w_data_q;
    wire [3:0] write_strb = accept_w ? s_axi_wstrb : w_strb_q;
    wire write_fire = !s_axi_bvalid &&
                      (aw_pending || accept_aw) && (w_pending || accept_w);
    wire write_window = write_addr >= MEM_START && write_addr < MEM_END
                        && write_addr[1:0] == 2'b00;
    wire read_window = s_axi_araddr >= MEM_START && s_axi_araddr < MEM_END
                       && s_axi_araddr[1:0] == 2'b00;

    // 2KiB window is exactly 512 words. The 9-bit word-index subtraction
    // intentionally wraps across 0x800, avoiding a wide/truncated index.
    wire [8:0] write_index = write_addr[10:2] - MEM_START[10:2];
    wire [8:0] read_index = s_axi_araddr[10:2] - MEM_START[10:2];

    assign s_axi_awready = s_axi_aresetn && !aw_pending && !s_axi_bvalid;
    assign s_axi_wready = s_axi_aresetn && !w_pending && !s_axi_bvalid;
    assign s_axi_arready = s_axi_aresetn && !s_axi_rvalid;

    // Explicitly ignored AXI protection bits for this isolated test-only IP.
    /* verilator lint_off UNUSED */
    wire [5:0] unused_protection = {s_axi_awprot, s_axi_arprot};
    /* verilator lint_on UNUSED */

    always_ff @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            aw_pending <= 1'b0;
            w_pending <= 1'b0;
            aw_addr_q <= '0;
            w_data_q <= '0;
            w_strb_q <= '0;
            writes_count <= '0;
            reads_count <= '0;
            s_axi_bresp <= OKAY;
            s_axi_bvalid <= 1'b0;
            s_axi_rdata <= '0;
            s_axi_rresp <= OKAY;
            s_axi_rvalid <= 1'b0;
        end else begin
            if (s_axi_bvalid && s_axi_bready)
                s_axi_bvalid <= 1'b0;
            if (accept_aw) begin
                aw_pending <= 1'b1;
                aw_addr_q <= s_axi_awaddr;
            end
            if (accept_w) begin
                w_pending <= 1'b1;
                w_data_q <= s_axi_wdata;
                w_strb_q <= s_axi_wstrb;
            end

            if (write_fire) begin
                aw_pending <= 1'b0;
                w_pending <= 1'b0;
                s_axi_bvalid <= 1'b1;
                s_axi_bresp <= OKAY;
                if (write_window) begin
                    // WSTRB0 is an accepted DATA transaction with no mutation.
                    for (int lane = 0; lane < 4; lane++) begin
                        if (write_strb[lane])
                            data_words[write_index][8*lane +: 8]
                                <= write_data[8*lane +: 8];
                    end
                    writes_count <= writes_count + 32'd1;
                end else if (write_addr == AXI_BASE_ADDRESS + 32'h10 &&
                             write_data == 32'd1 && write_strb == 4'hF) begin
                    writes_count <= '0;
                    reads_count <= '0;
                end else begin
                    s_axi_bresp <= SLVERR;
                end
            end

            if (s_axi_rvalid && s_axi_rready)
                s_axi_rvalid <= 1'b0;
            if (accept_ar) begin
                s_axi_rvalid <= 1'b1;
                s_axi_rresp <= OKAY;
                if (read_window) begin
                    s_axi_rdata <= data_words[read_index];
                    reads_count <= reads_count + 32'd1;
                end else begin
                    case (s_axi_araddr)
                        AXI_BASE_ADDRESS + 32'h00: s_axi_rdata <= 32'h4C543032;
                        AXI_BASE_ADDRESS + 32'h04: s_axi_rdata <= 32'h00010000;
                        AXI_BASE_ADDRESS + 32'h08: s_axi_rdata <= 32'h00000001;
                        AXI_BASE_ADDRESS + 32'h0C: s_axi_rdata <= 32'd2048;
                        AXI_BASE_ADDRESS + 32'h14: s_axi_rdata <= 32'd1;
                        AXI_BASE_ADDRESS + 32'h18: s_axi_rdata <= writes_count;
                        AXI_BASE_ADDRESS + 32'h1C: s_axi_rdata <= reads_count;
                        default: begin
                            s_axi_rdata <= '0;
                            s_axi_rresp <= SLVERR;
                        end
                    endcase
                end
            end
        end
    end
endmodule
