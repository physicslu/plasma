// Host loopback Command ABI v1. No external PL I/O.
module swd_command_axi_lite #(
    parameter logic [31:0] AXI_BASE_ADDRESS = 32'h40002000
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aclk, ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET s_axi_aresetn, FREQ_HZ 100000000" *)
    input  logic         s_axi_aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 s_axi_aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aresetn, POLARITY ACTIVE_LOW" *)
    input  logic         s_axi_aresetn,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWADDR" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 32, FREQ_HZ 100000000" *)
    input  logic [31:0]  s_axi_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *)
    input  logic [2:0]   s_axi_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *)
    input  logic         s_axi_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *)
    output logic         s_axi_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *)
    input  logic [31:0]  s_axi_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *)
    input  logic [3:0]   s_axi_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *)
    input  logic         s_axi_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *)
    output logic         s_axi_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *)
    output logic [1:0]   s_axi_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *)
    output logic         s_axi_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *)
    input  logic         s_axi_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *)
    input  logic [31:0]  s_axi_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *)
    input  logic [2:0]   s_axi_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *)
    input  logic         s_axi_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *)
    output logic         s_axi_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *)
    output logic [31:0]  s_axi_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *)
    output logic [1:0]   s_axi_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *)
    output logic         s_axi_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RREADY" *)
    input  logic         s_axi_rready
);
    localparam logic [31:0] REG_ABI = AXI_BASE_ADDRESS;
    localparam logic [31:0] REG_COMMAND = AXI_BASE_ADDRESS + 32'h04;
    localparam logic [31:0] REG_TX = AXI_BASE_ADDRESS + 32'h08;
    localparam logic [31:0] REG_COUNT = AXI_BASE_ADDRESS + 32'h0c;
    localparam logic [31:0] REG_HALF = AXI_BASE_ADDRESS + 32'h10;
    localparam logic [31:0] REG_DRIVE = AXI_BASE_ADDRESS + 32'h14;
    localparam logic [31:0] REG_RX = AXI_BASE_ADDRESS + 32'h18;
    localparam logic [31:0] REG_STATUS = AXI_BASE_ADDRESS + 32'h1c;
    localparam logic [31:0] REG_ERROR = AXI_BASE_ADDRESS + 32'h20;
    localparam logic [31:0] REG_MODE = AXI_BASE_ADDRESS + 32'h24;
    localparam logic [31:0] REG_PATTERN = AXI_BASE_ADDRESS + 32'h28;

    logic aw_pending, w_pending;
    logic [31:0] aw_addr_q, w_data_q;
    logic [3:0] w_strb_q;
    logic [31:0] tx_cfg, count_cfg, half_cfg, drive_cfg, mode_cfg, pattern_cfg;
    logic [31:0] rx_result, error_code;
    logic done_sticky, error_sticky;
    logic engine_start, soft_reset;
    wire engine_busy, engine_done, engine_error;
    wire swclk, swdio_out, swdio_oe, swdio_in;
    wire [31:0] engine_rx;
    wire active = engine_busy || engine_start || soft_reset;
    wire engine_resetn = s_axi_aresetn && !soft_reset;
    wire accept_aw = s_axi_awvalid && s_axi_awready;
    wire accept_w = s_axi_wvalid && s_axi_wready;
    wire accept_ar = s_axi_arvalid && s_axi_arready;
    wire [31:0] write_addr = accept_aw ? s_axi_awaddr : aw_addr_q;
    wire [31:0] write_data = accept_w ? s_axi_wdata : w_data_q;
    wire [3:0] write_strb = accept_w ? s_axi_wstrb : w_strb_q;

    assign s_axi_awready = s_axi_aresetn && !aw_pending && !s_axi_bvalid;
    assign s_axi_wready = s_axi_aresetn && !w_pending && !s_axi_bvalid;
    assign s_axi_arready = s_axi_aresetn && !s_axi_rvalid;

    function automatic logic [31:0] merge_bytes(
        input logic [31:0] previous, input logic [31:0] data, input logic [3:0] strb
    );
        merge_bytes = previous;
        for (int lane = 0; lane < 4; lane++)
            if (strb[lane]) merge_bytes[8*lane +: 8] = data[8*lane +: 8];
    endfunction

    // First semantic error wins until CLEAR, valid START or RESET.
    // Invalid addresses/RO writes only set AXI SLVERR, not this error latch.
    task automatic reject_command(input logic [31:0] code);
        s_axi_bresp <= 2'b10;
        error_sticky <= 1'b1;
        if (!error_sticky) error_code <= code;
    endtask

    swd_waveform_engine engine (
        .clk(s_axi_aclk), .rst_n(engine_resetn), .start(engine_start),
        .tx_data(tx_cfg), .bit_count(count_cfg[5:0]),
        .half_period_cycles(half_cfg[15:0]), .drive_enable(drive_cfg[0]),
        .swdio_in(swdio_in), .swclk(swclk), .swdio_out(swdio_out),
        .swdio_oe(swdio_oe), .rx_data(engine_rx), .busy(engine_busy),
        .done(engine_done), .error(engine_error)
    );
    pl_loopback_responder responder (
        .clk(s_axi_aclk), .rst_n(engine_resetn), .start(engine_start),
        .pattern(pattern_cfg), .pattern_mode(mode_cfg[0]), .swclk(swclk),
        .swdio_out(swdio_out), .swdio_oe(swdio_oe), .swdio_in(swdio_in)
    );

    always_ff @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            aw_pending <= 1'b0;
            w_pending <= 1'b0;
            aw_addr_q <= '0;
            w_data_q <= '0;
            w_strb_q <= '0;
            s_axi_bvalid <= 1'b0;
            s_axi_bresp <= 2'b00;
            s_axi_rvalid <= 1'b0;
            s_axi_rresp <= 2'b00;
            s_axi_rdata <= '0;
            tx_cfg <= '0;
            count_cfg <= '0;
            half_cfg <= 32'd2;
            drive_cfg <= '0;
            mode_cfg <= '0;
            pattern_cfg <= '0;
            rx_result <= '0;
            done_sticky <= 1'b0;
            error_sticky <= 1'b0;
            error_code <= '0;
            engine_start <= 1'b0;
            soft_reset <= 1'b0;
        end else begin
            engine_start <= 1'b0;
            soft_reset <= 1'b0;
            // Capture completion before command arbitration. A valid new START
            // or RESET wins for flags; START retains the completed RX result.
            if (engine_done && !soft_reset) begin
                rx_result <= engine_rx;
                done_sticky <= 1'b1;
                if (engine_error) begin
                    error_sticky <= 1'b1;
                    if (!error_sticky) error_code <= 32'd4;
                end
            end
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 1'b0;
            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 1'b0;
            if (accept_aw) begin
                aw_pending <= 1'b1;
                aw_addr_q <= s_axi_awaddr;
            end
            if (accept_w) begin
                w_pending <= 1'b1;
                w_data_q <= s_axi_wdata;
                w_strb_q <= s_axi_wstrb;
            end
            if (!s_axi_bvalid && (aw_pending || accept_aw) && (w_pending || accept_w)) begin
                aw_pending <= 1'b0;
                w_pending <= 1'b0;
                s_axi_bvalid <= 1'b1;
                s_axi_bresp <= 2'b00;
                case (write_addr)
                    REG_COMMAND: begin
                        if (write_strb == 0) begin
                            // A zero-strobe write at this valid RW/WO address is a no-op.
                        end else if (write_strb != 4'hf ||
                            (write_data != 1 && write_data != 2 && write_data != 4)) begin
                            reject_command(32'd1);
                        end else if (write_data == 4) begin
                            soft_reset <= 1'b1;
                            tx_cfg <= '0; count_cfg <= '0; half_cfg <= 32'd2;
                            drive_cfg <= '0; mode_cfg <= '0; pattern_cfg <= '0;
                            rx_result <= '0; done_sticky <= 1'b0;
                            error_sticky <= 1'b0; error_code <= '0;
                        end else if (active) begin
                            reject_command(32'd2);
                        end else if (write_data == 2) begin
                            done_sticky <= 1'b0; error_sticky <= 1'b0; error_code <= '0;
                        end else if (count_cfg == 0 || count_cfg > 32 || half_cfg < 2 || half_cfg > 65535) begin
                            reject_command(32'd3);
                        end else begin
                            engine_start <= 1'b1;
                            done_sticky <= 1'b0; error_sticky <= 1'b0; error_code <= '0;
                        end
                    end
                    REG_TX, REG_COUNT, REG_HALF, REG_DRIVE, REG_MODE, REG_PATTERN: begin
                        if (write_strb == 0) begin
                        end else if (active) begin
                            reject_command(32'd2);
                        end else begin
                            case (write_addr)
                                REG_TX: tx_cfg <= merge_bytes(tx_cfg, write_data, write_strb);
                                REG_PATTERN: pattern_cfg <= merge_bytes(pattern_cfg, write_data, write_strb);
                                REG_COUNT: begin
                                    if (merge_bytes(count_cfg, write_data, write_strb) < 1 ||
                                        merge_bytes(count_cfg, write_data, write_strb) > 32) reject_command(32'd3);
                                    else count_cfg <= merge_bytes(count_cfg, write_data, write_strb);
                                end
                                REG_HALF: begin
                                    if (merge_bytes(half_cfg, write_data, write_strb) < 2 ||
                                        merge_bytes(half_cfg, write_data, write_strb) > 65535) reject_command(32'd3);
                                    else half_cfg <= merge_bytes(half_cfg, write_data, write_strb);
                                end
                                REG_DRIVE: begin
                                    if (merge_bytes(drive_cfg, write_data, write_strb) > 1) reject_command(32'd3);
                                    else drive_cfg <= merge_bytes(drive_cfg, write_data, write_strb);
                                end
                                REG_MODE: begin
                                    if (merge_bytes(mode_cfg, write_data, write_strb) > 1) reject_command(32'd3);
                                    else mode_cfg <= merge_bytes(mode_cfg, write_data, write_strb);
                                end
                                default: begin end
                            endcase
                        end
                    end
                    default: s_axi_bresp <= 2'b10;
                endcase
            end
            if (accept_ar) begin
                s_axi_rvalid <= 1'b1;
                s_axi_rresp <= 2'b00;
                case (s_axi_araddr)
                    REG_ABI: s_axi_rdata <= 32'd1;
                    REG_COMMAND: s_axi_rdata <= '0;
                    REG_TX: s_axi_rdata <= tx_cfg;
                    REG_COUNT: s_axi_rdata <= count_cfg;
                    REG_HALF: s_axi_rdata <= half_cfg;
                    REG_DRIVE: s_axi_rdata <= drive_cfg;
                    REG_RX: s_axi_rdata <= rx_result;
                    REG_STATUS: s_axi_rdata <= {26'b0, swdio_oe, swdio_out, swclk, error_sticky, done_sticky, active};
                    REG_ERROR: s_axi_rdata <= error_code;
                    REG_MODE: s_axi_rdata <= mode_cfg;
                    REG_PATTERN: s_axi_rdata <= pattern_cfg;
                    default: begin s_axi_rdata <= '0; s_axi_rresp <= 2'b10; end
                endcase
            end
        end
    end
endmodule
