// Test-only harness: separate PS GPIO and external target drive ownership.
module swd_emio_bridge_tb (
    input  logic [63:0] gpio_o,
    input  logic [63:0] gpio_t,
    output logic [63:0] gpio_i,
    input  logic [2:0] ext_oe,
    input  logic [2:0] ext_data,
    output wire swclk_pin,
    output wire swdio_pin,
    output wire nrst_pin
);
    tri swclk_net;
    tri swdio_net;
    tri nrst_net;

    assign swclk_net = ext_oe[0] ? ext_data[0] : 1'bz;
    assign swdio_net = ext_oe[1] ? ext_data[1] : 1'bz;
    assign nrst_net = ext_oe[2] ? ext_data[2] : 1'bz;

    assign swclk_pin = swclk_net;
    assign swdio_pin = swdio_net;
    assign nrst_pin = nrst_net;

    swd_emio_bridge dut (
        .gpio_o(gpio_o), .gpio_t(gpio_t), .gpio_i(gpio_i),
        .swclk_io(swclk_net), .swdio_io(swdio_net), .nrst_io(nrst_net)
    );
endmodule
