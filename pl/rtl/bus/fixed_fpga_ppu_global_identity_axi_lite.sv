// PLASMA Fixed Universal Image ABI v1: isolated read-only PPU global slice.
// Host simulation only. NOT wired to existing legacy Identity, Site RTL,
// PYNQ-Z2 address decoder, UIO device, FPGA Manager or real pins.
// Parameters are example immutable build inputs, NOT an authenticity proof.
// The proposed Image/Build IDs must be separately bound to a reviewed manifest.
// Exactly 32-bit aligned little-endian AXI4-Lite accesses are supported.
// All writes and accesses to reserved/Site regions return SLVERR.
module fixed_fpga_ppu_global_identity_axi_lite #(
    parameter logic [31:0] AXI_BASE_ADDRESS = 32'h40000000,
    parameter logic [31:0] IMAGE_ID_W0 = 32'h11112222,
    parameter logic [31:0] IMAGE_ID_W1 = 32'h33334444,
    parameter logic [31:0] IMAGE_ID_W2 = 32'h55556666,
    parameter logic [31:0] IMAGE_ID_W3 = 32'h77778888,
    parameter logic [31:0] BUILD_ID_W0 = 32'habcde001,
    parameter logic [31:0] BUILD_ID_W1 = 32'habcde002,
    parameter logic [31:0] BUILD_ID_W2 = 32'habcde003,
    parameter logic [31:0] BUILD_ID_W3 = 32'habcde004,
    parameter logic [31:0] CAPABILITIES_LO = 32'h00000001,
    parameter logic [7:0] SITE_PRESENT = 8'h01,
    parameter logic [31:0] HW_REVISION = 32'h00000001,
    parameter logic [31:0] MAX_TRANSFER_BITS = 32'd64
) (
    input  logic        s_axi_aclk,
    input  logic        s_axi_aresetn,
    input  logic [31:0] s_axi_awaddr,
    input  logic [2:0]  s_axi_awprot,
    input  logic        s_axi_awvalid,
    output logic        s_axi_awready,
    input  logic [31:0] s_axi_wdata,
    input  logic [3:0]  s_axi_wstrb,
    input  logic        s_axi_wvalid,
    output logic        s_axi_wready,
    output logic [1:0]  s_axi_bresp,
    output logic        s_axi_bvalid,
    input  logic        s_axi_bready,
    input  logic [31:0] s_axi_araddr,
    input  logic [2:0]  s_axi_arprot,
    input  logic        s_axi_arvalid,
    output logic        s_axi_arready,
    output logic [31:0] s_axi_rdata,
    output logic [1:0]  s_axi_rresp,
    output logic        s_axi_rvalid,
    input  logic        s_axi_rready,
    input  logic [7:0]  site_ready_i,
    input  logic [7:0]  site_fault_i,
    input  logic        pl_ready_i
);
    localparam logic [1:0] OKAY = 2'b00, SLVERR = 2'b10;
    logic aw_pending, w_pending;
    wire aw_accept = s_axi_awvalid && s_axi_awready;
    wire w_accept  = s_axi_wvalid && s_axi_wready;
    wire ar_accept = s_axi_arvalid && s_axi_arready;
    assign s_axi_awready = s_axi_aresetn && !aw_pending && !s_axi_bvalid;
    assign s_axi_wready  = s_axi_aresetn && !w_pending && !s_axi_bvalid;
    assign s_axi_arready = s_axi_aresetn && !s_axi_rvalid;
    assign s_axi_bresp   = SLVERR; // read-only: writes always reject

    wire [7:0] ready_mask = SITE_PRESENT & site_ready_i & ~site_fault_i;
    wire [7:0] fault_mask = SITE_PRESENT & site_fault_i;
    wire [31:0] ppu_status =
        {30'd0, (|fault_mask), pl_ready_i};
    wire [31:0] global_status =
        {30'd0, (|fault_mask), pl_ready_i};

    always_ff @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            aw_pending <= 1'b0;
            w_pending <= 1'b0;
            s_axi_bvalid <= 1'b0;
            s_axi_rvalid <= 1'b0;
            s_axi_rresp <= OKAY;
            s_axi_rdata <= 32'd0;
        end else begin
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 1'b0;
            if (aw_accept) aw_pending <= 1'b1;
            if (w_accept) w_pending <= 1'b1;
            if (!s_axi_bvalid && (aw_pending || aw_accept) &&
                (w_pending || w_accept)) begin
                aw_pending <= 1'b0;
                w_pending <= 1'b0;
                s_axi_bvalid <= 1'b1;
            end

            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 1'b0;
            if (ar_accept) begin
                s_axi_rvalid <= 1'b1;
                s_axi_rresp <= OKAY;
                s_axi_rdata <= 32'd0;
                if (s_axi_araddr[31:16] != AXI_BASE_ADDRESS[31:16] ||
                    s_axi_araddr[1:0] != 2'b00) begin
                    s_axi_rresp <= SLVERR;
                end else begin
                    case (s_axi_araddr[15:0])
                        16'h0000: s_axi_rdata <= 32'h4D534C50; // v1 PLSM
                        16'h0004: s_axi_rdata <= 32'h00010000;
                        16'h0008: s_axi_rdata <= IMAGE_ID_W0;
                        16'h000c: s_axi_rdata <= IMAGE_ID_W1;
                        16'h0010: s_axi_rdata <= IMAGE_ID_W2;
                        16'h0014: s_axi_rdata <= IMAGE_ID_W3;
                        16'h0018: s_axi_rdata <= BUILD_ID_W0;
                        16'h001c: s_axi_rdata <= BUILD_ID_W1;
                        16'h0020: s_axi_rdata <= BUILD_ID_W2;
                        16'h0024: s_axi_rdata <= BUILD_ID_W3;
                        16'h0028: s_axi_rdata <= CAPABILITIES_LO;
                        16'h002c: s_axi_rdata <= 32'd0; // cap high
                        16'h0030: s_axi_rdata <= {24'd0, SITE_PRESENT};
                        16'h0034: s_axi_rdata <= {24'd0, ready_mask};
                        16'h0038: s_axi_rdata <= ppu_status;
                        16'h003c: s_axi_rdata <= HW_REVISION;
                        16'h0040: s_axi_rdata <= (|fault_mask) ? 32'd1 : 32'd0;
                        16'h0044: s_axi_rdata <= 32'd1; // map revision
                        16'h0048: s_axi_rdata <= 32'd4096;
                        16'h004c: s_axi_rdata <= MAX_TRANSFER_BITS;
                        16'h0050: s_axi_rdata <= 32'd0; // no reset provenance
                        16'h1000: s_axi_rdata <= global_status;
                        16'h1004: s_axi_rdata <= {24'd0, fault_mask};
                        16'h1008: s_axi_rdata <= {24'd0, fault_mask};
                        16'h100c: s_axi_rdata <= 32'd0; // broker epoch unavailable
                        default: s_axi_rresp <= SLVERR;
                    endcase
                end
            end
        end
    end
endmodule
