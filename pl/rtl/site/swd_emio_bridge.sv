// Zynq-7000 PS EMIO GPIO -> PYNQ-Z2 PMODB. GPIO_T: 1=Hi-Z.
// PS GPIO EMIO offsets [0..2] are NOT Linux gpiochip numbers.
// Not a hardware SWD master. No DUT may be connected until electrical HIL.
module swd_emio_bridge (
    input  logic [63:0] gpio_o,
    input  logic [63:0] gpio_t,
    output logic [63:0] gpio_i,
    inout  wire         swclk_io,
    inout  wire         swdio_io,
    inout  wire         nrst_io
);
    wire swclk_input;
    wire swdio_input;
    wire nrst_input;

    // True bidirectional buffers permit Linux libgpiod to switch GPIO
    // directions during SWD turnaround without push-pull bus contention.
    IOBUF swclk_buf (
        .I(gpio_o[0]), .T(gpio_t[0]), .O(swclk_input), .IO(swclk_io)
    );
    IOBUF swdio_buf (
        .I(gpio_o[1]), .T(gpio_t[1]), .O(swdio_input), .IO(swdio_io)
    );
    // nRESET is strictly open-drain: only drive low or float. Never drive high.
    // Requires target-side pull-up and validated voltage/protection.
    IOBUF nrst_buf (
        .I(1'b0), .T(gpio_t[2] | gpio_o[2]), .O(nrst_input), .IO(nrst_io)
    );

    // All unused EMIO GPIO read as 0 and have no PL output attachment.
    always_comb begin
        gpio_i = '0;
        gpio_i[0] = swclk_input;
        gpio_i[1] = swdio_input;
        gpio_i[2] = nrst_input;
    end
endmodule
