module mac_3stage #(
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

    logic stage1_valid;
    logic stage2_valid;
    logic stage3_valid;


    /*
     * Stage 1 registers
     */

    logic [DATA_W-1:0] a_stage1;
    logic [DATA_W-1:0] b_stage1;
    logic [ACC_W-1:0]  c_stage1;


    /*
     * Stage 2 registers
     */

    logic [PROD_W-1:0] product_stage2;
    logic [ACC_W-1:0]  c_stage2;


    /*
     * Product width conversion
     */

    logic [ACC_W-1:0] product_resized;


    /*
     * Elastic pipeline ready signals
     */

    logic stage1_ready;
    logic stage2_ready;
    logic stage3_ready;


    generate

        if (ACC_W >= PROD_W) begin : gen_extend

            assign product_resized = {
                {(ACC_W-PROD_W){product_stage2[PROD_W-1]}},
                product_stage2
            };

        end
        else begin : gen_truncate

            assign product_resized =
                product_stage2[ACC_W-1:0];

        end

    endgenerate


    /*
     * Backpressure propagation
     */

    assign stage3_ready =
        ~stage3_valid | out_ready;

    assign stage2_ready =
        ~stage2_valid | stage3_ready;

    assign stage1_ready =
        ~stage1_valid | stage2_ready;


    assign in_ready =
        stage1_ready;

    assign out_valid =
        stage3_valid;


    always_ff @(posedge clk or negedge rst_n) begin

        if (!rst_n) begin

            stage1_valid <= 1'b0;
            stage2_valid <= 1'b0;
            stage3_valid <= 1'b0;

            a_stage1 <= '0;
            b_stage1 <= '0;
            c_stage1 <= '0;

            product_stage2 <= '0;
            c_stage2       <= '0;

            y <= '0;

        end
        else begin

            /*
             * Stage 3
             *
             * accumulation
             */

            if (stage3_ready) begin

                stage3_valid <= stage2_valid;

                if (stage2_valid) begin

                    y <= product_resized + c_stage2;

                end

            end


            /*
             * Stage 2
             *
             * multiplication
             */

            if (stage2_ready) begin

                stage2_valid <= stage1_valid;

                if (stage1_valid) begin

                    product_stage2 <=
                        $signed(a_stage1) *
                        $signed(b_stage1);

                    c_stage2 <= c_stage1;

                end

            end


            /*
             * Stage 1
             *
             * input registers
             */

            if (stage1_ready) begin

                stage1_valid <= in_valid;

                if (in_valid) begin

                    a_stage1 <= a;
                    b_stage1 <= b;
                    c_stage1 <= c;

                end

            end

        end

    end

endmodule
