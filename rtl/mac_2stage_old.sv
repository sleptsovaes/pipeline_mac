module pipelined_mac #(
    parameter int DATA_W = 16,
    parameter int ACC_W  = 32
) (
    input  logic clk,
    input  logic rst_n,

    input  logic in_valid,
    output logic in_ready,

    input  logic signed [DATA_W-1:0] a,
    input  logic signed [DATA_W-1:0] b,
    input  logic signed [ACC_W-1:0]  c,

    output logic out_valid,
    input  logic out_ready,

    output logic signed [ACC_W-1:0] y
);

    localparam int PROD_W = 2 * DATA_W;

    logic stage1_valid;
    logic stage2_valid;

    logic signed [PROD_W-1:0] product_stage1;
    logic signed [ACC_W-1:0]  c_stage1;

    logic stage1_ready;
    logic stage2_ready;

    logic signed [ACC_W-1:0] product_extended;

    assign stage2_ready = ~stage2_valid | out_ready;
    assign stage1_ready = ~stage1_valid | stage2_ready;

    assign in_ready  = stage1_ready;
    assign out_valid = stage2_valid;

    assign product_extended =
        {{(ACC_W-PROD_W){product_stage1[PROD_W-1]}},
         product_stage1};

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            stage1_valid   <= 1'b0;
            stage2_valid   <= 1'b0;

            product_stage1 <= '0;
            c_stage1       <= '0;
            y              <= '0;
        end else begin

            if (stage2_ready) begin
                stage2_valid <= stage1_valid;

                if (stage1_valid) begin
                    y <= product_extended + c_stage1;
                end
            end

            if (stage1_ready) begin
                stage1_valid <= in_valid;

                if (in_valid) begin
                    product_stage1 <= $signed(a) * $signed(b);
                    c_stage1       <= c;
                end
            end

        end
    end

endmodule
