`timescale 1ns / 1ps

// AXI4-Lite register boundary for the Plasma PS<->PL diagnostic loopback.
//
// Register map (byte offsets):
//   0x000 MAGIC        RO  0x504C4C42 ("PLLB")
//   0x004 VERSION      RO  1
//   0x008 CAPABILITIES RO  [15:0]=max payload bytes, bit16=CRC32, bit17=echo
//   0x00C CONTROL      WO  bit0=START, bit1=CLEAR
//   0x010 STATUS       RO  bit0=READY, bit1=BUSY, bit2=DONE, bit3=ERROR
//   0x014 COMMAND      RW  1=ECHO
//   0x018 SEQUENCE     RW
//   0x01C LENGTH       RW  1..64
//   0x020 TX_CRC32     RW  IEEE CRC32/zlib convention
//   0x024 RX_SEQUENCE  RO
//   0x028 RX_LENGTH    RO
//   0x02C RX_CRC32     RO
//   0x030 ERROR_CODE   RO  0=none, 1=command, 2=length, 3=TX CRC
//   0x040..0x07C TX_DATA[0..15]  RW, little-endian bytes
//   0x080..0x0BC RX_DATA[0..15]  RO, little-endian bytes
//
// AW and W are accepted independently. One write response and one read response
// may be outstanding at a time; this deterministic control-plane boundary does
// not depend on AWVALID and WVALID arriving in the same cycle.
module plasma_pl_loopback_axi_lite #(
    parameter int unsigned MAX_PAYLOAD_BYTES = 64,
    parameter int unsigned AXI_ADDR_WIDTH = 12
) (
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aclk, ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET s_axi_aresetn" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *)
    input  logic                      s_axi_aclk,
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aresetn, POLARITY ACTIVE_LOW" *)
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 s_axi_aresetn RST" *)
    input  logic                      s_axi_aresetn,

    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 12" *)
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWADDR" *)
    input  logic [AXI_ADDR_WIDTH-1:0] s_axi_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *)
    input  logic [2:0]                s_axi_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *)
    input  logic                      s_axi_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *)
    output logic                      s_axi_awready,

    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *)
    input  logic [31:0]               s_axi_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *)
    input  logic [3:0]                s_axi_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *)
    input  logic                      s_axi_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *)
    output logic                      s_axi_wready,

    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *)
    output logic [1:0]                s_axi_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *)
    output logic                      s_axi_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *)
    input  logic                      s_axi_bready,

    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *)
    input  logic [AXI_ADDR_WIDTH-1:0] s_axi_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *)
    input  logic [2:0]                s_axi_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *)
    input  logic                      s_axi_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *)
    output logic                      s_axi_arready,

    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *)
    output logic [31:0]               s_axi_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *)
    output logic [1:0]                s_axi_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *)
    output logic                      s_axi_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RREADY" *)
    input  logic                      s_axi_rready
);
    localparam logic [31:0] MAGIC        = 32'h504C_4C42;
    localparam logic [31:0] VERSION      = 32'h0000_0001;
    localparam logic [31:0] CAPABILITIES = 32'h0003_0000;

    localparam logic [AXI_ADDR_WIDTH-1:0] REG_MAGIC       = 'h000;
    localparam logic [AXI_ADDR_WIDTH-1:0] REG_VERSION     = 'h004;
    localparam logic [AXI_ADDR_WIDTH-1:0] REG_CAPS        = 'h008;
    localparam logic [AXI_ADDR_WIDTH-1:0] REG_CONTROL     = 'h00C;
    localparam logic [AXI_ADDR_WIDTH-1:0] REG_STATUS      = 'h010;
    localparam logic [AXI_ADDR_WIDTH-1:0] REG_COMMAND     = 'h014;
    localparam logic [AXI_ADDR_WIDTH-1:0] REG_SEQUENCE    = 'h018;
    localparam logic [AXI_ADDR_WIDTH-1:0] REG_LENGTH      = 'h01C;
    localparam logic [AXI_ADDR_WIDTH-1:0] REG_TX_CRC32    = 'h020;
    localparam logic [AXI_ADDR_WIDTH-1:0] REG_RX_SEQUENCE = 'h024;
    localparam logic [AXI_ADDR_WIDTH-1:0] REG_RX_LENGTH   = 'h028;
    localparam logic [AXI_ADDR_WIDTH-1:0] REG_RX_CRC32    = 'h02C;
    localparam logic [AXI_ADDR_WIDTH-1:0] REG_ERROR_CODE  = 'h030;
    localparam logic [AXI_ADDR_WIDTH-1:0] REG_TX_DATA     = 'h040;
    localparam logic [AXI_ADDR_WIDTH-1:0] REG_RX_DATA     = 'h080;

    logic [AXI_ADDR_WIDTH-1:0] awaddr_q;
    logic [31:0]               wdata_q;
    logic [3:0]                wstrb_q;
    logic                      aw_pending_q;
    logic                      w_pending_q;

    logic [31:0] command_q;
    logic [31:0] sequence_q;
    logic [31:0] length_q;
    logic [31:0] tx_crc32_q;
    logic [7:0]  tx_mem [0:MAX_PAYLOAD_BYTES-1];
    logic [MAX_PAYLOAD_BYTES*8-1:0] tx_flat;

    logic core_start;
    logic core_clear;
    logic core_ready;
    logic core_busy;
    logic core_done;
    logic core_error;
    logic [31:0] core_rx_sequence;
    logic [31:0] core_rx_length;
    logic [31:0] core_rx_crc32;
    logic [31:0] core_error_code;
    logic [MAX_PAYLOAD_BYTES*8-1:0] core_rx_data;

    integer write_byte;
    integer read_byte;

    function automatic logic [31:0] apply_wstrb(
        input logic [31:0] previous,
        input logic [31:0] incoming,
        input logic [3:0]  strobe
    );
        logic [31:0] value;
        int lane;
        begin
            value = previous;
            for (lane = 0; lane < 4; lane = lane + 1) begin
                if (strobe[lane])
                    value[lane*8 +: 8] = incoming[lane*8 +: 8];
            end
            return value;
        end
    endfunction

    generate
        genvar g;
        for (g = 0; g < MAX_PAYLOAD_BYTES; g = g + 1) begin : gen_tx_flat
            assign tx_flat[g*8 +: 8] = tx_mem[g];
        end
    endgenerate

    plasma_pl_loopback_core #(
        .MAX_PAYLOAD_BYTES(MAX_PAYLOAD_BYTES)
    ) core (
        .clk(s_axi_aclk),
        .rst_n(s_axi_aresetn),
        .start(core_start),
        .clear(core_clear),
        .command(command_q),
        .sequence(sequence_q),
        .payload_length(length_q),
        .tx_crc32(tx_crc32_q),
        .tx_data(tx_flat),
        .ready(core_ready),
        .busy(core_busy),
        .done(core_done),
        .error(core_error),
        .rx_sequence(core_rx_sequence),
        .rx_length(core_rx_length),
        .rx_crc32(core_rx_crc32),
        .error_code(core_error_code),
        .rx_data(core_rx_data)
    );

    always_comb begin
        s_axi_awready = !aw_pending_q && !s_axi_bvalid;
        s_axi_wready  = !w_pending_q && !s_axi_bvalid;
        s_axi_bresp   = 2'b00;
        s_axi_arready = !s_axi_rvalid;
        s_axi_rresp   = 2'b00;
    end

    always_ff @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            awaddr_q     <= '0;
            wdata_q      <= '0;
            wstrb_q      <= '0;
            aw_pending_q <= 1'b0;
            w_pending_q  <= 1'b0;
            s_axi_bvalid <= 1'b0;
            command_q    <= 32'h1;
            sequence_q   <= 32'h0;
            length_q     <= 32'h0;
            tx_crc32_q   <= 32'h0;
            core_start   <= 1'b0;
            core_clear   <= 1'b0;
            for (write_byte = 0; write_byte < MAX_PAYLOAD_BYTES; write_byte = write_byte + 1)
                tx_mem[write_byte] <= 8'h00;
        end else begin
            core_start <= 1'b0;
            core_clear <= 1'b0;

            if (s_axi_awvalid && s_axi_awready) begin
                awaddr_q     <= s_axi_awaddr;
                aw_pending_q <= 1'b1;
            end
            if (s_axi_wvalid && s_axi_wready) begin
                wdata_q     <= s_axi_wdata;
                wstrb_q     <= s_axi_wstrb;
                w_pending_q <= 1'b1;
            end

            if (aw_pending_q && w_pending_q && !s_axi_bvalid) begin
                if (awaddr_q[1:0] == 2'b00) begin
                    case (awaddr_q)
                        REG_CONTROL: begin
                            if (wstrb_q[0]) begin
                                core_start <= wdata_q[0];
                                core_clear <= wdata_q[1];
                            end
                        end
                        REG_COMMAND:  command_q  <= apply_wstrb(command_q,  wdata_q, wstrb_q);
                        REG_SEQUENCE: sequence_q <= apply_wstrb(sequence_q, wdata_q, wstrb_q);
                        REG_LENGTH:   length_q   <= apply_wstrb(length_q,   wdata_q, wstrb_q);
                        REG_TX_CRC32: tx_crc32_q <= apply_wstrb(tx_crc32_q, wdata_q, wstrb_q);
                        default: begin
                            if (awaddr_q >= REG_TX_DATA && awaddr_q < (REG_TX_DATA + MAX_PAYLOAD_BYTES)) begin
                                for (write_byte = 0; write_byte < 4; write_byte = write_byte + 1) begin
                                    if (wstrb_q[write_byte])
                                        tx_mem[((((awaddr_q - REG_TX_DATA) >> 2) * 4) + write_byte)] <=
                                            wdata_q[write_byte*8 +: 8];
                                end
                            end
                        end
                    endcase
                end
                aw_pending_q <= 1'b0;
                w_pending_q  <= 1'b0;
                s_axi_bvalid <= 1'b1;
            end else if (s_axi_bvalid && s_axi_bready) begin
                s_axi_bvalid <= 1'b0;
            end
        end
    end

    logic [31:0] read_data;
    always_comb begin
        read_data = 32'h0;
        if (s_axi_araddr[1:0] == 2'b00) begin
            case (s_axi_araddr)
                REG_MAGIC:       read_data = MAGIC;
                REG_VERSION:     read_data = VERSION;
                REG_CAPS:        read_data = CAPABILITIES | MAX_PAYLOAD_BYTES;
                REG_STATUS:      read_data = {28'h0, core_error, core_done, core_busy, core_ready};
                REG_COMMAND:     read_data = command_q;
                REG_SEQUENCE:    read_data = sequence_q;
                REG_LENGTH:      read_data = length_q;
                REG_TX_CRC32:    read_data = tx_crc32_q;
                REG_RX_SEQUENCE: read_data = core_rx_sequence;
                REG_RX_LENGTH:   read_data = core_rx_length;
                REG_RX_CRC32:    read_data = core_rx_crc32;
                REG_ERROR_CODE:  read_data = core_error_code;
                default: begin
                    if (s_axi_araddr >= REG_TX_DATA && s_axi_araddr < (REG_TX_DATA + MAX_PAYLOAD_BYTES)) begin
                        for (read_byte = 0; read_byte < 4; read_byte = read_byte + 1)
                            read_data[read_byte*8 +: 8] =
                                tx_mem[((((s_axi_araddr - REG_TX_DATA) >> 2) * 4) + read_byte)];
                    end else if (s_axi_araddr >= REG_RX_DATA && s_axi_araddr < (REG_RX_DATA + MAX_PAYLOAD_BYTES)) begin
                        for (read_byte = 0; read_byte < 4; read_byte = read_byte + 1)
                            read_data[read_byte*8 +: 8] =
                                core_rx_data[(((((s_axi_araddr - REG_RX_DATA) >> 2) * 4) + read_byte) * 8) +: 8];
                    end
                end
            endcase
        end
    end

    always_ff @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            s_axi_rvalid <= 1'b0;
            s_axi_rdata  <= 32'h0;
        end else begin
            if (s_axi_arvalid && s_axi_arready) begin
                s_axi_rdata  <= read_data;
                s_axi_rvalid <= 1'b1;
            end else if (s_axi_rvalid && s_axi_rready) begin
                s_axi_rvalid <= 1'b0;
            end
        end
    end

    // Protection signals are intentionally not interpreted in PL. Access policy
    // is enforced at the OS/Gateway boundary; preserve the signals for AXI shape.
    logic unused_prot;
    assign unused_prot = ^{s_axi_awprot, s_axi_arprot};
endmodule
