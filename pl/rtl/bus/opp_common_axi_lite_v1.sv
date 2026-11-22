// OPP v1 common AXI4-Lite register slave. One instance per FPGA image.
// AW/W independent; one outstanding read and write response; WSTRB honored.
// Only SCRATCH is writable. All unimplemented offsets return SLVERR.
module opp_common_axi_lite_v1 #(
  parameter logic [127:0] IMAGE_ID = 128'h0,
  parameter logic [127:0] BUILD_ID = 128'h0,
  parameter logic [63:0] CAPABILITIES = 64'h0,
  parameter logic [31:0] SITE_PRESENT = 32'h0,
  parameter logic [31:0] SITE_READY = 32'h0,
  parameter logic [31:0] PPU_STATUS = 32'h0,
  parameter logic [31:0] HW_REVISION = 32'h0
) (
  input logic aclk,
  input logic aresetn,
  input logic [11:0] s_axi_awaddr,
  input logic s_axi_awvalid,
  output logic s_axi_awready,
  input logic [31:0] s_axi_wdata,
  input logic [3:0] s_axi_wstrb,
  input logic s_axi_wvalid,
  output logic s_axi_wready,
  output logic [1:0] s_axi_bresp,
  output logic s_axi_bvalid,
  input logic s_axi_bready,
  input logic [11:0] s_axi_araddr,
  input logic s_axi_arvalid,
  output logic s_axi_arready,
  output logic [31:0] s_axi_rdata,
  output logic [1:0] s_axi_rresp,
  output logic s_axi_rvalid,
  input logic s_axi_rready
);
  localparam logic [1:0] OKAY = 2'b00;
  localparam logic [1:0] SLVERR = 2'b10;
  logic aw_pending_q, w_pending_q;
  logic [11:0] awaddr_q;
  logic [31:0] wdata_q;
  logic [3:0] wstrb_q;
  logic [31:0] scratch_q;
  logic [31:0] read_data;
  logic read_valid;
  integer i;

  assign s_axi_awready = !aw_pending_q && !s_axi_bvalid;
  assign s_axi_wready = !w_pending_q && !s_axi_bvalid;
  assign s_axi_arready = !s_axi_rvalid;

  always_comb begin
    read_data = 32'h0;
    read_valid = 1'b1;
    case (s_axi_araddr)
      12'h000: read_data = 32'h4d534c50;
      12'h004: read_data = 32'h00010000;
      12'h008: read_data = IMAGE_ID[31:0];
      12'h00c: read_data = IMAGE_ID[63:32];
      12'h010: read_data = IMAGE_ID[95:64];
      12'h014: read_data = IMAGE_ID[127:96];
      12'h018: read_data = BUILD_ID[31:0];
      12'h01c: read_data = BUILD_ID[63:32];
      12'h020: read_data = BUILD_ID[95:64];
      12'h024: read_data = BUILD_ID[127:96];
      12'h028: read_data = CAPABILITIES[31:0];
      12'h02c: read_data = CAPABILITIES[63:32];
      12'h030: read_data = SITE_PRESENT;
      12'h034: read_data = SITE_READY;
      12'h038: read_data = PPU_STATUS;
      12'h03c: read_data = HW_REVISION;
      12'h040: read_data = scratch_q;
      default: read_valid = 1'b0;
    endcase
  end

  always_ff @(posedge aclk or negedge aresetn) begin
    if (!aresetn) begin
      aw_pending_q <= 1'b0;
      w_pending_q <= 1'b0;
      awaddr_q <= '0;
      wdata_q <= '0;
      wstrb_q <= '0;
      scratch_q <= '0;
      s_axi_bresp <= OKAY;
      s_axi_bvalid <= 1'b0;
      s_axi_rdata <= '0;
      s_axi_rresp <= OKAY;
      s_axi_rvalid <= 1'b0;
    end else begin
      if (s_axi_awready && s_axi_awvalid) begin
        aw_pending_q <= 1'b1;
        awaddr_q <= s_axi_awaddr;
      end
      if (s_axi_wready && s_axi_wvalid) begin
        w_pending_q <= 1'b1;
        wdata_q <= s_axi_wdata;
        wstrb_q <= s_axi_wstrb;
      end
      if (aw_pending_q && w_pending_q && !s_axi_bvalid) begin
        s_axi_bvalid <= 1'b1;
        s_axi_bresp <= awaddr_q == 12'h040 ? OKAY : SLVERR;
        if (awaddr_q == 12'h040)
          for (i = 0; i < 4; i = i + 1)
            if (wstrb_q[i])
              scratch_q[8*i +: 8] <= wdata_q[8*i +: 8];
        aw_pending_q <= 1'b0;
        w_pending_q <= 1'b0;
      end
      if (s_axi_bvalid && s_axi_bready)
        s_axi_bvalid <= 1'b0;
      if (s_axi_arready && s_axi_arvalid) begin
        s_axi_rvalid <= 1'b1;
        s_axi_rdata <= read_data;
        s_axi_rresp <= read_valid ? OKAY : SLVERR;
      end
      if (s_axi_rvalid && s_axi_rready)
        s_axi_rvalid <= 1'b0;
    end
  end
endmodule
