// PLASMA MPE clean-sheet physical multi-Site SWD core: independent engines.
// Gate 1 RTL candidate only. Not an AXI slave, FPGA Image or HIL approval.
//
// The engine instances are independent even though they share the 100-MHz
// synchronous fabric clock. Each has its own SWCLK divider, FSM, turnaround,
// command/response handshake, timeout, abort, status and physical IOBUF.
//
// Site index 0 => canonical Site 1 (Pmod A / JA).
// Site index 1 => canonical Site 2 (Pmod B / JB).
// No power, NRST, SWO, voltage translation or 5V authority is provided.
//
// A reviewed top-level XDC/HWH must tie swclk_io[0]/swdio_io[0] to Y18/Y19
// and swclk_io[1]/swdio_io[1] to W14/Y14. This candidate intentionally
// does not reuse the single-Site remote_bitbang AXI GPIO image.
module plasma_mpe_dual_swd_core #(
    parameter integer SITE_COUNT = 2
) (
    input  logic                       clk,
    input  logic                       rst_n,
    input  logic [SITE_COUNT-1:0]      site_enable,
    input  logic [SITE_COUNT-1:0]      cmd_valid,
    output wire  [SITE_COUNT-1:0]      cmd_ready,
    input  logic [SITE_COUNT-1:0]      cmd_abort,
    input  logic [SITE_COUNT-1:0]      cmd_op,
    input  logic [SITE_COUNT-1:0]      cmd_ap,
    input  logic [SITE_COUNT-1:0]      cmd_read,
    input  logic [SITE_COUNT*4-1:0]    cmd_addr,
    input  logic [SITE_COUNT*32-1:0]   cmd_wdata,
    input  logic [SITE_COUNT*16-1:0]   cmd_half_period,
    input  logic [SITE_COUNT*3-1:0]    cmd_turnaround,
    input  logic [SITE_COUNT*8-1:0]    cmd_idle_cycles,
    input  logic [SITE_COUNT*8-1:0]    cmd_max_retries,
    input  logic [SITE_COUNT-1:0]      cmd_error_data_phase,
    input  logic [SITE_COUNT*32-1:0]   cmd_timeout_cycles,
    output wire  [SITE_COUNT-1:0]      busy,
    output wire  [SITE_COUNT*2-1:0]    link_state,
    output wire  [SITE_COUNT-1:0]      resp_valid,
    input  logic [SITE_COUNT-1:0]      resp_ready,
    output wire  [SITE_COUNT*4-1:0]    resp_status,
    output wire  [SITE_COUNT*3-1:0]    resp_ack,
    output wire  [SITE_COUNT*32-1:0]   resp_rdata,
    output wire  [SITE_COUNT-1:0]      resp_data_valid,
    output wire  [SITE_COUNT*9-1:0]    resp_attempts,
    output wire  [SITE_COUNT-1:0]      swclk_io,
    inout  wire  [SITE_COUNT-1:0]      swdio_io
);
    generate
        for (genvar s = 0; s < SITE_COUNT; s = s + 1) begin : g_sites
            wire swclk_internal;
            wire swdio_out_internal;
            wire swdio_oe_internal;
            wire swdio_input;
            wire cmd_ready_internal;

            // Physical output isolation is independent per Site.
            // Deasserting site_enable aborts that Site's transaction;
            // it does not affect the other Site's engine.
            wire allowed = rst_n && site_enable[s];

            plasma_mpe_swd_engine u_transaction (
                .clk(clk),
                .rst_n(rst_n),
                .cmd_abort(cmd_abort[s] || !site_enable[s]),
                .cmd_valid(cmd_valid[s] && site_enable[s]),
                .cmd_ready(cmd_ready_internal),
                .cmd_op(cmd_op[s]),
                .cmd_ap(cmd_ap[s]),
                .cmd_read(cmd_read[s]),
                .cmd_addr(cmd_addr[s*4 +: 4]),
                .cmd_wdata(cmd_wdata[s*32 +: 32]),
                .cmd_half_period(cmd_half_period[s*16 +: 16]),
                .cmd_turnaround(cmd_turnaround[s*3 +: 3]),
                .cmd_idle_cycles(cmd_idle_cycles[s*8 +: 8]),
                .cmd_max_retries(cmd_max_retries[s*8 +: 8]),
                .cmd_error_data_phase(cmd_error_data_phase[s]),
                .cmd_timeout_cycles(cmd_timeout_cycles[s*32 +: 32]),
                .busy(busy[s]),
                .link_state(link_state[s*2 +: 2]),
                .resp_valid(resp_valid[s]),
                .resp_ready(resp_ready[s]),
                .resp_status(resp_status[s*4 +: 4]),
                .resp_ack(resp_ack[s*3 +: 3]),
                .resp_rdata(resp_rdata[s*32 +: 32]),
                .resp_data_valid(resp_data_valid[s]),
                .resp_attempts(resp_attempts[s*9 +: 9]),
                .swdio_in(swdio_input),
                .swclk(swclk_internal),
                .swdio_out(swdio_out_internal),
                .swdio_oe(swdio_oe_internal)
            );

            assign cmd_ready[s] = allowed && cmd_ready_internal;

            // SWCLK is always low while disabled/reset and never mirrored.
            OBUF u_swclk_pad (
                .I(swclk_internal && allowed),
                .O(swclk_io[s])
            );

            // Xilinx IOBUF.T == 1 means Hi-Z. Especially important while
            // the target returns ACK/data/parity after SWD turnaround.
            IOBUF u_swdio_pad (
                .I(swdio_out_internal),
                .T(!(allowed && swdio_oe_internal)),
                .O(swdio_input),
                .IO(swdio_io[s])
            );
        end
    endgenerate
endmodule
