// SWD-01 point-to-point transaction transport. No AXI, pins or target policy.
// Single FCLK domain; existing SWD-00 PHY samples target output at end of HIGH.
module swd_transaction_master (
    input logic clk, rst_n, cmd_abort,
    input logic cmd_valid,
    output logic cmd_ready,
    input logic cmd_op, // 0=raw transfer, 1=64-clock line reset + idle
    input logic cmd_ap, cmd_read,
    input logic [3:0] cmd_addr,
    input logic [31:0] cmd_wdata,
    input logic [15:0] cmd_half_period,
    input logic [2:0] cmd_turnaround,
    input logic [7:0] cmd_idle_cycles, cmd_max_retries,
    input logic cmd_error_data_phase,
    input logic [31:0] cmd_timeout_cycles,
    output logic busy,
    output logic [1:0] link_state, // 0=reset required, 1=DPIDR required, 2=connected
    output logic resp_valid,
    input logic resp_ready,
    output logic [3:0] resp_status,
    output logic [2:0] resp_ack,
    output logic [31:0] resp_rdata,
    output logic resp_data_valid,
    output logic [8:0] resp_attempts,
    input logic swdio_in,
    output logic swclk, swdio_out, swdio_oe
);
    localparam logic [3:0] OK=0, BAD_CONFIG=1, NEED_RESET=2, WAIT_LIMIT=3,
        FAULT=4, BAD_ACK=5, PARITY=6, TIMEOUT=7, ABORTED=8, PHY_ERROR=9;
    typedef enum logic [3:0] {
        RESET_A, RESET_B, REQUEST, TURN_IN, ACK, TURN_WRITE,
        DATA, PARITY_BIT, TURN_OUT, IDLE_CLOCKS, DRAIN_DATA, DRAIN_PARITY, DRAIN_TURN, RECOVER_A, RECOVER_B
    } phase_t;
    phase_t phase;
    logic op_q, ap_q, read_q, error_phase_q;
    logic [3:0] addr_q;
    logic [31:0] wdata_q, read_data_q, timeout_q, elapsed;
    logic [15:0] half_q;
    logic [2:0] turn_q;
    logic [7:0] idle_q, retries_q, idle_left;
    logic [3:0] result_q;
    logic phy_start, phy_abort, phy_drive;
    logic [31:0] phy_tx;
    logic [5:0] phy_count;
    wire phy_busy, phy_done, phy_error, phy_clock, phy_out, phy_oe_unused;
    wire [31:0] phy_rx;
    wire phy_resetn = rst_n && !phy_abort;
    wire is_dpidr = !ap_q && read_q && addr_q == 0;
    wire [7:0] header = {1'b1, 1'b0, ^{ap_q,read_q,addr_q[3:2]}, addr_q[3:2], read_q, ap_q, 1'b1};
    assign cmd_ready = rst_n && !cmd_abort && !busy && !resp_valid;
    assign swclk = rst_n && busy && !phy_abort && phy_clock;
    // Ownership spans PHY segments, including DATA[31] -> PARITY gaps.
    assign swdio_oe = rst_n && busy && !phy_abort && phy_drive;
    assign swdio_out = phy_busy ? phy_out : phy_tx[0];
    swd_waveform_engine phy (
        .clk(clk), .rst_n(phy_resetn), .start(phy_start), .tx_data(phy_tx),
        .bit_count(phy_count), .half_period_cycles(half_q), .drive_enable(phy_drive),
        .swdio_in(swdio_in), .swclk(phy_clock), .swdio_out(phy_out),
        .swdio_oe(phy_oe_unused), .rx_data(phy_rx), .busy(phy_busy),
        .done(phy_done), .error(phy_error)
    );
    task automatic segment(input phase_t next_phase, input logic [5:0] count,
                            input logic [31:0] data, input logic drive);
        phase <= next_phase;
        phy_count <= count;
        phy_tx <= data;
        phy_drive <= drive;
        phy_start <= 1'b1;
    endtask
    task automatic complete(input logic [3:0] status);
        busy <= 1'b0;
        phy_start <= 1'b0;
        phy_abort <= 1'b1;
        phy_drive <= 1'b0;
        resp_valid <= 1'b1;
        resp_status <= status;
        resp_rdata <= (status == OK && !op_q && read_q) ? read_data_q : 32'b0;
        resp_data_valid <= status == OK && !op_q && read_q;
        if (status == OK && op_q) link_state <= 1;
        else if (status == OK && is_dpidr) link_state <= 2;
        else if (status == BAD_ACK || status == PARITY || status == TIMEOUT ||
                 status == ABORTED || status == PHY_ERROR) link_state <= 0;
    endtask
    task automatic idle_segment;
        if (idle_left > 32) begin
            idle_left <= idle_left - 8'd32;
            segment(IDLE_CLOCKS, 6'd32, 0, 1'b1);
        end else begin
            idle_left <= 0;
            segment(IDLE_CLOCKS, {1'b0,idle_left[4:0]} == 0 ? 6'd32 : {1'b0,idle_left[4:0]}, 0, 1'b1);
        end
    endtask
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            busy <= 0; link_state <= 0; resp_valid <= 0;
            resp_status <= 0; resp_ack <= 0; resp_rdata <= 0;
            resp_data_valid <= 0; resp_attempts <= 0;
            op_q <= 0; ap_q <= 0; read_q <= 0; error_phase_q <= 0;
            addr_q <= 0; wdata_q <= 0; read_data_q <= 0;
            timeout_q <= 0; elapsed <= 0; half_q <= 2; turn_q <= 1;
            idle_q <= 8; retries_q <= 0; idle_left <= 0; result_q <= 0;
            phase <= RESET_A; phy_start <= 0; phy_abort <= 0;
            phy_drive <= 0; phy_tx <= 0; phy_count <= 1;
        end else begin
            phy_start <= 0;
            phy_abort <= 0;
            if (resp_valid && resp_ready) resp_valid <= 0;
            if (cmd_valid && cmd_ready) begin
                resp_ack <= 0; resp_attempts <= 0; resp_rdata <= 0; resp_data_valid <= 0;
                read_data_q <= 0; elapsed <= 0; result_q <= OK;
                op_q <= cmd_op; ap_q <= cmd_ap; read_q <= cmd_read;
                addr_q <= cmd_addr; wdata_q <= cmd_wdata;
                half_q <= cmd_half_period; turn_q <= cmd_turnaround;
                idle_q <= cmd_idle_cycles; retries_q <= cmd_max_retries;
                error_phase_q <= cmd_error_data_phase; timeout_q <= cmd_timeout_cycles;
                if (cmd_half_period < 2 || cmd_turnaround < 1 || cmd_turnaround > 4 ||
                    cmd_idle_cycles < 8 || cmd_timeout_cycles == 0 || cmd_addr[1:0] != 0) begin
                    resp_valid <= 1; resp_status <= BAD_CONFIG;
                end else if (!cmd_op && (link_state == 0 || (link_state == 1 &&
                             (cmd_ap || !cmd_read || cmd_addr != 0)))) begin
                    resp_valid <= 1; resp_status <= NEED_RESET;
                end else begin
                    busy <= 1;
                    if (cmd_op) begin
                        idle_left <= 8;
                        link_state <= 0;
                        segment(RECOVER_A, 32, 0, 0);
                    end else begin
                        idle_left <= cmd_idle_cycles;
                        resp_attempts <= 1;
                        segment(REQUEST, 8, {24'b0,1'b1,1'b0,
                            ^{cmd_ap,cmd_read,cmd_addr[3:2]},cmd_addr[3:2],cmd_read,cmd_ap,1'b1}, 1);
                    end
                end
            end else if (busy) begin
                elapsed <= elapsed + 32'd1;
                if (cmd_abort) complete(ABORTED);
                else if (elapsed >= timeout_q - 32'd1) complete(TIMEOUT);
                else if (phy_done) begin
                    if (phy_error) complete(PHY_ERROR);
                    else case (phase)
                        RECOVER_A: segment(RECOVER_B, 32, 0, 0);
                        RECOVER_B: segment(RESET_A, 32, 32'hffffffff, 1);
                        RESET_A: segment(RESET_B, 32, 32'hffffffff, 1);
                        RESET_B: idle_segment();
                        REQUEST: segment(TURN_IN, {3'b0,turn_q}, 0, 0);
                        TURN_IN: segment(ACK, 3, 0, 0);
                        ACK: begin
                            resp_ack <= phy_rx[2:0];
                            if (phy_rx[2:0] == 1 || phy_rx[2:0] == 2 || phy_rx[2:0] == 4) begin
                                if (phy_rx[2:0] == 2) result_q <= WAIT_LIMIT;
                                else if (phy_rx[2:0] == 4) result_q <= FAULT;
                                else result_q <= OK;
                                if (phy_rx[2:0] == 1 || error_phase_q) begin
                                    if (read_q) segment(DATA, 32, 0, 0);
                                    else segment(TURN_WRITE, {3'b0,turn_q}, 0, 0);
                                end else segment(TURN_OUT, {3'b0,turn_q}, 0, 0);
                            end else begin
                                // Unknown ACK can hide a real OK. Drain possible 33-bit
                                // target data without driving; never replay a write.
                                result_q <= BAD_ACK;
                                segment(DRAIN_DATA, 32, 0, 0);
                            end
                        end
                        TURN_WRITE: segment(DATA, 32, resp_ack == 1 ? wdata_q : 32'b0, 1);
                        DATA: begin
                            if (read_q && resp_ack == 1) read_data_q <= phy_rx;
                            segment(PARITY_BIT, 1, (!read_q && resp_ack == 1) ? {31'b0,^wdata_q} : 32'b0, !read_q);
                        end
                        PARITY_BIT: begin
                            if (read_q) begin
                                if (resp_ack == 1 && phy_rx[0] != ^read_data_q) result_q <= PARITY;
                                segment(TURN_OUT, {3'b0,turn_q}, 0, 0);
                            end else idle_segment();
                        end
                        TURN_OUT: idle_segment();
                        IDLE_CLOCKS: begin
                            if (idle_left != 0) idle_segment();
                            else if (!op_q && result_q == WAIT_LIMIT && resp_attempts <= {1'b0,retries_q}) begin
                                resp_attempts <= resp_attempts + 9'd1;
                                idle_left <= idle_q;
                                segment(REQUEST, 8, {24'b0,header}, 1);
                            end else complete(result_q);
                        end
                        DRAIN_DATA: segment(DRAIN_PARITY, 1, 0, 0);
                        DRAIN_PARITY: segment(DRAIN_TURN, 4, 0, 0);
                        DRAIN_TURN: complete(BAD_ACK);
                        default: complete(PHY_ERROR);
                    endcase
                end
            end
        end
    end
endmodule
