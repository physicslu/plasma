// SWD-00: clocked LSB-first SWD waveform primitive, not a SWD transaction master.
// One command shifts 1..32 bits at a programmable >=2 cycle half-period.
// SWDIO ownership is output-enable only; a separately approved IOBUF, VTref,
// level translation and target isolation are REQUIRED before any physical DUT.
// No target reset, power control, ACK/parity, turnaround or OpenOCD integration.
module swd_waveform_engine (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         start,
    input  logic [31:0]  tx_data,
    input  logic [5:0]   bit_count,
    input  logic [15:0]  half_period_cycles,
    input  logic         drive_enable,
    input  logic         swdio_in,
    output logic         swclk,
    output logic         swdio_out,
    output logic         swdio_oe,
    output logic [31:0]  rx_data,
    output logic         busy,
    output logic         done,
    output logic         error
);
    typedef enum logic [1:0] {
        ST_IDLE,
        ST_LOW,
        ST_HIGH
    } state_t;

    state_t state;
    logic [15:0] ticks_left;
    logic [15:0] half_period_q;
    logic [5:0]  count_q;
    logic [4:0]  bit_index;
    logic [31:0] tx_q;

    assign busy = state != ST_IDLE;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state         <= ST_IDLE;
            ticks_left    <= '0;
            half_period_q <= '0;
            count_q       <= '0;
            bit_index     <= '0;
            tx_q          <= '0;
            swclk         <= 1'b0;
            swdio_out     <= 1'b0;
            swdio_oe      <= 1'b0; // fail-safe Hi-Z
            rx_data       <= '0;
            done          <= 1'b0;
            error         <= 1'b0;
        end else begin
            done <= 1'b0;
            case (state)
                ST_IDLE: begin
                    swclk <= 1'b0;
                    swdio_oe <= 1'b0;
                    if (start) begin
                        if (bit_count == 0 || bit_count > 32 ||
                            half_period_cycles < 2) begin
                            done <= 1'b1;
                            error <= 1'b1;
                        end else begin
                            error <= 1'b0;
                            state <= ST_LOW;
                            count_q <= bit_count;
                            bit_index <= '0;
                            tx_q <= tx_data;
                            swdio_out <= tx_data[0];
                            swdio_oe <= drive_enable;
                            rx_data <= '0;
                            half_period_q <= half_period_cycles;
                            ticks_left <= half_period_cycles - 16'd1;
                        end
                    end
                end
                ST_LOW: begin
                    // A second START during an active command is rejected.
                    if (start)
                        error <= 1'b1;
                    if (ticks_left == 0) begin
                        swclk <= 1'b1;
                        ticks_left <= half_period_q - 16'd1;
                        state <= ST_HIGH;
                    end else begin
                        ticks_left <= ticks_left - 16'd1;
                    end
                end
                ST_HIGH: begin
                    if (start)
                        error <= 1'b1;
                    if (ticks_left == 0) begin
                        // Sample just before the generated falling edge.
                        rx_data[bit_index] <= swdio_in;
                        swclk <= 1'b0;
                        if ({1'b0, bit_index} == count_q - 6'd1) begin
                            swdio_oe <= 1'b0;
                            done <= 1'b1;
                            state <= ST_IDLE;
                        end else begin
                            bit_index <= bit_index + 5'd1;
                            swdio_out <= tx_q[bit_index + 5'd1];
                            ticks_left <= half_period_q - 16'd1;
                            state <= ST_LOW;
                        end
                    end else begin
                        ticks_left <= ticks_left - 16'd1;
                    end
                end
                default: begin
                    state <= ST_IDLE;
                    swclk <= 1'b0;
                    swdio_oe <= 1'b0;
                    done <= 1'b1;
                    error <= 1'b1;
                end
            endcase
        end
    end
endmodule
