// PSPL-02: isolated AXI4-Lite read/write loopback peripheral.
// 0x00 CONTROL is byte-writeable; 0x04 STATUS = CONTROL ^ 0xA5A55A5A.
// No external pins, SWD activity, target power, or side effects.
module pl_control_axi_lite #(
    parameter logic [31:0] AXI_BASE_ADDRESS = 32'h40001000
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
    input  logic         s_axi_rready,
    output logic [31:0]  control_value
);
    logic aw_pending;
    logic w_pending;
    logic [31:0] aw_addr_q;
    logic [31:0] w_data_q;
    logic [3:0]  w_strb_q;

    wire accept_aw = s_axi_awvalid && s_axi_awready;
    wire accept_w  = s_axi_wvalid  && s_axi_wready;
    wire accept_ar = s_axi_arvalid && s_axi_arready;

    wire [31:0] write_addr = accept_aw ? s_axi_awaddr : aw_addr_q;
    wire [31:0] write_data = accept_w  ? s_axi_wdata  : w_data_q;
    wire [3:0]  write_strb = accept_w  ? s_axi_wstrb  : w_strb_q;

    assign s_axi_awready = s_axi_aresetn && !aw_pending && !s_axi_bvalid;
    assign s_axi_wready  = s_axi_aresetn && !w_pending && !s_axi_bvalid;
    assign s_axi_arready = s_axi_aresetn && !s_axi_rvalid;

    always_ff @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            aw_pending    <= 1'b0;
            w_pending     <= 1'b0;
            aw_addr_q     <= '0;
            w_data_q      <= '0;
            w_strb_q      <= '0;
            control_value <= '0;
            s_axi_bresp   <= 2'b00;
            s_axi_bvalid  <= 1'b0;
            s_axi_rresp   <= 2'b00;
            s_axi_rdata   <= '0;
            s_axi_rvalid  <= 1'b0;
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
            if (!s_axi_bvalid && (aw_pending || accept_aw) &&
                (w_pending || accept_w)) begin
                aw_pending <= 1'b0;
                w_pending  <= 1'b0;
                s_axi_bvalid <= 1'b1;
                if (write_addr == AXI_BASE_ADDRESS) begin
                    s_axi_bresp <= 2'b00; // OKAY; WSTRB=0 is a no-op.
                    for (int lane = 0; lane < 4; lane++) begin
                        if (write_strb[lane])
                            control_value[8*lane +: 8] <= write_data[8*lane +: 8];
                    end
                end else begin
                    // STATUS and every other offset are read-only/invalid.
                    s_axi_bresp <= 2'b10; // SLVERR
                end
            end

            if (s_axi_rvalid && s_axi_rready)
                s_axi_rvalid <= 1'b0;
            if (accept_ar) begin
                s_axi_rvalid <= 1'b1;
                s_axi_rresp  <= 2'b00;
                case (s_axi_araddr)
                    AXI_BASE_ADDRESS:
                        s_axi_rdata <= control_value;
                    (AXI_BASE_ADDRESS + 32'd4):
                        s_axi_rdata <= control_value ^ 32'hA5A55A5A;
                    default: begin
                        s_axi_rdata <= '0;
                        s_axi_rresp <= 2'b10; // SLVERR
                    end
                endcase
            end
        end
    end
endmodule
