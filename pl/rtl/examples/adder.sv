module adder #(
    parameter int WIDTH = 8
) (
    input  logic [WIDTH-1:0] a,
    input  logic [WIDTH-1:0] b,
    output logic [WIDTH:0]   sum
);

    always_comb begin
        sum = {1'b0, a} + {1'b0, b};
    end

endmodule
