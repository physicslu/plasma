// Verification-only checker for ONE ABI-v5 SWD Site:
// pl/rtl/swd/plasma_swd_site_axi_lite.sv + plasma_swd_transaction_engine.sv.
//
// Executed by Icarus 11 during the cocotb regressions. Icarus supports
// immediate assertions but neither concurrent `assert property` nor `bind`,
// so every rule is an immediate assertion over registered history, and the
// test wrappers instantiate this module with hierarchical references into
// the Site. Temporal SVA/bind semantics are NOT claimed. Never synthesised.
//
// The checker samples on the same FCLK edge as the RTL, so combinational
// inputs (cmd_enqueue, cmd_dequeue, ...) describe the transition taking
// effect at this edge, and registered inputs hold their pre-edge value.
// A shadow model of the command / in-flight / response queues checks
// snapshot and ordering rules independently of the RTL pointers.
// Every failure prints "PLASMA_SVA <rule>" and ends the simulation.
module plasma_swd_site_checks (
    input logic clk, rst_n,
    // Site registers and queue control
    input logic [1:0] mode_q,
    input logic normal_enable_q, fault_q,
    input logic [7:0] idle_cycles_q,
    input logic [15:0] half_q,
    input logic [4:0] cmd_level_q, resp_level_q,
    input logic cmd_enqueue, cmd_dequeue, cmd_flush,
    input logic resp_enqueue, resp_dequeue,
    input logic [31:0] data_w,
    input logic [15:0] active_tag,
    input logic [66:0] resp_head,
    input logic drive_clk, drive_oe,
    // Transaction engine
    input logic busy, resp_valid, resp_ready, cmd_ready,
    input logic [3:0] resp_status,
    input logic [2:0] resp_ack,
    input logic [31:0] resp_rdata,
    input logic resp_data_valid,
    input logic [8:0] resp_attempts,
    input logic [7:0] cmd_idle_cycles,
    input logic [15:0] cmd_half_period,
    input logic [3:0] phase,
    input logic [7:0] engine_idle_q,
    input logic [15:0] engine_half_q,
    input logic [31:0] elapsed, timeout_q,
    input logic swclk, swdio_oe, swdio_out
);
    localparam logic [3:0] PH_IDLE = 4'd9;
    localparam integer QD = 64;

    // Shadow queues: command FIFO {tag, idle, half}, in-flight tag, responses.
    logic [15:0] c_tag [0:QD-1];
    logic [7:0] c_idle [0:QD-1];
    logic [15:0] c_half [0:QD-1];
    logic [15:0] r_tag [0:QD-1];
    integer c_head, c_count, r_head, r_count;
    logic inflight;
    logic [15:0] inflight_tag;
    logic check_active;
    logic [15:0] expect_active;

    // History
    logic [1:0] p_mode;
    logic p_valid, p_fault, p_busy, p_enable, p_resp_valid, p_swclk;
    logic [4:0] p_cmd_level, p_resp_level;
    logic p_resp_hold, p_head_hold, p_fault_cause, p_flush;
    logic [48:0] p_response;
    logic [66:0] p_resp_head;
    integer idle_rises, high_cycles;

    wire [48:0] response = {resp_status, resp_ack, resp_rdata,
                            resp_data_valid, resp_attempts};
    wire cut = resp_valid && (resp_status == 4'd7 || resp_status == 4'd8);

    task automatic fail(input string rule);
        $display("PLASMA_SVA %s at %0t", rule, $time);
        $fatal(1, "PLASMA_SVA %s", rule);
    endtask

    always @(posedge clk) begin
        if (!rst_n) begin
            c_head = 0; c_count = 0; r_head = 0; r_count = 0;
            inflight = 1'b0; check_active = 1'b0;
            p_valid <= 1'b0;
            idle_rises = 0; high_cycles = 0;
        end else begin
            // ---- Site register invariants --------------------------------
            if (cmd_level_q > 5'd16 || resp_level_q > 5'd16)
                fail("fifo_level_bound");
            if (idle_cycles_q < 8'd8)
                fail("idle_cycles_range");
            if (mode_q == 2'd0 && idle_cycles_q != 8'd8)
                fail("idle_cycles_default_when_off");
            if (!(mode_q == 2'd1 && normal_enable_q) && (drive_clk || drive_oe))
                fail("pads_released_unless_normal_enabled");
            if (fault_q && cmd_dequeue)
                fail("fault_stops_dispatch");
            if (cmd_flush && !fault_q)
                fail("discard_only_on_fault");

            if (p_valid) begin
                if (mode_q != p_mode &&
                    (p_busy || p_resp_valid || p_enable ||
                     p_cmd_level != 0 || p_resp_level != 0))
                    fail("mode_change_only_when_quiescent");
                if (fault_q && !p_fault && !p_fault_cause)
                    fail("fault_latched_only_by_parity_timeout_abort");
                if (!fault_q && p_fault &&
                    (p_busy || p_resp_valid || p_cmd_level != 0))
                    fail("fault_cleared_only_when_drained");
                if (p_flush && cmd_level_q != 0)
                    fail("discard_empties_command_fifo");
                if (p_head_hold && resp_head != p_resp_head)
                    fail("retained_response_immutable");
            end

            // ---- Shadow queues: snapshot and ordering --------------------
            if (check_active && active_tag != expect_active)
                fail("dispatch_in_push_order");
            check_active = 1'b0;
            if (resp_enqueue) begin
                if (!inflight || active_tag != inflight_tag)
                    fail("completion_tag_is_dispatched_tag");
                inflight = 1'b0;
                r_tag[(r_head + r_count) % QD] = active_tag;
                r_count = r_count + 1;
            end
            if (resp_dequeue) begin
                if (r_count == 0 || data_w[15:0] != r_tag[r_head])
                    fail("completions_popped_in_order");
                r_head = (r_head + 1) % QD;
                r_count = r_count - 1;
            end
            if (cmd_dequeue) begin
                if (c_count == 0)
                    fail("dispatch_from_empty_shadow");
                if (cmd_idle_cycles != c_idle[c_head])
                    fail("idle_cycles_snapshot_at_push");
                if (cmd_half_period != c_half[c_head])
                    fail("half_period_snapshot_at_push");
                if (inflight)
                    fail("single_command_in_flight");
                if (cmd_ready) begin
                    inflight = 1'b1;
                    inflight_tag = c_tag[c_head];
                    expect_active = c_tag[c_head];
                    check_active = 1'b1;
                end
                c_head = (c_head + 1) % QD;
                c_count = c_count - 1;
            end
            if (cmd_flush) begin
                c_count = 0;
            end
            if (cmd_enqueue) begin
                c_tag[(c_head + c_count) % QD] = data_w[31:16];
                c_idle[(c_head + c_count) % QD] = idle_cycles_q;
                c_half[(c_head + c_count) % QD] = half_q;
                c_count = c_count + 1;
            end

            // ---- Transaction engine --------------------------------------
            if (busy && resp_valid)
                fail("engine_busy_response_overlap");
            if (resp_data_valid && !(resp_status == 4'd0 && resp_ack == 3'd1))
                fail("read_data_only_on_ok");
            if (!busy && (swclk || swdio_oe))
                fail("engine_idle_releases_line");
            if (busy && !(timeout_q != 0 && elapsed < timeout_q))
                fail("bounded_completion");
            if (p_valid && p_resp_hold && (!resp_valid || response != p_response))
                fail("response_stable_until_consumed");

            // Trailing idle: exactly idle_q host-driven SWDIO-low clocks.
            if (busy && phase == PH_IDLE && !(swdio_oe && !swdio_out) && !cut)
                fail("idle_phase_drives_low");
            if (p_valid && !p_busy && busy)
                idle_rises = 0;
            if (swclk && !p_swclk && phase == PH_IDLE)
                idle_rises = idle_rises + 1;
            if (p_valid && p_busy && !busy && phase == PH_IDLE && !cut &&
                idle_rises != engine_idle_q)
                fail("idle_clock_count_equals_snapshot");

            // SWCLK HIGH lasts exactly the snapshotted half period.
            if (swclk)
                high_cycles = high_cycles + 1;
            if (p_valid && p_swclk && !swclk) begin
                if (!cut && high_cycles != engine_half_q)
                    fail("swclk_high_equals_half_period");
                high_cycles = 0;
            end

            // ---- History -------------------------------------------------
            p_valid <= 1'b1;
            p_mode <= mode_q;
            p_fault <= fault_q;
            p_busy <= busy;
            p_enable <= normal_enable_q;
            p_resp_valid <= resp_valid;
            p_swclk <= swclk;
            p_cmd_level <= cmd_level_q;
            p_resp_level <= resp_level_q;
            p_fault_cause <= resp_enqueue &&
                (resp_status == 4'd6 || resp_status == 4'd7 ||
                 resp_status == 4'd8);
            p_flush <= cmd_flush;
            p_resp_hold <= resp_valid && !resp_ready;
            p_response <= response;
            p_head_hold <= resp_level_q != 0 && !resp_dequeue;
            p_resp_head <= resp_head;
        end
    end

    // Shadow and RTL occupancy agree after every edge.
    always @(negedge clk) begin
        if (rst_n && p_valid) begin
            if (c_count != cmd_level_q)
                fail("command_level_matches_shadow");
            if (r_count != resp_level_q)
                fail("response_level_matches_shadow");
        end
    end
endmodule
