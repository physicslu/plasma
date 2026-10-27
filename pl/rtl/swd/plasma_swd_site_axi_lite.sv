// PLASMA reusable ONE-SITE SWD AXI4-Lite IP, Gate 1 RTL candidate.
// Each instance owns one independent AXI slave, SWD FSM, registers and pads.
// No MPE-wide register decoder, no Site manager, no legacy WordPort transport.
// NORMAL (mode=1): FPGA autonomous SWD transaction.
// DEBUG (mode=2): guarded per-bit pad writes for a *version-qualified*
// OpenOCD SWD remote_bitbang Bridge. OpenOCD 0.12.0 is JTAG-only: NOT qualified.
// DISABLED (mode=0): SWCLK low, SWDIO Hi-Z. NORMAL and DEBUG never drive
// simultaneously. Does not control target power or reset.
//
// Candidate Normal SWD HW ceiling 12.5MHz (N>=4 @100MHz); NOT HIL qualified.
// Software must independently qualify the DUT/Profile's usable SWD clock.
// Single in-flight command + one retained completion, NOT a 16-deep FIFO.
// Registers (relative to this Site's own independent 4-KiB AXI address):
// 00 SITE_ID_CAP 04 STATUS 08 HALF_PERIOD 0C TIMEOUT 10 TX_DATA
// 14 CMD_PUSH 18 COMPLETION_META 1C DATA 20 TAGGED_POP 24 LEVELS
// 28 NORMAL_CONTROL 2C ERROR_LATCH 30 IRQ_ENABLE 34 IRQ_LEVEL
// 38 MODE (0 disabled,1 normal,2 debug) 3C DEBUG_DRIVE (bit0 CLK,
// bit1 DOUT, bit2 OE), 40 DEBUG_SAMPLE (bit0 DIN, debug-only).
// All writes full word WSTRB=F; invalid/forbidden reads/writes -> SLVERR.
// No live DUT/HIL or Vivado results asserted by synthesizable source.
module plasma_swd_site_axi_lite #(
    parameter integer SITE_ID = 1,
    parameter logic [31:0] SITE_BASE_ADDRESS = 32'h43C01000
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aclk, ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET s_axi_aresetn, FREQ_HZ 100000000" *)
    input logic s_axi_aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 s_axi_aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aresetn, POLARITY ACTIVE_LOW" *)
    input logic s_axi_aresetn,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWADDR" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 32, FREQ_HZ 100000000" *)
    input logic [31:0] s_axi_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *)
    input logic [2:0] s_axi_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *)
    input logic s_axi_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *)
    input logic [31:0] s_axi_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *)
    input logic [3:0] s_axi_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *)
    input logic s_axi_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *)
    input logic s_axi_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *)
    input logic [31:0] s_axi_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *)
    input logic [2:0] s_axi_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *)
    input logic s_axi_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RREADY" *)
    input logic s_axi_rready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *)
    output wire s_axi_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *)
    output wire s_axi_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *)
    output logic [1:0] s_axi_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *)
    output logic s_axi_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *)
    output wire s_axi_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *)
    output logic [31:0] s_axi_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *)
    output logic [1:0] s_axi_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *)
    output logic s_axi_rvalid,
    output wire swclk_io,
    inout wire swdio_io,
    output wire site_irq
);
    localparam logic [1:0] OKAY=2'b00, SLVERR=2'b10;
    // Per-Site dynamic divider: N >= 4 => 12.5MHz candidate hardware max.
    // Target-qualified working speed is a separate PS/Programming Profile gate.
    localparam logic [15:0] MIN_HALF_PERIOD = 16'd4;
    localparam logic [1:0] MODE_OFF=2'd0, MODE_NORMAL=2'd1,
                           MODE_DEBUG=2'd2;
    logic aw_hold, w_hold;
    logic [31:0] aw_q, wd_q;
    logic [3:0] strobe_q;
    wire take_aw = s_axi_awvalid && s_axi_awready;
    wire take_w = s_axi_wvalid && s_axi_wready;
    wire take_ar = s_axi_arvalid && s_axi_arready;
    wire [31:0] addr_w = take_aw ? s_axi_awaddr : aw_q;
    wire [31:0] data_w = take_w ? s_axi_wdata : wd_q;
    wire [3:0] strb_w = take_w ? s_axi_wstrb : strobe_q;
    wire commit = !s_axi_bvalid && (aw_hold || take_aw) && (w_hold || take_w);
    assign s_axi_awready = s_axi_aresetn && !aw_hold && !s_axi_bvalid;
    assign s_axi_wready = s_axi_aresetn && !w_hold && !s_axi_bvalid;
    assign s_axi_arready = s_axi_aresetn && !s_axi_rvalid;

    logic [1:0] mode_q;
    logic normal_enable_q, launch_q, abort_q, consume_q, fault_q, irq_enable_q;
    logic debug_clk_q, debug_out_q, debug_oe_q;
    logic [15:0] half_q, active_tag;
    logic [31:0] timeout_q, data_q;
    logic [8:0] command_q;

    wire cmd_ready, busy, resp_valid, resp_data_valid;
    wire [3:0] resp_status;
    wire [2:0] resp_ack;
    wire [31:0] resp_data;
    wire [8:0] resp_attempts;
    wire [1:0] link_state;
    wire engine_clk, engine_out, engine_oe, swdio_in;
    wire normal_pad = s_axi_aresetn && (mode_q == MODE_NORMAL) &&
                      normal_enable_q;
    wire debug_pad = s_axi_aresetn && (mode_q == MODE_DEBUG);
    wire drive_oe = (normal_pad && engine_oe) ||
                    (debug_pad && debug_oe_q);
    wire drive_out = debug_pad ? debug_out_q : engine_out;
    wire drive_clk = (normal_pad && engine_clk) ||
                     (debug_pad && debug_clk_q);

    OBUF u_swclk (.I(drive_clk), .O(swclk_io));
    IOBUF u_swdio (.I(drive_out), .T(!drive_oe), .O(swdio_in),
                    .IO(swdio_io));
    assign site_irq = (mode_q == MODE_NORMAL) && irq_enable_q && resp_valid;

    plasma_swd_transaction_engine u_transaction (
        .clk(s_axi_aclk), .rst_n(s_axi_aresetn),
        .cmd_abort(abort_q || !normal_enable_q || mode_q != MODE_NORMAL),
        .cmd_valid(launch_q), .cmd_ready(cmd_ready),
        .cmd_op(command_q[8]), .cmd_ap(command_q[0]),
        .cmd_read(command_q[1]),
        .cmd_addr({command_q[3:2],2'b00}), .cmd_wdata(data_q),
        .cmd_half_period(half_q), .cmd_turnaround(3'd1),
        .cmd_idle_cycles(8'd8), .cmd_max_retries(8'd0),
        .cmd_error_data_phase(1'b0), .cmd_timeout_cycles(timeout_q),
        .busy(busy), .link_state(link_state),
        .resp_valid(resp_valid), .resp_ready(consume_q),
        .resp_status(resp_status), .resp_ack(resp_ack),
        .resp_rdata(resp_data), .resp_data_valid(resp_data_valid),
        .resp_attempts(resp_attempts), .swdio_in(swdio_in),
        .swclk(engine_clk), .swdio_out(engine_out), .swdio_oe(engine_oe)
    );

    function automatic logic in_window(input logic [31:0] addr);
        in_window = addr[31:12] == SITE_BASE_ADDRESS[31:12] &&
                    addr[11:8] == 4'd0 && addr[7:6] <= 2'b01 &&
                    addr[1:0] == 2'b00;
    endfunction

    always_ff @(posedge s_axi_aclk) begin : registers
        if (!s_axi_aresetn) begin
            aw_hold <= 1'b0; w_hold <= 1'b0;
            aw_q <= 32'd0; wd_q <= 32'd0; strobe_q <= 4'd0;
            s_axi_bvalid <= 1'b0; s_axi_bresp <= OKAY;
            s_axi_rvalid <= 1'b0; s_axi_rresp <= OKAY;
            s_axi_rdata <= 32'd0;
            mode_q <= MODE_OFF;
            normal_enable_q <= 1'b0;
            launch_q <= 1'b0; abort_q <= 1'b0; consume_q <= 1'b0;
            fault_q <= 1'b0; irq_enable_q <= 1'b0;
            debug_clk_q <= 1'b0; debug_out_q <= 1'b0;
            debug_oe_q <= 1'b0;
            half_q <= 16'd500; timeout_q <= 32'd1000000;
            data_q <= 32'd0; command_q <= 9'd0; active_tag <= 16'd0;
        end else begin
            launch_q <= 1'b0; abort_q <= 1'b0; consume_q <= 1'b0;
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 1'b0;
            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 1'b0;
            if (take_aw) begin
                aw_hold <= 1'b1; aw_q <= s_axi_awaddr;
            end
            if (take_w) begin
                w_hold <= 1'b1; wd_q <= s_axi_wdata; strobe_q <= s_axi_wstrb;
            end
            if (resp_valid &&
                (resp_status == 4'd6 || resp_status == 4'd7 ||
                 resp_status == 4'd8))
                fault_q <= 1'b1;
            if (commit) begin
                aw_hold <= 1'b0; w_hold <= 1'b0;
                s_axi_bvalid <= 1'b1; s_axi_bresp <= SLVERR;
                if (strb_w == 4'hF && in_window(addr_w)) begin
                    case (addr_w[7:0])
                        8'h08: if (mode_q == MODE_NORMAL && !busy &&
                                   !resp_valid && !launch_q &&
                                   data_w[31:16] == 0 && data_w[15:0] >= MIN_HALF_PERIOD) begin
                            half_q <= data_w[15:0]; s_axi_bresp <= OKAY;
                        end
                        8'h0C: if (mode_q == MODE_NORMAL && !busy &&
                                   !resp_valid && !launch_q && data_w != 0) begin
                            timeout_q <= data_w; s_axi_bresp <= OKAY;
                        end
                        8'h10: if (mode_q == MODE_NORMAL && !busy &&
                                   !resp_valid && !launch_q) begin
                            data_q <= data_w; s_axi_bresp <= OKAY;
                        end
                        8'h14: if (mode_q == MODE_NORMAL && normal_enable_q &&
                                   !fault_q && cmd_ready && !launch_q &&
                                   data_w[31:16] != 0 &&
                                   data_w[15:9] == 0 && data_w[7:4] == 0 &&
                                   (data_w[8] == 0 || data_w[7:0] == 0)) begin
                            active_tag <= data_w[31:16];
                            command_q <= {data_w[8],data_w[7:0]};
                            launch_q <= 1'b1; s_axi_bresp <= OKAY;
                        end
                        8'h20: if (mode_q == MODE_NORMAL && resp_valid &&
                                   data_w == {16'd0,active_tag} &&
                                   !consume_q) begin
                            consume_q <= 1'b1; s_axi_bresp <= OKAY;
                        end
                        8'h28: if (mode_q == MODE_NORMAL &&
                                   data_w[31:2] == 0 &&
                                   !(data_w[1] && !busy)) begin
                            normal_enable_q <= data_w[0];
                            abort_q <= data_w[1]; s_axi_bresp <= OKAY;
                        end
                        8'h30: if (mode_q == MODE_NORMAL &&
                                   data_w[31:1] == 0) begin
                            irq_enable_q <= data_w[0]; s_axi_bresp <= OKAY;
                        end
                        8'h38: if (data_w[31:2] == 0 &&
                                   data_w[1:0] != 2'd3 &&
                                   !busy && !resp_valid && !launch_q &&
                                   !normal_enable_q &&
                                   !debug_oe_q && !debug_clk_q) begin
                            mode_q <= data_w[1:0]; s_axi_bresp <= OKAY;
                        end
                        8'h3C: if (mode_q == MODE_DEBUG &&
                                   data_w[31:3] == 0 &&
                                   // SWDIO data/OE may only change while
                                   // SWCLK is low both before and after
                                   // the MMIO write, avoiding simultaneous
                                   // rising-clock/data-direction updates.
                                   ((!debug_clk_q && !data_w[0]) ||
                                    data_w[2:1] ==
                                        {debug_oe_q,debug_out_q})) begin
                            debug_clk_q <= data_w[0];
                            debug_out_q <= data_w[1];
                            debug_oe_q <= data_w[2];
                            s_axi_bresp <= OKAY;
                        end
                        default: s_axi_bresp <= SLVERR;
                    endcase
                end
            end
            if (take_ar) begin
                s_axi_rvalid <= 1'b1; s_axi_rresp <= SLVERR;
                s_axi_rdata <= 32'd0;
                if (in_window(s_axi_araddr)) begin
                    case (s_axi_araddr[7:0])
                        8'h00: begin
                            s_axi_rdata <= 32'h00020000 | SITE_ID;
                            s_axi_rresp <= OKAY;
                        end
                        8'h04: begin
                            s_axi_rdata <= {26'd0,mode_q, fault_q,
                                            resp_valid,busy,normal_enable_q};
                            s_axi_rresp <= OKAY;
                        end
                        8'h08: begin
                            s_axi_rdata <= {16'd0,half_q}; s_axi_rresp <= OKAY;
                        end
                        8'h0C: begin
                            s_axi_rdata <= timeout_q; s_axi_rresp <= OKAY;
                        end
                        8'h18: if (mode_q == MODE_NORMAL) begin
                            s_axi_rdata <= {active_tag,2'd0,link_state,
                                resp_attempts[3:0],resp_data_valid,
                                resp_ack,resp_status};
                            s_axi_rresp <= OKAY;
                        end
                        8'h1C: if (mode_q == MODE_NORMAL) begin
                            s_axi_rdata <= resp_data; s_axi_rresp <= OKAY;
                        end
                        8'h24: begin
                            s_axi_rdata <= {30'd0,resp_valid,1'b0};
                            s_axi_rresp <= OKAY;
                        end
                        8'h28: begin
                            s_axi_rdata <= {31'd0,normal_enable_q};
                            s_axi_rresp <= OKAY;
                        end
                        8'h2C: begin
                            s_axi_rdata <= {31'd0,fault_q}; s_axi_rresp <= OKAY;
                        end
                        8'h30: begin
                            s_axi_rdata <= {31'd0,irq_enable_q};
                            s_axi_rresp <= OKAY;
                        end
                        8'h34: begin
                            s_axi_rdata <= {31'd0,site_irq}; s_axi_rresp <= OKAY;
                        end
                        8'h38: begin
                            s_axi_rdata <= {30'd0,mode_q}; s_axi_rresp <= OKAY;
                        end
                        8'h3C: if (mode_q == MODE_DEBUG) begin
                            s_axi_rdata <= {29'd0,debug_oe_q,
                                debug_out_q,debug_clk_q};
                            s_axi_rresp <= OKAY;
                        end
                        8'h40: if (mode_q == MODE_DEBUG) begin
                            s_axi_rdata <= {31'd0,swdio_in};
                            s_axi_rresp <= OKAY;
                        end
                        default: s_axi_rresp <= SLVERR;
                    endcase
                end
            end
        end
    end
endmodule
