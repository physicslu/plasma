`timescale 1ns / 1ps

// Plasma PS<->PL diagnostic loopback execution core.
//
// This block is intentionally PPU-wide and does not touch Programming Site I/O.
// A transaction validates the host-provided CRC32 inside PL, then copies the
// accepted payload into an independent RX buffer. The host must read the RX
// buffer back through the PS/PL register interface before a PL Loopback can PASS.
module plasma_pl_loopback_core #(
    parameter int unsigned MAX_PAYLOAD_BYTES = 64
) (
    input  logic                         clk,
    input  logic                         rst_n,
    input  logic                         start,
    input  logic                         clear,
    input  logic [31:0]                  command,
    input  logic [31:0]                  sequence,
    input  logic [31:0]                  payload_length,
    input  logic [31:0]                  tx_crc32,
    input  logic [MAX_PAYLOAD_BYTES*8-1:0] tx_data,
    output logic                         ready,
    output logic                         busy,
    output logic                         done,
    output logic                         error,
    output logic [31:0]                  rx_sequence,
    output logic [31:0]                  rx_length,
    output logic [31:0]                  rx_crc32,
    output logic [31:0]                  error_code,
    output logic [MAX_PAYLOAD_BYTES*8-1:0] rx_data
);
    localparam logic [31:0] COMMAND_ECHO              = 32'h0000_0001;
    localparam logic [31:0] ERROR_NONE                = 32'h0000_0000;
    localparam logic [31:0] ERROR_UNSUPPORTED_COMMAND = 32'h0000_0001;
    localparam logic [31:0] ERROR_INVALID_LENGTH      = 32'h0000_0002;
    localparam logic [31:0] ERROR_TX_CRC_MISMATCH     = 32'h0000_0003;

    typedef enum logic [1:0] {
        STATE_IDLE,
        STATE_CRC,
        STATE_COPY
    } state_t;

    state_t state_q;
    logic [$clog2(MAX_PAYLOAD_BYTES)-1:0] index_q;
    logic [31:0] crc_q;
    logic [31:0] crc_next;
    logic [7:0] current_byte;

    function automatic logic [31:0] crc32_byte(
        input logic [31:0] crc_in,
        input logic [7:0]  data_in
    );
        logic [31:0] value;
        int bit_index;
        begin
            value = crc_in ^ {24'h0, data_in};
            for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1) begin
                if (value[0])
                    value = (value >> 1) ^ 32'hEDB8_8320;
                else
                    value = value >> 1;
            end
            return value;
        end
    endfunction

    always_comb begin
        ready = !busy;
        current_byte = tx_data[index_q*8 +: 8];
        crc_next = crc32_byte(crc_q, current_byte);
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state_q      <= STATE_IDLE;
            index_q      <= '0;
            crc_q        <= 32'hFFFF_FFFF;
            busy         <= 1'b0;
            done         <= 1'b0;
            error        <= 1'b0;
            rx_sequence  <= 32'h0;
            rx_length    <= 32'h0;
            rx_crc32     <= 32'h0;
            error_code   <= ERROR_NONE;
            rx_data      <= '0;
        end else begin
            if (clear && !busy) begin
                done       <= 1'b0;
                error      <= 1'b0;
                error_code <= ERROR_NONE;
                rx_crc32   <= 32'h0;
                rx_data    <= '0;
            end

            if (start && !busy) begin
                done        <= 1'b0;
                error       <= 1'b0;
                error_code  <= ERROR_NONE;
                rx_sequence <= sequence;
                rx_length   <= payload_length;
                rx_crc32    <= 32'h0;
                rx_data     <= '0;
                index_q     <= '0;
                crc_q       <= 32'hFFFF_FFFF;

                if (command != COMMAND_ECHO) begin
                    done       <= 1'b1;
                    error      <= 1'b1;
                    error_code <= ERROR_UNSUPPORTED_COMMAND;
                    state_q    <= STATE_IDLE;
                end else if (payload_length == 0 || payload_length > MAX_PAYLOAD_BYTES) begin
                    done       <= 1'b1;
                    error      <= 1'b1;
                    error_code <= ERROR_INVALID_LENGTH;
                    state_q    <= STATE_IDLE;
                end else begin
                    busy    <= 1'b1;
                    state_q <= STATE_CRC;
                end
            end else if (busy) begin
                case (state_q)
                    STATE_CRC: begin
                        crc_q <= crc_next;
                        if ((index_q + 1) == payload_length) begin
                            if ((crc_next ^ 32'hFFFF_FFFF) != tx_crc32) begin
                                busy       <= 1'b0;
                                done       <= 1'b1;
                                error      <= 1'b1;
                                error_code <= ERROR_TX_CRC_MISMATCH;
                                rx_crc32   <= crc_next ^ 32'hFFFF_FFFF;
                                state_q    <= STATE_IDLE;
                            end else begin
                                index_q  <= '0;
                                state_q  <= STATE_COPY;
                            end
                        end else begin
                            index_q <= index_q + 1'b1;
                        end
                    end

                    STATE_COPY: begin
                        rx_data[index_q*8 +: 8] <= current_byte;
                        if ((index_q + 1) == payload_length) begin
                            busy       <= 1'b0;
                            done       <= 1'b1;
                            error      <= 1'b0;
                            error_code <= ERROR_NONE;
                            rx_crc32   <= tx_crc32;
                            state_q    <= STATE_IDLE;
                        end else begin
                            index_q <= index_q + 1'b1;
                        end
                    end

                    default: begin
                        busy       <= 1'b0;
                        done       <= 1'b1;
                        error      <= 1'b1;
                        error_code <= ERROR_UNSUPPORTED_COMMAND;
                        state_q    <= STATE_IDLE;
                    end
                endcase
            end
        end
    end
endmodule
