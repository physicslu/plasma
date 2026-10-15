module swd_transaction_axi_lite #(
    parameter logic [31:0] AXI_BASE_ADDRESS = 32'h40003000
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
    /* verilator lint_off UNUSED */
    input  logic [2:0]  s_axi_awprot,
    /* verilator lint_on UNUSED */
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
    /* verilator lint_off UNUSED */
    input  logic [2:0]  s_axi_arprot,
    /* verilator lint_on UNUSED */
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
    input  logic        s_axi_rready,

    // Internal digital SWD interface; no external pin assignment here.
    input  logic        swdio_in,
    output logic        swclk,
    output logic        swdio_out,
    output logic        swdio_oe
);


    // Fixed AXI4-Lite ABI widths. Not configurable without a new ABI.
    localparam integer AXI_ADDR_W = 32;
    localparam integer AXI_DATA_W = 32;
    localparam integer AXI_STRB_W = AXI_DATA_W / 8;

    // SWD command field widths.
    localparam integer CFG_W         = 8;
    localparam integer SWD_ADDR_W    = 4;
    localparam integer SWD_HALF_W    = 16;
    localparam integer SWD_TURN_W    = 3;
    localparam integer SWD_IDLE_W    = 8;
    localparam integer SWD_RETRY_W   = 8;
    localparam integer SWD_LINK_W    = 2;
    localparam integer RESP_STATUS_W = 4;
    localparam integer RESP_ACK_W    = 3;
    localparam integer RESP_ATTEMPT_W = 9;

    // CONFIG register bit positions.
    localparam integer CFG_OP_BIT    = 0;
    localparam integer CFG_AP_BIT    = 1;
    localparam integer CFG_READ_BIT  = 2;
    localparam integer CFG_ADDR_LSB  = 3;
    localparam integer CFG_ERROR_BIT = 7;

    // Software command encodings.
    localparam logic [AXI_DATA_W-1:0] CMD_START = 32'd1;
    localparam logic [AXI_DATA_W-1:0] CMD_ABORT = 32'd2;
    localparam logic [AXI_DATA_W-1:0] CMD_ACK_RESPONSE = 32'd4;
    localparam logic [AXI_DATA_W-1:0] ABI_VERSION = 32'd1;

    // Power-on configuration.
    localparam logic [AXI_DATA_W-1:0] DEFAULT_CONFIG = 32'h00000004;
    localparam logic [AXI_DATA_W-1:0] DEFAULT_HALF = 32'd2;
    localparam logic [AXI_DATA_W-1:0] DEFAULT_TURN = 32'd1;
    localparam logic [AXI_DATA_W-1:0] DEFAULT_IDLE = 32'd8;
    localparam logic [AXI_DATA_W-1:0] DEFAULT_TIMEOUT = 32'd1000000;

    // Reject writes to reserved bits after WSTRB merging.
    localparam logic [AXI_DATA_W-1:0] CFG_RESERVED_MASK =
        {AXI_DATA_W{1'b1}} << CFG_W;
    localparam logic [AXI_DATA_W-1:0] HALF_RESERVED_MASK =
        {AXI_DATA_W{1'b1}} << SWD_HALF_W;
    localparam logic [AXI_DATA_W-1:0] TURN_RESERVED_MASK =
        {AXI_DATA_W{1'b1}} << SWD_TURN_W;
    localparam logic [AXI_DATA_W-1:0] IDLE_RESERVED_MASK =
        {AXI_DATA_W{1'b1}} << SWD_IDLE_W;
    localparam logic [AXI_DATA_W-1:0] RETRY_RESERVED_MASK =
        {AXI_DATA_W{1'b1}} << SWD_RETRY_W;

    // Packed status and response field widths.
    localparam integer STATUS_USED_W = SWD_LINK_W + 3;
    localparam integer META_USED_W =
        RESP_ATTEMPT_W + 1 + RESP_ACK_W + RESP_STATUS_W;

    localparam logic [AXI_ADDR_W-1:0]
        REG_ABI      = AXI_BASE_ADDRESS + 'h00,
        REG_COMMAND  = AXI_BASE_ADDRESS + 'h04,
        REG_CONFIG   = AXI_BASE_ADDRESS + 'h08,
        REG_WDATA    = AXI_BASE_ADDRESS + 'h0c,
        REG_HALF     = AXI_BASE_ADDRESS + 'h10,
        REG_TURN     = AXI_BASE_ADDRESS + 'h14,
        REG_IDLE     = AXI_BASE_ADDRESS + 'h18,
        REG_RETRIES  = AXI_BASE_ADDRESS + 'h1c,
        REG_TIMEOUT  = AXI_BASE_ADDRESS + 'h20,
        REG_STATUS   = AXI_BASE_ADDRESS + 'h24,
        REG_META     = AXI_BASE_ADDRESS + 'h28,
        REG_RDATA    = AXI_BASE_ADDRESS + 'h2c;

    localparam logic [1:0] AXI_OKAY = 2'b00;
    localparam logic [1:0] AXI_SLVERR = 2'b10;

    logic aw_pending, w_pending;
    logic [AXI_DATA_W-1:0] aw_addr_q, w_data_q;
    logic [AXI_STRB_W-1:0] w_strb_q;

    logic [AXI_DATA_W-1:0] config_q, wdata_q, half_q, turn_q;
    logic [AXI_DATA_W-1:0] idle_q, retries_q, timeout_q;

    logic launch_pending, abort_pulse, consume_pulse;

    wire master_ready, master_busy, master_resp_valid;
    wire [SWD_LINK_W-1:0] master_link_state;
    wire [RESP_STATUS_W-1:0] master_status;
    wire [RESP_ACK_W-1:0] master_ack;
    wire [AXI_DATA_W-1:0] master_rdata;
    wire master_data_valid;
    wire [RESP_ATTEMPT_W-1:0] master_attempts;

    wire active = launch_pending || master_busy || master_resp_valid;
    wire software_ready = master_ready && !active;

    wire accept_aw = s_axi_awvalid && s_axi_awready;
    wire accept_w = s_axi_wvalid && s_axi_wready;
    wire accept_ar = s_axi_arvalid && s_axi_arready;

    wire [AXI_ADDR_W-1:0] write_addr = accept_aw ? s_axi_awaddr : aw_addr_q;
    wire [AXI_DATA_W-1:0] write_data = accept_w ? s_axi_wdata : w_data_q;
    wire [AXI_STRB_W-1:0] write_strb = accept_w ? s_axi_wstrb : w_strb_q;

    wire [AXI_DATA_W-1:0] status_word = {
        {(AXI_DATA_W-STATUS_USED_W){1'b0}}, master_link_state, master_resp_valid,
        software_ready, (launch_pending || master_busy)
    };

    wire [AXI_DATA_W-1:0] response_meta = {
        {(AXI_DATA_W-META_USED_W){1'b0}}, master_attempts, master_data_valid,
        master_ack, master_status
    };

    assign s_axi_awready = s_axi_aresetn && !aw_pending && !s_axi_bvalid;
    assign s_axi_wready = s_axi_aresetn && !w_pending && !s_axi_bvalid;
    assign s_axi_arready = s_axi_aresetn && !s_axi_rvalid;

    function automatic logic [31:0] merge_bytes(
        input logic [31:0] old_value,
        input logic [31:0] new_value,
        input logic [3:0] strb
    );
        merge_bytes = old_value;
        for (int i = 0; i < 4; i++)
            if (strb[i])
                merge_bytes[i*8 +: 8] = new_value[i*8 +: 8];
    endfunction

    swd_transaction_master master (
        .clk(s_axi_aclk),
        .rst_n(s_axi_aresetn),
        .cmd_abort(abort_pulse),
        .cmd_valid(launch_pending),
        .cmd_ready(master_ready),
        .cmd_op(config_q[CFG_OP_BIT]),
        .cmd_ap(config_q[CFG_AP_BIT]),
        .cmd_read(config_q[CFG_READ_BIT]),
        .cmd_addr(config_q[CFG_ADDR_LSB +: SWD_ADDR_W]),
        .cmd_wdata(wdata_q),
        .cmd_half_period(half_q[SWD_HALF_W-1:0]),
        .cmd_turnaround(turn_q[SWD_TURN_W-1:0]),
        .cmd_idle_cycles(idle_q[SWD_IDLE_W-1:0]),
        .cmd_max_retries(retries_q[SWD_RETRY_W-1:0]),
        .cmd_error_data_phase(config_q[CFG_ERROR_BIT]),
        .cmd_timeout_cycles(timeout_q),
        .busy(master_busy),
        .link_state(master_link_state),
        .resp_valid(master_resp_valid),
        .resp_ready(consume_pulse),
        .resp_status(master_status),
        .resp_ack(master_ack),
        .resp_rdata(master_rdata),
        .resp_data_valid(master_data_valid),
        .resp_attempts(master_attempts),
        .swdio_in(swdio_in),
        .swclk(swclk),
        .swdio_out(swdio_out),
        .swdio_oe(swdio_oe)
    );

    always_ff @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            aw_pending <= 0;
            w_pending <= 0;
            aw_addr_q <= 0;
            w_data_q <= 0;
            w_strb_q <= 0;

            s_axi_bvalid <= 0;
            s_axi_bresp <= AXI_OKAY;
            s_axi_rvalid <= 0;
            s_axi_rresp <= AXI_OKAY;
            s_axi_rdata <= 0;

            config_q <= DEFAULT_CONFIG;
            wdata_q <= 0;
            half_q <= DEFAULT_HALF;
            turn_q <= DEFAULT_TURN;
            idle_q <= DEFAULT_IDLE;
            retries_q <= 0;
            timeout_q <= DEFAULT_TIMEOUT;

            launch_pending <= 0;
            abort_pulse <= 0;
            consume_pulse <= 0;
        end else begin
            abort_pulse <= 0;
            consume_pulse <= 0;

            if (launch_pending && master_ready)
                launch_pending <= 0;

            if (s_axi_bvalid && s_axi_bready)
                s_axi_bvalid <= 0;

            if (s_axi_rvalid && s_axi_rready)
                s_axi_rvalid <= 0;

            if (accept_aw) begin
                aw_pending <= 1;
                aw_addr_q <= s_axi_awaddr;
            end

            if (accept_w) begin
                w_pending <= 1;
                w_data_q <= s_axi_wdata;
                w_strb_q <= s_axi_wstrb;
            end

            if (!s_axi_bvalid &&
                (aw_pending || accept_aw) &&
                (w_pending || accept_w)) begin

                aw_pending <= 0;
                w_pending <= 0;
                s_axi_bvalid <= 1;
                s_axi_bresp <= AXI_OKAY;

                case (write_addr)
                    REG_COMMAND: begin
                        if (write_strb == 0) begin
                            // No operation.
                        end else if (write_strb != {AXI_STRB_W{1'b1}}) begin
                            s_axi_bresp <= AXI_SLVERR;
                        end else begin
                            case (write_data)
                                CMD_START: begin
                                    if (!software_ready)
                                        s_axi_bresp <= AXI_SLVERR;
                                    else
                                        launch_pending <= 1;
                                end
                                CMD_ABORT: begin
                                    // Abort only a running transaction.
                                    if (!master_busy)
                                        s_axi_bresp <= AXI_SLVERR;
                                    else
                                        abort_pulse <= 1;
                                end
                                CMD_ACK_RESPONSE: begin
                                    if (!master_resp_valid)
                                        s_axi_bresp <= AXI_SLVERR;
                                    else
                                        consume_pulse <= 1;
                                end
                                default:
                                    s_axi_bresp <= AXI_SLVERR;
                            endcase
                        end
                    end

                    REG_CONFIG, REG_WDATA, REG_HALF,
                    REG_TURN, REG_IDLE, REG_RETRIES,
                    REG_TIMEOUT: begin
                        if (write_strb != 0) begin
                            if (active) begin
                                s_axi_bresp <= AXI_SLVERR;
                            end else begin
                                case (write_addr)
                                    REG_CONFIG: begin
                                        if (|(merge_bytes(config_q, write_data, write_strb) & CFG_RESERVED_MASK))
                                            s_axi_bresp <= AXI_SLVERR;
                                        else
                                            config_q <= merge_bytes(config_q, write_data, write_strb);
                                    end
                                    REG_WDATA:
                                        wdata_q <= merge_bytes(wdata_q, write_data, write_strb);
                                    REG_HALF: begin
                                        if (|(merge_bytes(half_q, write_data, write_strb) & HALF_RESERVED_MASK))
                                            s_axi_bresp <= AXI_SLVERR;
                                        else
                                            half_q <= merge_bytes(half_q, write_data, write_strb);
                                    end
                                    REG_TURN: begin
                                        if (|(merge_bytes(turn_q, write_data, write_strb) & TURN_RESERVED_MASK))
                                            s_axi_bresp <= AXI_SLVERR;
                                        else
                                            turn_q <= merge_bytes(turn_q, write_data, write_strb);
                                    end
                                    REG_IDLE: begin
                                        if (|(merge_bytes(idle_q, write_data, write_strb) & IDLE_RESERVED_MASK))
                                            s_axi_bresp <= AXI_SLVERR;
                                        else
                                            idle_q <= merge_bytes(idle_q, write_data, write_strb);
                                    end
                                    REG_RETRIES: begin
                                        if (|(merge_bytes(retries_q, write_data, write_strb) & RETRY_RESERVED_MASK))
                                            s_axi_bresp <= AXI_SLVERR;
                                        else
                                            retries_q <= merge_bytes(retries_q, write_data, write_strb);
                                    end
                                    REG_TIMEOUT:
                                        timeout_q <= merge_bytes(timeout_q, write_data, write_strb);
                                    default:
                                        s_axi_bresp <= AXI_SLVERR;
                                endcase
                            end
                        end
                    end

                    default:
                        s_axi_bresp <= AXI_SLVERR;
                endcase
            end

            if (accept_ar) begin
                s_axi_rvalid <= 1;
                s_axi_rresp <= AXI_OKAY;
                s_axi_rdata <= 0;

                case (s_axi_araddr)
                    REG_ABI:     s_axi_rdata <= ABI_VERSION;
                    REG_COMMAND: s_axi_rdata <= 0;
                    REG_CONFIG:  s_axi_rdata <= config_q;
                    REG_WDATA:   s_axi_rdata <= wdata_q;
                    REG_HALF:    s_axi_rdata <= half_q;
                    REG_TURN:    s_axi_rdata <= turn_q;
                    REG_IDLE:    s_axi_rdata <= idle_q;
                    REG_RETRIES: s_axi_rdata <= retries_q;
                    REG_TIMEOUT: s_axi_rdata <= timeout_q;
                    REG_STATUS:  s_axi_rdata <= status_word;
                    REG_META:    s_axi_rdata <= response_meta;
                    REG_RDATA:   s_axi_rdata <= master_rdata;
                    default: begin
                        s_axi_rresp <= AXI_SLVERR;
                        s_axi_rdata <= 0;
                    end
                endcase
            end
        end
    end

endmodule
