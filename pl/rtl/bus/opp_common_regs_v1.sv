// OPP Common Register v1 candidate: isolated register slave, NOT wired to SWD v5.
// Host supplies verified build/image words; no protocol or DUT pins are touched.
module opp_common_regs_v1 #(
  parameter logic [31:0] IMAGE_ID_W0 = 32'h0,
  parameter logic [31:0] BUILD_ID_W0 = 32'h0,
  parameter logic [31:0] CAPABILITIES_LO = 32'h0,
  parameter logic [31:0] SITE_PRESENT = 32'h0
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
        8'h08: begin rdata_o = IMAGE_ID_W0; valid_o = 1'b1; end
        8'h18: begin rdata_o = BUILD_ID_W0; valid_o = 1'b1; end
        8'h28: begin rdata_o = CAPABILITIES_LO; valid_o = 1'b1; end
        8'h30: begin rdata_o = SITE_PRESENT; valid_o = 1'b1; end
        SCRATCH_ADDR: begin rdata_o = scratch_q; valid_o = 1'b1; end
        default: ;
      endcase
    end else if (write_i && addr_i == SCRATCH_ADDR) begin
      valid_o = 1'b1;
    end
  end
endmodule
