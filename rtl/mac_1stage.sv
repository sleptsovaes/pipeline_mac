module mac_1stage #(
    parameter int DATA_W = 16,
    parameter int ACC_W  = 32
) (
    input  logic clk,
    input  logic rst_n,

    input  logic in_valid,
    output logic in_ready,

    input  logic [DATA_W-1:0] a,
    input  logic [DATA_W-1:0] b,
    input  logic [ACC_W-1:0]  c,

    output logic out_valid,
    input  logic out_ready,

    output logic [ACC_W-1:0] y
);

    localparam int PROD_W = 2 * DATA_W;

    logic stage_valid;

    logic [PROD_W-1:0] product_comb;
    logic [ACC_W-1:0]  product_resized;

    assign product_comb =
        $signed(a) * $signed(b);

    generate

        if (ACC_W >= PROD_W) begin : gen_extend

            assign product_resized = {
                {(ACC_W-PROD_W){product_comb[PROD_W-1]}},
                product_comb
            };

        end
        else begin : gen_truncate

            assign product_resized =
                product_comb[ACC_W-1:0];

        end

    endgenerate

    assign in_ready  =
        ~stage_valid | out_ready;

    assign out_valid =
        stage_valid;

    always_ff @(posedge clk or negedge rst_n) begin

        if (!rst_n) begin

            stage_valid <= 1'b0;
            y           <= '0;

        end
        else if (in_ready) begin

            stage_valid <= in_valid;

            if (in_valid) begin

                y <= product_resized + c;

            end

        end

    end

endmodule
