// SWD-03 SYNTHESIZABLE *TEST-ONLY* fixture.
// Deliberately narrow: detect line reset, respond OK to DP DPIDR read,
// FAULT for every other request. NOT a real target or physical SWD interface.
// All signals live in PS FCLK0 (100MHz) domain; no external PL pins.
module swd03_dpidr_responder (
    input  logic clk,
    input  logic rst_n,
    input  logic swclk,
    input  logic host_out,
    input  logic host_oe,
    output logic swdio_in
);
    localparam integer HEADER_W = 8;
    localparam integer DATA_W = 32;
    localparam integer RESET_ONES = 50;
    localparam logic [DATA_W-1:0] DP_IDCODE = 32'h2BA01477;
    localparam logic [HEADER_W-1:0] DPIDR_HEADER = 8'hA5;
    typedef enum logic [2:0] {
        UNSYNC, RESET_TAIL, HEADER, TURN_IN, ACK, DATA, PARITY, TURN_OUT
    } state_t;
    state_t state;
    logic prev_swclk, drive_q, value_q, good_req;
    logic [6:0] ones_q;
    logic [1:0] zero_tail_q;
    logic [HEADER_W-1:0] header_q;
    logic [2:0] header_index, ack_index;
    logic [4:0] data_index;

    // Resolved internal line; host owns it when host_oe is high.
    assign swdio_in = host_oe ? host_out : (drive_q ? value_q : 1'b1);

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= UNSYNC;
            prev_swclk <= 1'b0;
            drive_q <= 1'b0;
            value_q <= 1'b1;
            good_req <= 1'b0;
            ones_q <= '0;
            zero_tail_q <= '0;
            header_q <= '0;
            header_index <= '0;
            ack_index <= '0;
            data_index <= '0;
        end else begin
            prev_swclk <= swclk;
            if (swclk && !prev_swclk) begin
                // Line-reset pattern supersedes any partial SWD phase.
                if (host_oe && host_out) begin
                    if (ones_q < RESET_ONES) ones_q <= ones_q + 7'd1;
                end else begin
                    ones_q <= '0;
                end

                if (host_oe && host_out && ones_q >= RESET_ONES - 1) begin
                    state <= RESET_TAIL;
                    zero_tail_q <= '0;
                    drive_q <= 1'b0;
                end else if (state == RESET_TAIL) begin
                    drive_q <= 1'b0;
                    if (host_oe && !host_out) begin
                        if (zero_tail_q == 2'd1) begin
                            state <= HEADER;
                            zero_tail_q <= '0;
                            header_index <= '0;
                            header_q <= '0;
                        end else zero_tail_q <= zero_tail_q + 2'd1;
                    end else zero_tail_q <= '0;
                end else begin
                    case (state)
                        UNSYNC: drive_q <= 1'b0;
                        HEADER: begin
                            drive_q <= 1'b0;
                            // Ignore low idle clocks; start bit must be host-driven 1.
                            if (host_oe && (host_out || header_index != 0)) begin
                                header_q[header_index] <= host_out;
                                if (header_index == HEADER_W - 1) begin
                                    good_req <= ({host_out,header_q[6:0]} == DPIDR_HEADER);
                                    header_index <= '0;
                                    ack_index <= '0;
                                    state <= TURN_IN;
                                end else header_index <= header_index + 3'd1;
                            end
                        end
                        TURN_IN: begin
                            drive_q <= 1'b0;
                            state <= ACK;
                        end
                        ACK: begin
                            // SWD ACK OK = b001, FAULT = b100, transmitted LSB first.
                            drive_q <= 1'b1;
                            value_q <= good_req ? (ack_index == 0) : (ack_index == 2);
                            if (ack_index == 2) begin
                                ack_index <= '0;
                                data_index <= '0;
                                state <= good_req ? DATA : TURN_OUT;
                            end else ack_index <= ack_index + 3'd1;
                        end
                        DATA: begin
                            drive_q <= 1'b1;
                            value_q <= DP_IDCODE[data_index];
                            if (data_index == DATA_W - 1) begin
                                data_index <= '0;
                                state <= PARITY;
                            end else data_index <= data_index + 5'd1;
                        end
                        PARITY: begin
                            drive_q <= 1'b1;
                            value_q <= ^DP_IDCODE;
                            state <= TURN_OUT;
                        end
                        TURN_OUT: begin
                            drive_q <= 1'b0;
                            state <= HEADER;
                        end
                        default: begin
                            drive_q <= 1'b0;
                            state <= UNSYNC;
                        end
                    endcase
                end
            end
        end
    end
endmodule
