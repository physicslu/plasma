// MPE AXI4-Lite transaction/control vertical slice (HOST-ONLY CANDIDATE).
// NOT the completed FIFO/IRQ-capable product ABI, NOT Vivado/PS/HIL qualified.
// Address family is NEW, deliberately incompatible with RemoteBitbang GPIO.
//   0x43C00000 global identity; 0x43C01000 SITE 1 JA; 0x43C02000 SITE 2 JB.
// One in-flight command per Site, independent engines, retained completion
// until matching tagged POP. No blind retry, no legacy RTL/driver imports.
// Separate AW/W acceptance, full-word WSTRB and backpressure are mandatory.
// This source-only slice does NOT falsely advertise the planned 16-deep FIFO.
// Registers within each Site window:
//  0x00 ID/CAP, 0x04 STATUS, 0x08 HALF, 0x0C TIMEOUT,
//  0x10 TX_DATA, 0x14 CMD_PUSH, 0x18 DONE_META, 0x1C DONE_DATA,
//  0x20 DONE_POP, 0x24 FIFO_LEVELS (zero command, 0/1 result),
//  0x28 CONTROL (bit0 enable, bit1 abort), 0x2C ERROR_LATCH,
//  0x30 IRQ_ENABLE, 0x34 IRQ_STATUS (W1C deferred; level event).
// CMD_PUSH: [31:16] nonzero tag, [8] line_reset,
// [3:2] word address, [1] read, [0] AP; reserved [15:9],[7:4]=0.
// For reset, low 8 bits must all be zero; no other command is accepted.
// All writes use WSTRB 4'b1111 and aligned 32-bit address, or SLVERR.
// Only two Sites are physically implemented. No external power/NRST/OE.
module plasma_mpe_swd_axi_lite #(
    parameter logic [31:0] AXI_BASE_ADDRESS = 32'h43C00000
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
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *)
    output wire s_axi_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *)
    input logic [31:0] s_axi_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *)
    input logic [3:0] s_axi_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *)
    input logic s_axi_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *)
    output wire s_axi_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *)
    output logic [1:0] s_axi_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *)
    output logic s_axi_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *)
    input logic s_axi_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *)
    input logic [31:0] s_axi_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *)
    input logic [2:0] s_axi_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *)
    input logic s_axi_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *)
    output wire s_axi_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *)
    output logic [31:0] s_axi_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *)
    output logic [1:0] s_axi_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *)
    output logic s_axi_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RREADY" *)
    input logic s_axi_rready,
    output wire [1:0] swclk_io,
    inout wire [1:0] swdio_io,
    output wire [1:0] site_irq
);
    localparam logic [1:0] OKAY = 2'b00, SLVERR = 2'b10;
    localparam logic [31:0] MAGIC = 32'h4D504531;  // "MPE1"
    localparam logic [31:0] ABI = 32'h00010000;
    localparam logic [31:0] PRESENT = 32'h00000003;

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

    logic [1:0] enable_q, abort_q, launch_q, consume_q, irq_enable_q;
    logic [15:0] half_q [0:1];
    logic [31:0] timeout_q [0:1], data_q [0:1], active_tag [0:1];
    logic [8:0] command_q [0:1];
    logic [1:0] fault_q;
    logic [1:0] cmd_ready, busy, resp_valid, resp_data_valid;
    wire [3:0] resp_status [0:1];
    wire [2:0] resp_ack [0:1];
    wire [31:0] resp_data [0:1];
    wire [8:0] resp_attempts [0:1];
    wire [1:0] link_state [0:1];

    wire [1:0] cmd_op_bus, cmd_ap_bus, cmd_read_bus;
    wire [7:0] cmd_addr_bus;
    wire [63:0] cmd_wdata_bus, cmd_timeout_bus;
    wire [31:0] cmd_half_bus;
    wire [5:0] cmd_turn_bus;
    wire [15:0] cmd_idle_bus, cmd_retries_bus;
    wire [1:0] cmd_error_phase_bus;

    for (genvar g = 0; g < 2; g = g + 1) begin : g_cmd
        assign cmd_op_bus[g] = command_q[g][8];
        assign cmd_ap_bus[g] = command_q[g][0];
        assign cmd_read_bus[g] = command_q[g][1];
        assign cmd_addr_bus[g*4 +: 4] = {command_q[g][3:2], 2'b00};
        assign cmd_wdata_bus[g*32 +: 32] = data_q[g];
        assign cmd_timeout_bus[g*32 +: 32] = timeout_q[g];
        assign cmd_half_bus[g*16 +: 16] = half_q[g];
        assign cmd_turn_bus[g*3 +: 3] = 3'd1;
        assign cmd_idle_bus[g*8 +: 8] = 8'd8;
        assign cmd_retries_bus[g*8 +: 8] = 8'd0;
        assign cmd_error_phase_bus[g] = 1'b0;
        assign site_irq[g] = resp_valid[g] && irq_enable_q[g];
    end

    plasma_mpe_dual_swd_core #(.SITE_COUNT(2)) u_mpe (
        .clk(s_axi_aclk), .rst_n(s_axi_aresetn),
        .site_enable(enable_q),
        .cmd_valid(launch_q), .cmd_ready(cmd_ready),
        .cmd_abort(abort_q),
        .cmd_op(cmd_op_bus), .cmd_ap(cmd_ap_bus), .cmd_read(cmd_read_bus),
        .cmd_addr(cmd_addr_bus), .cmd_wdata(cmd_wdata_bus),
        .cmd_half_period(cmd_half_bus), .cmd_turnaround(cmd_turn_bus),
        .cmd_idle_cycles(cmd_idle_bus), .cmd_max_retries(cmd_retries_bus),
        .cmd_error_data_phase(cmd_error_phase_bus),
        .cmd_timeout_cycles(cmd_timeout_bus),
        .busy(busy), .link_state({link_state[1],link_state[0]}),
        .resp_valid(resp_valid), .resp_ready(consume_q),
        .resp_status({resp_status[1],resp_status[0]}),
        .resp_ack({resp_ack[1],resp_ack[0]}),
        .resp_rdata({resp_data[1],resp_data[0]}),
        .resp_data_valid(resp_data_valid),
        .resp_attempts({resp_attempts[1],resp_attempts[0]}),
        .swclk_io(swclk_io), .swdio_io(swdio_io)
    );

    function automatic logic correct_window(input logic [31:0] address);
        correct_window =
            address[31:16] == AXI_BASE_ADDRESS[31:16] &&
            address[15:12] >= 4'd1 && address[15:12] <= 4'd2 &&
            address[11:8] == 4'd0 && address[7:6] == 2'b00 &&
            address[1:0] == 2'b00;
    endfunction

    always_ff @(posedge s_axi_aclk) begin : axi_sequential
        if (!s_axi_aresetn) begin
            aw_hold <= 1'b0; w_hold <= 1'b0;
            aw_q <= '0; wd_q <= '0; strobe_q <= '0;
            s_axi_bvalid <= 1'b0; s_axi_bresp <= OKAY;
            s_axi_rvalid <= 1'b0; s_axi_rresp <= OKAY;
            s_axi_rdata <= 32'd0;
            enable_q <= 2'b00; abort_q <= 2'b00;
            launch_q <= 2'b00; consume_q <= 2'b00;
            irq_enable_q <= 2'b00; fault_q <= 2'b00;
            for (int n = 0; n < 2; n = n + 1) begin
                half_q[n] <= 16'd500;
                timeout_q[n] <= 32'd1000000;
                data_q[n] <= 32'd0;
                command_q[n] <= 9'd0;
                active_tag[n] <= 32'd0;
            end
        end else begin
            launch_q <= 2'b00; abort_q <= 2'b00; consume_q <= 2'b00;
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 1'b0;
            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 1'b0;
            if (take_aw) begin aw_hold <= 1'b1; aw_q <= s_axi_awaddr; end
            if (take_w) begin
                w_hold <= 1'b1; wd_q <= s_axi_wdata; strobe_q <= s_axi_wstrb;
            end

            for (int n = 0; n < 2; n = n + 1)
                if (resp_valid[n] &&
                    (resp_status[n] == 4'd6 || resp_status[n] == 4'd7 ||
                     resp_status[n] == 4'd8))
                    fault_q[n] <= 1'b1;

            if (commit) begin : write_transaction
                int n;
                n = (addr_w[15:12] == 4'd2) ? 1 : 0;
                aw_hold <= 1'b0; w_hold <= 1'b0;
                s_axi_bvalid <= 1'b1; s_axi_bresp <= SLVERR;
                if (strb_w == 4'hF && correct_window(addr_w)) begin
                    case (addr_w[7:0])
                        8'h08: if (!busy[n] && !resp_valid[n] && !launch_q[n] &&
                                   data_w[31:16] == 0 && data_w[15:0] >= 2) begin
                            half_q[n] <= data_w[15:0];
                            s_axi_bresp <= OKAY;
                        end
                        8'h0C: if (!busy[n] && !resp_valid[n] && !launch_q[n] &&
                                   data_w != 0) begin
                            timeout_q[n] <= data_w;
                            s_axi_bresp <= OKAY;
                        end
                        8'h10: if (!busy[n] && !resp_valid[n] && !launch_q[n]) begin
                            data_q[n] <= data_w;
                            s_axi_bresp <= OKAY;
                        end
                        8'h14: if (enable_q[n] && !fault_q[n] &&
                                   cmd_ready[n] && !launch_q[n] &&
                                   data_w[31:16] != 0 &&
                                   data_w[15:9] == 0 && data_w[7:4] == 0 &&
                                   (data_w[8] == 0 || data_w[7:0] == 0)) begin
                            active_tag[n] <= {16'd0, data_w[31:16]};
                            command_q[n] <= {data_w[8],data_w[7:0]};
                            launch_q[n] <= 1'b1;
                            s_axi_bresp <= OKAY;
                        end
                        8'h20: if (resp_valid[n] &&
                                   data_w == active_tag[n] && !consume_q[n]) begin
                            consume_q[n] <= 1'b1;
                            s_axi_bresp <= OKAY;
                        end
                        8'h28: if (data_w[31:2] == 0 &&
                                   !(data_w[1] && !busy[n])) begin
                            enable_q[n] <= data_w[0];
                            abort_q[n] <= data_w[1];
                            s_axi_bresp <= OKAY;
                        end
                        8'h30: if (data_w[31:1] == 0) begin
                            irq_enable_q[n] <= data_w[0];
                            s_axi_bresp <= OKAY;
                        end
                        default: s_axi_bresp <= SLVERR;
                    endcase
                end
            end

            if (take_ar) begin : read_transaction
                int n;
                n = (s_axi_araddr[15:12] == 4'd2) ? 1 : 0;
                s_axi_rvalid <= 1'b1; s_axi_rresp <= SLVERR;
                s_axi_rdata <= 32'd0;
                if (s_axi_araddr == AXI_BASE_ADDRESS) begin
                    s_axi_rdata <= MAGIC; s_axi_rresp <= OKAY;
                end else if (s_axi_araddr == AXI_BASE_ADDRESS + 32'd4) begin
                    s_axi_rdata <= ABI; s_axi_rresp <= OKAY;
                end else if (s_axi_araddr == AXI_BASE_ADDRESS + 32'd8) begin
                    s_axi_rdata <= PRESENT; s_axi_rresp <= OKAY;
                end else if (correct_window(s_axi_araddr)) begin
                    case (s_axi_araddr[7:0])
                        8'h00: begin
                            s_axi_rdata <= 32'h00010000 | (n + 1);
                            s_axi_rresp <= OKAY;
                        end
                        8'h04: begin
                            s_axi_rdata <= {28'd0, fault_q[n],resp_valid[n],busy[n],enable_q[n]};
                            s_axi_rresp <= OKAY;
                        end
                        8'h08: begin
                            s_axi_rdata <= {16'd0,half_q[n]};
                            s_axi_rresp <= OKAY;
                        end
                        8'h0C: begin
                            s_axi_rdata <= timeout_q[n];
                            s_axi_rresp <= OKAY;
                        end
                        8'h18: begin
                            // Completion is immutable until matching POP.
                            s_axi_rdata <= {active_tag[n][15:0], 2'd0,
                                link_state[n],resp_attempts[n][3:0],
                                resp_data_valid[n],resp_ack[n],resp_status[n]};
                            s_axi_rresp <= OKAY;
                        end
                        8'h1C: begin
                            s_axi_rdata <= resp_data[n];
                            s_axi_rresp <= OKAY;
                        end
                        8'h24: begin
                            s_axi_rdata <= {30'd0,resp_valid[n],1'b0};
                            s_axi_rresp <= OKAY;
                        end
                        8'h28: begin
                            s_axi_rdata <= {31'd0,enable_q[n]};
                            s_axi_rresp <= OKAY;
                        end
                        8'h2C: begin
                            s_axi_rdata <= {31'd0,fault_q[n]};
                            s_axi_rresp <= OKAY;
                        end
                        8'h30: begin
                            s_axi_rdata <= {31'd0,irq_enable_q[n]};
                            s_axi_rresp <= OKAY;
                        end
                        8'h34: begin
                            s_axi_rdata <= {31'd0,site_irq[n]};
                            s_axi_rresp <= OKAY;
                        end
                        default: s_axi_rresp <= SLVERR;
                    endcase
                end
            end
        end
    end
endmodule
