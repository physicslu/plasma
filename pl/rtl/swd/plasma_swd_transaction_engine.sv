// PLASMA Site-owned SWD transaction engine. No legacy SWD-00/01 dependency.
// Standalone per-Site transaction FSM, no scheduling, queue/AXI/IRQ/Flash.
// A single 100 MHz clock drives this Site-local SWCLK divider and full SWD
// request / turnaround / ACK / read-write / parity / idle transaction.
//
// Command contract (private to SWD IP RTL; NOT the old RemoteBitbang ABI):
// cmd_op=1  => 64 SWCLK cycles with SWDIO=1, then 8 idle clocks.
// cmd_op=0  => one SWD DP/AP register read/write at cmd_addr[3:2].
// Currently cmd_turnaround must be 1, cmd_idle_cycles>=8, retries must
// be 0; unsupported features fail as BAD_CONFIG instead of being ignored.
// SWDIO direction is controlled by physical IOBUF in the parent; reset
// releases SWDIO and holds clock low. No target power / reset authority.
//
// Response statuses: OK=0, BAD_CONFIG=1, NEED_RESET=2, WAIT=3, FAULT=4,
// BAD_ACK=5, PARITY=6, TIMEOUT=7, ABORTED=8.
// An invalid ACK is drained as potential data without host drive.
// No implicit WAIT write replay; OpenOCD broker owns retry policy.
// A completion waits for resp_ready, preventing overwrite by another job.
module plasma_swd_transaction_engine (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        cmd_abort,
    input  logic        cmd_valid,
    output wire         cmd_ready,
    input  logic        cmd_op,
    input  logic        cmd_ap,
    input  logic        cmd_read,
    input  logic [3:0]  cmd_addr,
    input  logic [31:0] cmd_wdata,
    input  logic [15:0] cmd_half_period,
    input  logic [2:0]  cmd_turnaround,
    input  logic [7:0]  cmd_idle_cycles,
    input  logic [7:0]  cmd_max_retries,
    input  logic        cmd_error_data_phase,
    input  logic [31:0] cmd_timeout_cycles,
    output logic        busy,
    output logic [1:0]  link_state,
    output logic        resp_valid,
    input  logic        resp_ready,
    output logic [3:0]  resp_status,
    output logic [2:0]  resp_ack,
    output logic [31:0] resp_rdata,
    output logic        resp_data_valid,
    output logic [8:0]  resp_attempts,
    input  logic        swdio_in,
    output logic        swclk,
    output logic        swdio_out,
    output logic        swdio_oe
);
    localparam logic [3:0] ST_OK=4'd0, ST_CONFIG=4'd1,
        ST_NEED_RESET=4'd2, ST_WAIT=4'd3, ST_FAULT=4'd4,
        ST_BAD_ACK=4'd5, ST_PARITY=4'd6,
        ST_TIMEOUT=4'd7, ST_ABORT=4'd8;
    // 100MHz FCLK / (2 * 4) = 12.5MHz design maximum (NOT HIL qualified).
    localparam logic [15:0] MIN_HALF_PERIOD = 16'd4;
    localparam logic [2:0] ACK_OK=3'b001, ACK_WAIT=3'b010,
        ACK_FAULT=3'b100;

    typedef enum logic [3:0] {
        PH_RESET_HIGH, PH_RESET_IDLE, PH_REQUEST, PH_TURN_INPUT,
        PH_ACK, PH_TURN_WRITE, PH_DATA, PH_PARITY, PH_TURN_RETURN,
        PH_IDLE, PH_DRAIN
    } phase_t;

    phase_t phase;
    logic [7:0] bit_index, phase_bits;
    logic [15:0] half_q, timer;
    logic [31:0] elapsed, timeout_q, write_q, read_q;
    logic [7:0] request_q, idle_q;
    logic op_q, ap_q, read_direction_q;
    logic [3:0] address_q, result_q;
    logic [2:0] ack_shift;
    wire is_dpidr = !ap_q && read_direction_q && address_q == 4'b0000;
    wire [2:0] complete_ack = {swdio_in,ack_shift[1:0]};
    wire parity_read_mismatch = ((^read_q) != swdio_in);

    assign cmd_ready = rst_n && !cmd_abort && !busy && !resp_valid;

    function automatic logic owned(input phase_t ph, input logic read_direction);
        case (ph)
            PH_RESET_HIGH, PH_RESET_IDLE, PH_REQUEST, PH_IDLE:
                owned = 1'b1;
            PH_DATA, PH_PARITY:
                owned = !read_direction;
            default:
                owned = 1'b0;
        endcase
    endfunction

    function automatic logic tx_bit(input phase_t ph, input logic [7:0] idx,
                                     input logic [7:0] request_byte,
                                     input logic [31:0] payload);
        case (ph)
            PH_RESET_HIGH: tx_bit = 1'b1;
            PH_REQUEST: tx_bit = request_byte[idx[2:0]];
            PH_DATA: tx_bit = payload[idx[4:0]];
            PH_PARITY: tx_bit = ^payload;
            default: tx_bit = 1'b0;
        endcase
    endfunction

    // Fastest allowed candidate SWCLK is 12.5MHz, not yet DUT/board qualified.
    // Only called in the synchronous process; SWCLK is already falling or
    // held low when the next bit/ownership takes effect.
    task automatic enter_phase(input phase_t next_phase, input logic [7:0] cycles);
        phase <= next_phase;
        phase_bits <= cycles;
        bit_index <= 8'd0;
        swdio_oe <= owned(next_phase, read_direction_q);
        swdio_out <= tx_bit(next_phase, 8'd0, request_q, write_q);
    endtask

    task automatic finish_cmd(input logic [3:0] result);
        busy <= 1'b0;
        swclk <= 1'b0;
        swdio_oe <= 1'b0;
        swdio_out <= 1'b0;
        resp_valid <= 1'b1;
        resp_status <= result;
        resp_data_valid <= (result == ST_OK && !op_q && read_direction_q);
        if (result == ST_OK && !op_q && read_direction_q)
            resp_rdata <= read_q;
        else
            resp_rdata <= 32'd0;
        if (result == ST_OK && op_q)
            link_state <= 2'd1;
        else if (result == ST_OK && is_dpidr)
            link_state <= 2'd2;
        else if (result == ST_BAD_ACK || result == ST_PARITY ||
                 result == ST_TIMEOUT || result == ST_ABORT)
            link_state <= 2'd0;
    endtask

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            busy <= 1'b0;
            link_state <= 2'd0;
            resp_valid <= 1'b0;
            resp_status <= 4'd0;
            resp_ack <= 3'd0;
            resp_rdata <= 32'd0;
            resp_data_valid <= 1'b0;
            resp_attempts <= 9'd0;
            swclk <= 1'b0;
            swdio_out <= 1'b0;
            swdio_oe <= 1'b0;
            phase <= PH_RESET_HIGH;
            bit_index <= 8'd0;
            phase_bits <= 8'd0;
            half_q <= 16'd2;
            timer <= 16'd0;
            elapsed <= 32'd0;
            timeout_q <= 32'd0;
            write_q <= 32'd0;
            read_q <= 32'd0;
            request_q <= 8'd0;
            idle_q <= 8'd8;
            op_q <= 1'b0;
            ap_q <= 1'b0;
            read_direction_q <= 1'b0;
            address_q <= 4'd0;
            result_q <= ST_OK;
            ack_shift <= 3'd0;
        end else begin
            if (resp_valid && resp_ready)
                resp_valid <= 1'b0;

            if (cmd_valid && cmd_ready) begin
                op_q <= cmd_op;
                ap_q <= cmd_ap;
                read_direction_q <= cmd_read;
                address_q <= cmd_addr;
                write_q <= cmd_wdata;
                read_q <= 32'd0;
                request_q <= {1'b1,1'b0,
                    ^{cmd_ap,cmd_read,cmd_addr[3:2]},
                    cmd_addr[3:2],cmd_read,cmd_ap,1'b1};
                half_q <= cmd_half_period;
                timeout_q <= cmd_timeout_cycles;
                idle_q <= cmd_idle_cycles;
                elapsed <= 32'd0;
                result_q <= ST_OK;
                resp_ack <= 3'd0;
                resp_attempts <= cmd_op ? 9'd0 : 9'd1;
                resp_rdata <= 32'd0;
                resp_data_valid <= 1'b0;
                ack_shift <= 3'd0;
                swclk <= 1'b0;
                if (cmd_half_period < MIN_HALF_PERIOD ||
                    cmd_turnaround != 3'd1 ||
                    cmd_idle_cycles < 8'd8 ||
                    cmd_max_retries != 8'd0 ||
                    cmd_error_data_phase ||
                    cmd_timeout_cycles == 0 ||
                    cmd_addr[1:0] != 2'b00) begin
                    busy <= 1'b0;
                    swdio_oe <= 1'b0;
                    resp_valid <= 1'b1;
                    resp_status <= ST_CONFIG;
                end else if (!cmd_op &&
                             (link_state == 2'd0 ||
                              (link_state == 2'd1 &&
                               (cmd_ap || !cmd_read || cmd_addr != 0)))) begin
                    busy <= 1'b0;
                    swdio_oe <= 1'b0;
                    resp_valid <= 1'b1;
                    resp_status <= ST_NEED_RESET;
                end else begin
                    busy <= 1'b1;
                    timer <= cmd_half_period - 16'd1;
                    if (cmd_op) begin
                        link_state <= 2'd0;
                        phase <= PH_RESET_HIGH;
                        phase_bits <= 8'd64;
                        bit_index <= 8'd0;
                        swdio_oe <= 1'b1;
                        swdio_out <= 1'b1;
                    end else begin
                        phase <= PH_REQUEST;
                        phase_bits <= 8'd8;
                        bit_index <= 8'd0;
                        swdio_oe <= 1'b1;
                        swdio_out <= 1'b1; // request bit zero is START=1
                    end
                end
            end else if (busy) begin
                elapsed <= elapsed + 32'd1;
                if (cmd_abort) begin
                    finish_cmd(ST_ABORT);
                end else if (elapsed >= timeout_q - 32'd1) begin
                    finish_cmd(ST_TIMEOUT);
                end else if (timer != 0) begin
                    timer <= timer - 16'd1;
                end else if (!swclk) begin
                    swclk <= 1'b1;
                    timer <= half_q - 16'd1;
                end else begin
                    // End of SWCLK HIGH: sample target near falling edge,
                    // before choosing the next bit and direction.
                    swclk <= 1'b0;
                    timer <= half_q - 16'd1;
                    if (phase == PH_ACK)
                        ack_shift[bit_index[1:0]] <= swdio_in;
                    if (phase == PH_DATA && read_direction_q)
                        read_q[bit_index[4:0]] <= swdio_in;
                    if (bit_index + 8'd1 < phase_bits) begin
                        bit_index <= bit_index + 8'd1;
                        swdio_out <= tx_bit(phase, bit_index + 8'd1,
                                            request_q, write_q);
                    end else begin
                        case (phase)
                            PH_RESET_HIGH:
                                enter_phase(PH_RESET_IDLE, 8'd8);
                            PH_RESET_IDLE:
                                finish_cmd(ST_OK);
                            PH_REQUEST:
                                enter_phase(PH_TURN_INPUT, 8'd1);
                            PH_TURN_INPUT:
                                enter_phase(PH_ACK, 8'd3);
                            PH_ACK: begin
                                resp_ack <= complete_ack;
                                if (complete_ack == ACK_OK) begin
                                    if (read_direction_q)
                                        enter_phase(PH_DATA, 8'd32);
                                    else
                                        enter_phase(PH_TURN_WRITE, 8'd1);
                                end else if (complete_ack == ACK_WAIT ||
                                             complete_ack == ACK_FAULT) begin
                                    result_q <= (complete_ack == ACK_WAIT) ?
                                        ST_WAIT : ST_FAULT;
                                    enter_phase(PH_TURN_RETURN, 8'd1);
                                end else begin
                                    result_q <= ST_BAD_ACK;
                                    // Never drive an unrecognized target reply.
                                    enter_phase(PH_DRAIN, 8'd33);
                                end
                            end
                            PH_TURN_WRITE:
                                enter_phase(PH_DATA, 8'd32);
                            PH_DATA:
                                enter_phase(PH_PARITY, 8'd1);
                            PH_PARITY: begin
                                if (read_direction_q) begin
                                    if (parity_read_mismatch)
                                        result_q <= ST_PARITY;
                                    enter_phase(PH_TURN_RETURN, 8'd1);
                                end else begin
                                    enter_phase(PH_IDLE, idle_q);
                                end
                            end
                            PH_DRAIN:
                                enter_phase(PH_TURN_RETURN, 8'd1);
                            PH_TURN_RETURN:
                                enter_phase(PH_IDLE, idle_q);
                            PH_IDLE:
                                finish_cmd(result_q);
                            default:
                                finish_cmd(ST_BAD_ACK);
                        endcase
                    end
                end
            end
        end
    end
endmodule
