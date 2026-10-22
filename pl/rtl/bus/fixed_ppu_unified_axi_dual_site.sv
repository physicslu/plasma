// Fixed PPU ABI v1 — Host-only 64 KiB unified AXI4-Lite slave.
// Two physically instantiated, independent SWD Sites + RO Global Identity.
// No FPGA build, pin constraints, actual UIO, SPI, PS integration or DUT IO.
// AW and W are paired by the router and delivered to ONLY the same slave;
// reads are independent, with one in-flight read and one write at a time.
// All absent sites/reserved regions return SLVERR without downstream access.
module fixed_ppu_unified_axi_dual_site #(
    parameter logic [31:0] PPU_BASE = 32'h40000000
) (
    input logic s_axi_aclk, s_axi_aresetn,
    input logic [31:0] s_axi_awaddr,
    input logic [2:0] s_axi_awprot,
    input logic s_axi_awvalid,
    output logic s_axi_awready,
    input logic [31:0] s_axi_wdata,
    input logic [3:0] s_axi_wstrb,
    input logic s_axi_wvalid,
    output logic s_axi_wready,
    output logic [1:0] s_axi_bresp,
    output logic s_axi_bvalid,
    input logic s_axi_bready,
    input logic [31:0] s_axi_araddr,
    input logic [2:0] s_axi_arprot,
    input logic s_axi_arvalid,
    output logic s_axi_arready,
    output logic [31:0] s_axi_rdata,
    output logic [1:0] s_axi_rresp,
    output logic s_axi_rvalid,
    input logic s_axi_rready,
    input logic [1:0] swdio_in,
    output logic [1:0] swclk, swdio_out, swdio_oe
);
    localparam logic [1:0] OKAY=2'b00, SLVERR=2'b10;
    localparam logic [1:0] W_COLLECT=0, W_SEND=1, W_RESP=2, W_ERROR=3;
    localparam logic [1:0] R_IDLE=0, R_SEND=1, R_RESP=2, R_ERROR=3;
    logic [1:0] wr_state, rd_state;
    logic aw_saved, w_saved, aw_sent, w_sent;
    logic [31:0] aw_addr_q, w_data_q, wr_addr_q, rd_addr_q;
    logic [3:0] w_strb_q, wr_strb_q;
    logic [31:0] wr_data_q;
    logic [1:0] wr_sel, rd_sel;
    wire aw_take = s_axi_awvalid && s_axi_awready;
    wire w_take  = s_axi_wvalid && s_axi_wready;
    wire ar_take = s_axi_arvalid && s_axi_arready;
    wire [31:0] paired_aw = aw_take ? s_axi_awaddr : aw_addr_q;
    wire [31:0] paired_wdata = w_take ? s_axi_wdata : w_data_q;
    wire [3:0] paired_strb = w_take ? s_axi_wstrb : w_strb_q;

    // Fixed ABI v1: Global 0x0000, Site1 0x4000, Site2 0x5000.
    // Sites 3..8 remain absent and reject writes/reads with SLVERR.
    function automatic logic in_global(input logic [31:0] addr);
        in_global = addr >= PPU_BASE && (addr - PPU_BASE) < 32'h2000;
    endfunction
    function automatic logic in_site1(input logic [31:0] addr);
        in_site1 = addr >= PPU_BASE && (addr - PPU_BASE) >= 32'h4000 &&
                   (addr - PPU_BASE) < 32'h5000;
    endfunction
    function automatic logic in_site2(input logic [31:0] addr);
        in_site2 = addr >= PPU_BASE && (addr - PPU_BASE) >= 32'h5000 &&
                   (addr - PPU_BASE) < 32'h6000;
    endfunction
    function automatic logic [1:0] select_child(input logic [31:0] addr);
        select_child = in_site2(addr) ? 2'd2 : in_site1(addr) ? 2'd1 : 2'd0;
    endfunction
    wire [2:0] aw_valid_child, w_valid_child, child_bvalid;
    wire [2:0] child_awready, child_wready;
    wire [1:0] child_bresp [0:2];
    wire [2:0] ar_valid_child, child_arready, child_rvalid;
    wire [1:0] child_rresp [0:2];
    wire [31:0] child_rdata [0:2];
    wire [2:0] child_bready, child_rready;

    assign s_axi_awready = s_axi_aresetn && wr_state==W_COLLECT && !aw_saved;
    assign s_axi_wready  = s_axi_aresetn && wr_state==W_COLLECT && !w_saved;
    assign s_axi_arready = s_axi_aresetn && rd_state==R_IDLE;
    for (genvar child = 0; child < 3; child = child + 1) begin : route_child
        assign aw_valid_child[child] = wr_state==W_SEND &&
                                      wr_sel==child && !aw_sent;
        assign w_valid_child[child] = wr_state==W_SEND &&
                                     wr_sel==child && !w_sent;
        assign child_bready[child] = wr_state==W_RESP &&
                                     wr_sel==child && s_axi_bready;
        assign ar_valid_child[child] = rd_state==R_SEND && rd_sel==child;
        assign child_rready[child] = rd_state==R_RESP &&
                                     rd_sel==child && s_axi_rready;
    end

    assign s_axi_bvalid = wr_state==W_ERROR ? 1'b1 :
                          wr_state==W_RESP ? child_bvalid[wr_sel] : 1'b0;
    assign s_axi_bresp  = wr_state==W_ERROR ? SLVERR :
                          wr_state==W_RESP ? child_bresp[wr_sel] : OKAY;
    assign s_axi_rvalid = rd_state==R_ERROR ? 1'b1 :
                          rd_state==R_RESP ? child_rvalid[rd_sel] : 1'b0;
    assign s_axi_rresp  = rd_state==R_ERROR ? SLVERR :
                          rd_state==R_RESP ? child_rresp[rd_sel] : OKAY;
    assign s_axi_rdata  = rd_state==R_RESP ? child_rdata[rd_sel] : 32'd0;

    wire [1:0] site_ready, site_fault;
    fixed_fpga_ppu_global_identity_axi_lite #(
        .AXI_BASE_ADDRESS(PPU_BASE),
        .SITE_PRESENT(8'h03),
        .CAPABILITIES_LO(32'd1),
        .MAX_TRANSFER_BITS(32'd64)
    ) ppu_global (
        .s_axi_aclk(s_axi_aclk), .s_axi_aresetn(s_axi_aresetn),
        .s_axi_awaddr(wr_addr_q), .s_axi_awprot(3'd0),
        .s_axi_awvalid(aw_valid_child[0]), .s_axi_awready(child_awready[0]),
        .s_axi_wdata(wr_data_q), .s_axi_wstrb(wr_strb_q),
        .s_axi_wvalid(w_valid_child[0]), .s_axi_wready(child_wready[0]),
        .s_axi_bresp(child_bresp[0]), .s_axi_bvalid(child_bvalid[0]),
        .s_axi_bready(child_bready[0]),
        .s_axi_araddr(rd_addr_q), .s_axi_arprot(3'd0),
        .s_axi_arvalid(ar_valid_child[0]), .s_axi_arready(child_arready[0]),
        .s_axi_rdata(child_rdata[0]), .s_axi_rresp(child_rresp[0]),
        .s_axi_rvalid(child_rvalid[0]), .s_axi_rready(child_rready[0]),
        .site_ready_i({6'd0, site_ready}), .site_fault_i({6'd0, site_fault}),
        .pl_ready_i(s_axi_aresetn)
    );
    fixed_fpga_swd_site_axi_lite #(
        .AXI_BASE_ADDRESS(PPU_BASE + 32'h4000), .SITE_ID(32'd1)
    ) site1 (
        .s_axi_aclk(s_axi_aclk), .s_axi_aresetn(s_axi_aresetn),
        .s_axi_awaddr(wr_addr_q), .s_axi_awprot(3'd0),
        .s_axi_awvalid(aw_valid_child[1]), .s_axi_awready(child_awready[1]),
        .s_axi_wdata(wr_data_q), .s_axi_wstrb(wr_strb_q),
        .s_axi_wvalid(w_valid_child[1]), .s_axi_wready(child_wready[1]),
        .s_axi_bresp(child_bresp[1]), .s_axi_bvalid(child_bvalid[1]),
        .s_axi_bready(child_bready[1]),
        .s_axi_araddr(rd_addr_q), .s_axi_arprot(3'd0),
        .s_axi_arvalid(ar_valid_child[1]), .s_axi_arready(child_arready[1]),
        .s_axi_rdata(child_rdata[1]), .s_axi_rresp(child_rresp[1]),
        .s_axi_rvalid(child_rvalid[1]), .s_axi_rready(child_rready[1]),
        .swdio_in(swdio_in[0]), .swclk(swclk[0]), .swdio_out(swdio_out[0]),
        .swdio_oe(swdio_oe[0]), .site_ready_o(site_ready[0]),
        .site_fault_o(site_fault[0])
    );
    fixed_fpga_swd_site_axi_lite #(
        .AXI_BASE_ADDRESS(PPU_BASE + 32'h5000), .SITE_ID(32'd2)
    ) site2 (
        .s_axi_aclk(s_axi_aclk), .s_axi_aresetn(s_axi_aresetn),
        .s_axi_awaddr(wr_addr_q), .s_axi_awprot(3'd0),
        .s_axi_awvalid(aw_valid_child[2]), .s_axi_awready(child_awready[2]),
        .s_axi_wdata(wr_data_q), .s_axi_wstrb(wr_strb_q),
        .s_axi_wvalid(w_valid_child[2]), .s_axi_wready(child_wready[2]),
        .s_axi_bresp(child_bresp[2]), .s_axi_bvalid(child_bvalid[2]),
        .s_axi_bready(child_bready[2]),
        .s_axi_araddr(rd_addr_q), .s_axi_arprot(3'd0),
        .s_axi_arvalid(ar_valid_child[2]), .s_axi_arready(child_arready[2]),
        .s_axi_rdata(child_rdata[2]), .s_axi_rresp(child_rresp[2]),
        .s_axi_rvalid(child_rvalid[2]), .s_axi_rready(child_rready[2]),
        .swdio_in(swdio_in[1]), .swclk(swclk[1]), .swdio_out(swdio_out[1]),
        .swdio_oe(swdio_oe[1]), .site_ready_o(site_ready[1]),
        .site_fault_o(site_fault[1])
    );

    always_ff @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            wr_state<=W_COLLECT; rd_state<=R_IDLE;
            aw_saved<=0; w_saved<=0; aw_sent<=0; w_sent<=0;
            aw_addr_q<=0; w_data_q<=0; w_strb_q<=0;
            wr_addr_q<=0; wr_data_q<=0; wr_strb_q<=0;
            wr_sel<=0; rd_sel<=0; rd_addr_q<=0;
        end else begin
            case (wr_state)
                W_COLLECT: begin
                    if (aw_take) begin aw_saved<=1; aw_addr_q<=s_axi_awaddr; end
                    if (w_take) begin
                        w_saved<=1; w_data_q<=s_axi_wdata; w_strb_q<=s_axi_wstrb;
                    end
                    if ((aw_saved || aw_take) && (w_saved || w_take)) begin
                        aw_saved<=0; w_saved<=0;
                        wr_addr_q<=paired_aw; wr_data_q<=paired_wdata;
                        wr_strb_q<=paired_strb;
                        aw_sent<=0; w_sent<=0;
                        wr_sel<=select_child(paired_aw);
                        wr_state<=in_global(paired_aw) || in_site1(paired_aw) || in_site2(paired_aw)
                                 ? W_SEND : W_ERROR;
                    end
                end
                W_SEND: begin
                    if (!aw_sent && child_awready[wr_sel]) aw_sent<=1;
                    if (!w_sent && child_wready[wr_sel]) w_sent<=1;
                    if ((aw_sent || child_awready[wr_sel]) &&
                        (w_sent || child_wready[wr_sel]))
                        wr_state<=W_RESP;
                end
                W_RESP: if (child_bvalid[wr_sel] && s_axi_bready)
                    wr_state<=W_COLLECT;
                W_ERROR: if (s_axi_bready) wr_state<=W_COLLECT;
                default: wr_state<=W_COLLECT;
            endcase
            case (rd_state)
                R_IDLE: if (ar_take) begin
                    rd_addr_q<=s_axi_araddr;
                    rd_sel<=select_child(s_axi_araddr);
                    rd_state<=in_global(s_axi_araddr)||in_site1(s_axi_araddr)||in_site2(s_axi_araddr)
                              ? R_SEND : R_ERROR;
                end
                R_SEND: if (child_arready[rd_sel]) rd_state<=R_RESP;
                R_RESP: if (child_rvalid[rd_sel] && s_axi_rready) rd_state<=R_IDLE;
                R_ERROR: if (s_axi_rready) rd_state<=R_IDLE;
                default: rd_state<=R_IDLE;
            endcase
        end
    end
endmodule
