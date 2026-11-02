// PLASMA reusable ONE-SITE SWD AXI4-Lite IP, Gate 1 RTL candidate.
// Each instance owns one independent AXI slave, SWD FSM, registers and pads.
// No MPE-wide register decoder, no Site manager, no legacy WordPort transport.
// NORMAL (mode=1): FPGA autonomous SWD transactions.
// DISABLED (mode=0): SWCLK low, SWDIO Hi-Z; no SWD Debug Bitbang path.
// A future multi-protocol GPIO Bus is a separate proposed IP, NOT instantiated.
// No target power or reset control.
//
// Candidate Normal SWD HW ceiling 12.5MHz (N>=4 @100MHz); NOT HIL qualified.
// Software must independently qualify the DUT/Profile's usable SWD clock.
// Each IP has its own 16-entry command and completion FIFOs. Commands latch
// all parameters at acceptance; completion tags/data remain immutable until
// a matching tagged POP. Neither queue is shared across Sites.
// Registers (relative to this Site's own independent 4-KiB AXI address):
// 00 SITE_ID_CAP 04 STATUS 08 HALF_PERIOD 0C TIMEOUT 10 TX_DATA
// 14 CMD_PUSH 18 COMPLETION_META 1C DATA 20 TAGGED_POP 24 LEVELS
// 28 NORMAL_CONTROL (bit2 fault-only pending-command discard)
// 2C ERROR_LATCH (RW1C) 30 IRQ_ENABLE 34 IRQ_PENDING (RW1C)
// 38 MODE (0 disabled, 1 normal; all other values invalid).
// 3C/40 retired diagnostic offsets; reads/writes always SLVERR.
// 44..60 SWJ_DATA0..7 (8 x 32-bit staging), 64 SWJ_LENGTH (0 or 33..256).
// SWJ_LENGTH=0 uses the old <=32-bit TX_DATA / 64-clock line-reset encoding.
// Extended SWJ snapshots all 256 bits on CMD_PUSH and disarms staging.
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
    localparam logic [1:0] MODE_OFF=2'd0, MODE_NORMAL=2'd1;
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
    logic normal_enable_q, abort_q, consume_q, fault_q, irq_enable_q;
    logic irq_pending_q;
    logic [15:0] half_q, active_tag;
    logic [31:0] timeout_q, data_q;
    logic [255:0] swj_stage_q;
    logic [8:0] swj_length_q;

    localparam integer FIFO_DEPTH = 16;
    typedef struct packed {
        logic [15:0] tag;
        logic [8:0] command;
        logic [31:0] data;
        logic [255:0] sequence_data;
        logic [8:0] sequence_bits;
        logic [15:0] half_period;
        logic [31:0] timeout;
    } command_entry_t;
    typedef struct packed {
        logic [15:0] tag;
        logic [3:0] status;
        logic [2:0] ack;
        logic [31:0] data;
        logic data_valid;
        logic [8:0] attempts;
        logic [1:0] link;
    } response_entry_t;
    command_entry_t cmd_fifo [0:FIFO_DEPTH-1];
    response_entry_t resp_fifo [0:FIFO_DEPTH-1];
    // Icarus and Vivado both support packed records; select the memory word
    // first, then select struct fields (not a dynamic memory field select).
    command_entry_t cmd_head;
    response_entry_t resp_head;
    assign cmd_head = cmd_fifo[cmd_rd_q];
    assign resp_head = resp_fifo[resp_rd_q];
    logic [3:0] cmd_wr_q, cmd_rd_q, resp_wr_q, resp_rd_q;
    logic [4:0] cmd_level_q, resp_level_q;
    wire cmd_full = (cmd_level_q == 5'd16);
    wire resp_full = (resp_level_q == 5'd16);
    wire cmd_empty = (cmd_level_q == 5'd0);
    wire resp_empty = (resp_level_q == 5'd0);
    wire cmd_enqueue = commit && strb_w == 4'hF && in_window(addr_w) &&
        addr_w[7:0] == 8'h14 && mode_q == MODE_NORMAL &&
        normal_enable_q && !fault_q && !cmd_full &&
        data_w[31:16] != 0 && data_w[15:9] == 0 &&
        ((data_w[8] == 0 && data_w[7:4] == 0) ||
         (data_w[8] == 1 &&
          ((swj_length_q == 0 && data_w[7:0] <= 8'd32) ||
           (swj_length_q >= 9'd33 && swj_length_q <= 9'd256 &&
            data_w[7:0] == swj_length_q[7:0]))));
    wire cmd_dequeue = !cmd_empty && !resp_full &&
        mode_q == MODE_NORMAL && normal_enable_q && !fault_q && cmd_ready;
    // Fault recovery must never replay queued writes. Explicit discard leaves
    // retained completions intact, and callers must reconcile dropped tags.
    wire cmd_flush = commit && strb_w == 4'hF && in_window(addr_w) &&
        addr_w[7:0] == 8'h28 && data_w == 32'd4 &&
        mode_q == MODE_NORMAL && fault_q && !busy && !resp_valid;
    wire resp_enqueue = resp_valid && !consume_q && !resp_full;
    wire resp_dequeue = commit && strb_w == 4'hF && in_window(addr_w) &&
        addr_w[7:0] == 8'h20 && mode_q == MODE_NORMAL &&
        !resp_empty && data_w == {16'd0,resp_head.tag};

    wire cmd_ready, busy, resp_valid, resp_data_valid;
    wire [3:0] resp_status;
    wire [2:0] resp_ack;
    wire [31:0] resp_data;
    wire [8:0] resp_attempts;
    wire [1:0] link_state;
    wire engine_clk, engine_out, engine_oe, swdio_in;
    wire normal_pad = s_axi_aresetn && (mode_q == MODE_NORMAL) &&
                      normal_enable_q;
    wire drive_oe = normal_pad && engine_oe;
    wire drive_out = engine_out;
    wire drive_clk = normal_pad && engine_clk;

    OBUF u_swclk (.I(drive_clk), .O(swclk_io));
    IOBUF u_swdio (.I(drive_out), .T(!drive_oe), .O(swdio_in),
                    .IO(swdio_io));
    assign site_irq = (mode_q == MODE_NORMAL) && irq_enable_q && irq_pending_q;

    plasma_swd_transaction_engine u_transaction (
        .clk(s_axi_aclk), .rst_n(s_axi_aresetn),
        .cmd_abort(abort_q || !normal_enable_q || mode_q != MODE_NORMAL),
        .cmd_valid(cmd_dequeue), .cmd_ready(cmd_ready),
        .cmd_op(cmd_head.command[8]),
        .cmd_sequence_bits(cmd_head.sequence_bits),
        .cmd_sequence_data(cmd_head.sequence_data),
        .cmd_ap(cmd_head.command[0]),
        .cmd_read(cmd_head.command[1]),
        .cmd_addr({cmd_head.command[3:2],2'b00}),
        .cmd_wdata(cmd_head.data),
        .cmd_half_period(cmd_head.half_period),
        .cmd_turnaround(3'd1),
        .cmd_idle_cycles(8'd8), .cmd_max_retries(8'd0),
        .cmd_error_data_phase(1'b0),
        .cmd_timeout_cycles(cmd_head.timeout),
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
            abort_q <= 1'b0; consume_q <= 1'b0;
            fault_q <= 1'b0; irq_enable_q <= 1'b0;
            irq_pending_q <= 1'b0;
            cmd_wr_q <= 4'd0; cmd_rd_q <= 4'd0;
            resp_wr_q <= 4'd0; resp_rd_q <= 4'd0;
            cmd_level_q <= 5'd0; resp_level_q <= 5'd0;
            half_q <= 16'd500; timeout_q <= 32'd1000000;
            data_q <= 32'd0; active_tag <= 16'd0;
            swj_stage_q <= 256'd0; swj_length_q <= 9'd0;
        end else begin
            abort_q <= 1'b0; consume_q <= 1'b0;
            // A completion is copied into a separate retained response FIFO
            // before the engine is released. Backpressure halts dispatch when
            // the response FIFO is full; no result or write is replayed.
            if (cmd_enqueue) begin
                cmd_fifo[cmd_wr_q] <= {data_w[31:16],data_w[8:0],
                    data_q,
                    (swj_length_q != 0 ? swj_stage_q : {224'd0,data_q}),
                    (swj_length_q != 0 ? swj_length_q : {1'b0,data_w[7:0]}),
                    half_q,timeout_q};
                cmd_wr_q <= cmd_wr_q + 4'd1;
                if (data_w[8]) swj_length_q <= 9'd0;
            end
            if (cmd_dequeue) begin
                active_tag <= cmd_head.tag;
                cmd_rd_q <= cmd_rd_q + 4'd1;
            end
            if (cmd_flush) begin
                cmd_rd_q <= cmd_wr_q;
                cmd_level_q <= 5'd0;
            end else begin
                case ({cmd_enqueue,cmd_dequeue})
                    2'b10: cmd_level_q <= cmd_level_q + 5'd1;
                    2'b01: cmd_level_q <= cmd_level_q - 5'd1;
                    default: ;
                endcase
            end
            if (resp_enqueue) begin
                resp_fifo[resp_wr_q] <= {active_tag,resp_status,resp_ack,
                    resp_data,resp_data_valid,resp_attempts,link_state};
                resp_wr_q <= resp_wr_q + 4'd1;
                consume_q <= 1'b1;
                irq_pending_q <= 1'b1;
            end else begin
                consume_q <= 1'b0;
            end
            if (resp_dequeue) resp_rd_q <= resp_rd_q + 4'd1;
            case ({resp_enqueue,resp_dequeue})
                2'b10: resp_level_q <= resp_level_q + 5'd1;
                2'b01: resp_level_q <= resp_level_q - 5'd1;
                default: ;
            endcase
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 1'b0;
            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 1'b0;
            if (take_aw) begin
                aw_hold <= 1'b1; aw_q <= s_axi_awaddr;
            end
            if (take_w) begin
                w_hold <= 1'b1; wd_q <= s_axi_wdata; strobe_q <= s_axi_wstrb;
            end
            if (resp_enqueue &&
                (resp_status == 4'd6 || resp_status == 4'd7 ||
                 resp_status == 4'd8))
                fault_q <= 1'b1;
            if (commit) begin
                aw_hold <= 1'b0; w_hold <= 1'b0;
                s_axi_bvalid <= 1'b1; s_axi_bresp <= SLVERR;
                if (strb_w == 4'hF && in_window(addr_w)) begin
                    case (addr_w[7:0])
                        8'h08: if (mode_q == MODE_NORMAL &&
                                   data_w[31:16] == 0 && data_w[15:0] >= MIN_HALF_PERIOD) begin
                            half_q <= data_w[15:0]; s_axi_bresp <= OKAY;
                        end
                        8'h0C: if (mode_q == MODE_NORMAL && data_w != 0) begin
                            timeout_q <= data_w; s_axi_bresp <= OKAY;
                        end
                        8'h10: if (mode_q == MODE_NORMAL) begin
                            data_q <= data_w; s_axi_bresp <= OKAY;
                        end
                        8'h44: if (mode_q == MODE_NORMAL) begin
                            swj_stage_q[31:0] <= data_w;
                            swj_length_q <= 9'd0;
                            s_axi_bresp <= OKAY;
                        end
                        8'h48: if (mode_q == MODE_NORMAL) begin
                            swj_stage_q[63:32] <= data_w;
                            swj_length_q <= 9'd0;
                            s_axi_bresp <= OKAY;
                        end
                        8'h4C: if (mode_q == MODE_NORMAL) begin
                            swj_stage_q[95:64] <= data_w;
                            swj_length_q <= 9'd0;
                            s_axi_bresp <= OKAY;
                        end
                        8'h50: if (mode_q == MODE_NORMAL) begin
                            swj_stage_q[127:96] <= data_w;
                            swj_length_q <= 9'd0;
                            s_axi_bresp <= OKAY;
                        end
                        8'h54: if (mode_q == MODE_NORMAL) begin
                            swj_stage_q[159:128] <= data_w;
                            swj_length_q <= 9'd0;
                            s_axi_bresp <= OKAY;
                        end
                        8'h58: if (mode_q == MODE_NORMAL) begin
                            swj_stage_q[191:160] <= data_w;
                            swj_length_q <= 9'd0;
                            s_axi_bresp <= OKAY;
                        end
                        8'h5C: if (mode_q == MODE_NORMAL) begin
                            swj_stage_q[223:192] <= data_w;
                            swj_length_q <= 9'd0;
                            s_axi_bresp <= OKAY;
                        end
                        8'h60: if (mode_q == MODE_NORMAL) begin
                            swj_stage_q[255:224] <= data_w;
                            swj_length_q <= 9'd0;
                            s_axi_bresp <= OKAY;
                        end
                        8'h64: if (mode_q == MODE_NORMAL &&
                                    data_w[31:9] == 0 &&
                                    (data_w == 0 ||
                                     (data_w >= 33 && data_w <= 256))) begin
                            swj_length_q <= data_w[8:0];
                            s_axi_bresp <= OKAY;
                        end
                        8'h14: if (cmd_enqueue) s_axi_bresp <= OKAY;
                        8'h20: if (resp_dequeue) s_axi_bresp <= OKAY;
                        8'h28: if (cmd_flush) begin
                            s_axi_bresp <= OKAY;
                        end else if (mode_q == MODE_NORMAL &&
                                   data_w[31:2] == 0 &&
                                   !(data_w[1] && !busy) &&
                                   (data_w[0] ||
                                    (!busy && cmd_empty && resp_empty &&
                                     !resp_valid))) begin
                            normal_enable_q <= data_w[0];
                            abort_q <= data_w[1]; s_axi_bresp <= OKAY;
                        end
                        // ERROR_LATCH is RW1C. Do not clear a fault with
                        // pending commands: prevent accidental write replay.
                        8'h2C: if (mode_q == MODE_NORMAL && data_w == 1 &&
                                   !busy && cmd_empty && !resp_valid) begin
                            fault_q <= 1'b0; s_axi_bresp <= OKAY;
                        end
                        8'h30: if (mode_q == MODE_NORMAL &&
                                   data_w[31:1] == 0) begin
                            irq_enable_q <= data_w[0]; s_axi_bresp <= OKAY;
                        end
                        // IRQ_PENDING is sticky completion-event RW1C;
                        // clearing it does not pop or erase any response.
                        8'h34: if (mode_q == MODE_NORMAL && data_w == 1) begin
                            if (!resp_enqueue) irq_pending_q <= 1'b0;
                            s_axi_bresp <= OKAY;
                        end
                        8'h38: if (data_w[31:1] == 0 &&
                                   !busy && !resp_valid &&
                                   cmd_empty && resp_empty &&
                                   !normal_enable_q) begin
                            mode_q <= data_w[0] ? MODE_NORMAL : MODE_OFF;
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
                            s_axi_rdata <= 32'h00050000 | SITE_ID;
                            s_axi_rresp <= OKAY;
                        end
                        8'h04: begin
                            s_axi_rdata <= {26'd0,mode_q, fault_q,
                                            !resp_empty,busy,normal_enable_q};
                            s_axi_rresp <= OKAY;
                        end
                        8'h08: begin
                            s_axi_rdata <= {16'd0,half_q}; s_axi_rresp <= OKAY;
                        end
                        8'h0C: begin
                            s_axi_rdata <= timeout_q; s_axi_rresp <= OKAY;
                        end
                        8'h18: if (mode_q == MODE_NORMAL && !resp_empty) begin
                            s_axi_rdata <= {resp_head.tag,2'd0,
                                resp_head.link,resp_head.attempts[3:0],
                                resp_head.data_valid,resp_head.ack,
                                resp_head.status};
                            s_axi_rresp <= OKAY;
                        end
                        8'h1C: if (mode_q == MODE_NORMAL && !resp_empty) begin
                            s_axi_rdata <= resp_head.data;
                            s_axi_rresp <= OKAY;
                        end
                        8'h24: begin
                            s_axi_rdata <= {10'd0,resp_level_q,3'd0,
                                cmd_level_q,7'd0,!resp_empty,!cmd_empty};
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
                            s_axi_rdata <= {31'd0,irq_pending_q};
                            s_axi_rresp <= OKAY;
                        end
                        8'h38: begin
                            s_axi_rdata <= {30'd0,mode_q}; s_axi_rresp <= OKAY;
                        end
                        default: s_axi_rresp <= SLVERR;
                    endcase
                end
            end
        end
    end
endmodule
