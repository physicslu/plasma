// OPP Common Register v1 candidate: isolated register slave, NOT wired to SWD v5.
// This is a DISTINCT common-register aperture, never an SWD Site-v5 aperture.
// SWD v5 offsets 0x3c/0x40 remain forbidden; no protocol or DUT pins are touched.
module opp_common_regs_v1 #(
  parameter logic [127:0] IMAGE_ID = 128'h0,
  parameter logic [127:0] BUILD_ID = 128'h0,
  parameter logic [63:0] CAPABILITIES = 64'h0,
  parameter logic [31:0] SITE_PRESENT = 32'h0,
  parameter logic [31:0] SITE_READY = 32'h0,
  parameter logic [31:0] PPU_STATUS = 32'h0,
  parameter logic [31:0] HW_REVISION = 32'h0
) (
  input  logic        clk_i,
  input  logic        rst_ni,
  input  logic        read_i,
  input  logic        write_i,
  input  logic [7:0]  addr_i,
  input  logic [31:0] wdata_i,
  output logic [31:0] rdata_o,
  output logic        valid_o
);
  localparam logic [31:0] MAGIC = 32'h4d534c50;
  localparam logic [31:0] ABI_VERSION = 32'h00010000;
  localparam logic [7:0] SCRATCH_ADDR = 8'h40; // candidate only; not a deployed MMIO offset
  logic [31:0] scratch_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) scratch_q <= 32'h0;
    else if (write_i && addr_i == SCRATCH_ADDR) scratch_q <= wdata_i;
  end

  always_comb begin
    rdata_o = 32'h0;
    valid_o = 1'b0;
    if (read_i) begin
      unique case (addr_i)
        8'h00: begin rdata_o = MAGIC; valid_o = 1'b1; end
        8'h04: begin rdata_o = ABI_VERSION; valid_o = 1'b1; end
        8'h08: begin rdata_o = IMAGE_ID[31:0]; valid_o = 1'b1; end
        8'h0c: begin rdata_o = IMAGE_ID[63:32]; valid_o = 1'b1; end
        8'h10: begin rdata_o = IMAGE_ID[95:64]; valid_o = 1'b1; end
        8'h14: begin rdata_o = IMAGE_ID[127:96]; valid_o = 1'b1; end
        8'h18: begin rdata_o = BUILD_ID[31:0]; valid_o = 1'b1; end
        8'h1c: begin rdata_o = BUILD_ID[63:32]; valid_o = 1'b1; end
        8'h20: begin rdata_o = BUILD_ID[95:64]; valid_o = 1'b1; end
        8'h24: begin rdata_o = BUILD_ID[127:96]; valid_o = 1'b1; end
        8'h28: begin rdata_o = CAPABILITIES[31:0]; valid_o = 1'b1; end
        8'h2c: begin rdata_o = CAPABILITIES[63:32]; valid_o = 1'b1; end
        8'h30: begin rdata_o = SITE_PRESENT; valid_o = 1'b1; end
        8'h34: begin rdata_o = SITE_READY; valid_o = 1'b1; end
        8'h38: begin rdata_o = PPU_STATUS; valid_o = 1'b1; end
        8'h3c: begin rdata_o = HW_REVISION; valid_o = 1'b1; end
        SCRATCH_ADDR: begin rdata_o = scratch_q; valid_o = 1'b1; end
        default: ;
      endcase
    end else if (write_i && addr_i == SCRATCH_ADDR) begin
      valid_o = 1'b1;
    end
  end
endmodule
