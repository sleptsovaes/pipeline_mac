`timescale 1ns/1ps

`ifndef DUT
`define DUT mac_2stage
`endif


module tb_pipelined_mac;

    parameter int DATA_W = 16;
    parameter int ACC_W  = 32;
    parameter int N_TX   = 1000;

    logic clk;
    logic rst_n;

    logic in_valid;
    logic in_ready;

    logic signed [DATA_W-1:0] a;
    logic signed [DATA_W-1:0] b;
    logic signed [ACC_W-1:0]  c;

    logic out_valid;
    logic out_ready;

    logic signed [ACC_W-1:0] y;

    `DUT #(
        .DATA_W(DATA_W),
        .ACC_W(ACC_W)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),

        .in_valid(in_valid),
        .in_ready(in_ready),

        .a(a),
        .b(b),
        .c(c),

        .out_valid(out_valid),
        .out_ready(out_ready),

        .y(y)
    );

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end


    initial begin
        rst_n = 1'b0;

        repeat (4)
            @(posedge clk);

        @(negedge clk);
        #1;
        rst_n = 1'b1;
    end


    function automatic logic signed [ACC_W-1:0] model_mac (
        input logic signed [DATA_W-1:0] a_i,
        input logic signed [DATA_W-1:0] b_i,
        input logic signed [ACC_W-1:0]  c_i
    );

        logic signed [(2*DATA_W)-1:0] product;
        logic signed [ACC_W-1:0] product_extended;

        begin
            product = a_i * b_i;
            product_extended = product;

            model_mac = product_extended + c_i;
        end

    endfunction


    logic signed [ACC_W-1:0] expected [0:N_TX-1];

    integer write_ptr;
    integer read_ptr;
    integer accepted;
    integer received;

    always @(posedge clk) begin

        if (!rst_n) begin
            write_ptr = 0;
            read_ptr  = 0;
            accepted  = 0;
            received  = 0;
        end
        else begin

            if (in_valid && in_ready) begin

                expected[write_ptr] =
                    model_mac(a, b, c);

                write_ptr = write_ptr + 1;
                accepted  = accepted + 1;

            end


            if (out_valid && out_ready) begin

                if (read_ptr >= write_ptr) begin
                    $fatal(
                        1,
                        "Output produced without expected transaction"
                    );
                end

                if (y !== expected[read_ptr]) begin

                    $display("");
                    $display("FAIL");
                    $display("Transaction: %0d", read_ptr);
                    $display(
                        "Expected: %0d",
                        $signed(expected[read_ptr])
                    );
                    $display(
                        "Received: %0d",
                        $signed(y)
                    );
                    $display("");

                    $fatal(1, "MAC result mismatch");

                end

                read_ptr = read_ptr + 1;
                received = received + 1;

            end

        end

    end


    logic last_input_fire;
    logic input_pending;

    integer generated;

    always @(posedge clk) begin

        if (!rst_n)
            last_input_fire <= 1'b0;
        else
            last_input_fire <= in_valid && in_ready;

    end


    always @(negedge clk) begin

        if (!rst_n) begin

            in_valid = 1'b0;

            a = '0;
            b = '0;
            c = '0;

            input_pending = 1'b0;
            generated = 0;

        end
        else begin

            if (input_pending && last_input_fire)
                input_pending = 1'b0;


            if (!input_pending) begin

                if (generated < N_TX) begin

                    if ((generated < 8) ||
                        ($urandom_range(0, 3) != 0)) begin

                        in_valid = 1'b1;
                        input_pending = 1'b1;

                        case (generated)

                            0: begin
                                a = 0;
                                b = 0;
                                c = 0;
                            end

                            1: begin
                                a = 1;
                                b = 1;
                                c = 0;
                            end

                            2: begin
                                a = -1;
                                b = 1;
                                c = 0;
                            end

                            3: begin
                                a = -3;
                                b = 7;
                                c = 5;
                            end

                            4: begin
                                a = {
                                    1'b0,
                                    {(DATA_W-1){1'b1}}
                                };

                                b = {
                                    1'b0,
                                    {(DATA_W-1){1'b1}}
                                };

                                c = 0;
                            end

                            5: begin
                                a = {
                                    1'b1,
                                    {(DATA_W-1){1'b0}}
                                };

                                b = 1;
                                c = 0;
                            end

                            6: begin
                                a = -17;
                                b = -23;
                                c = -100;
                            end

                            7: begin
                                a = 123;
                                b = -456;
                                c = 789;
                            end

                            default: begin
                                a = $urandom;
                                b = $urandom;
                                c = $urandom;
                            end

                        endcase

                        generated = generated + 1;

                    end
                    else begin
                        in_valid = 1'b0;
                    end

                end
                else begin
                    in_valid = 1'b0;
                end

            end

        end

    end


    always @(negedge clk) begin

        if (!rst_n)
            out_ready = 1'b0;
        else
            out_ready =
                ($urandom_range(0, 3) != 0);

    end


    logic signed [ACC_W-1:0] previous_y;
    logic previous_stall;

    always @(posedge clk) begin

        if (!rst_n) begin

            previous_y <= '0;
            previous_stall <= 1'b0;

        end
        else begin

            if (previous_stall) begin

                if (!out_valid)
                    $fatal(
                        1,
                        "out_valid dropped during backpressure"
                    );

                if (y !== previous_y)
                    $fatal(
                        1,
                        "Output changed during backpressure"
                    );

            end

            previous_y <= y;

            previous_stall <=
                out_valid && !out_ready;

        end

    end


    initial begin

        wait(rst_n);

        repeat (10000) begin

            @(posedge clk);

            if (received == N_TX) begin

                $display("");
                $display("        TEST PASSED");
                $display("Transactions generated : %0d", generated);
                $display("Transactions accepted  : %0d", accepted);
                $display("Transactions received  : %0d", received);
                $display("");

                $finish;

            end

        end

        $display("");
        $display("Generated: %0d", generated);
        $display("Accepted : %0d", accepted);
        $display("Received : %0d", received);

        $fatal(1, "Simulation timeout");

    end


    initial begin

        $dumpfile("results/pipelined_mac.vcd");
        $dumpvars(0, tb_pipelined_mac);

    end

endmodule
