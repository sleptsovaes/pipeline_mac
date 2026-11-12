`timescale 1ns/1ps
`ifndef DUT
`define DUT mac_2stage
`endif

module tb_mac_parameter_reset;
    parameter int DATA_W = 16;
    parameter int ACC_W = 32;
    parameter int STAGES = 2;
    parameter int N_VECTORS = 1;
    localparam int VECTOR_W = 2*DATA_W + 2*ACC_W;

    logic clk = 0, rst_n = 0;
    logic in_valid = 0, in_ready, out_valid, out_ready = 0;
    logic [DATA_W-1:0] a = '0, b = '0;
    logic [ACC_W-1:0] c = '0, y, expected_input = '0;
    logic [VECTOR_W-1:0] vectors [0:N_VECTORS-1];
    logic [ACC_W-1:0] expected [0:N_VECTORS+15];
    logic [ACC_W-1:0] stalled_value;
    bit was_stalled = 0;
    integer head = 0, tail = 0;
    integer accepted = 0, received = 0, cancelled = 0, resets = 0;
    integer stall_cycles = 0, cycles = 0;
    integer random_seed = 12345, unused;
    string vector_file;

    `DUT #(.DATA_W(DATA_W), .ACC_W(ACC_W)) dut (.*);
    always #5 clk = ~clk;

    // Expected values come from Python integer arithmetic, not an RTL MAC model.
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            head = 0;
            tail = 0;
            was_stalled = 0;
        end else begin
            if ((in_ready !== 1'b0 && in_ready !== 1'b1) ||
                (out_valid !== 1'b0 && out_valid !== 1'b1))
                $fatal(1, "Unknown handshake signal: in_ready=%b out_valid=%b", in_ready, out_valid);
            if (was_stalled && (out_valid !== 1'b1 || y !== stalled_value))
                $fatal(1, "Output changed or disappeared during a stall");
            if (out_valid && out_ready) begin
                if (head >= tail)
                    $fatal(1, "Output without a post-reset accepted transaction");
                if (y !== expected[head])
                    $fatal(1, "Arithmetic mismatch: got %h expected %h", y, expected[head]);
                head = head + 1;
                received = received + 1;
            end
            if (in_valid && in_ready) begin
                if (tail > N_VECTORS+15) $fatal(1, "Scoreboard overflow");
                expected[tail] = expected_input;
                tail = tail + 1;
                accepted = accepted + 1;
            end
            was_stalled = out_valid && !out_ready;
            stalled_value = y;
            if (was_stalled) stall_cycles = stall_cycles + 1;
        end
    end

    always @(posedge clk) begin
        cycles = cycles + 1;
        if (cycles > 20000) $fatal(1, "Parameter/reset test timed out");
    end

    task automatic offer(input integer index, input bit random_backpressure);
        bit taken;
        begin
            @(negedge clk);
            {a, b, c, expected_input} = vectors[index];
            in_valid = 1;
            if (random_backpressure) out_ready = ($urandom_range(0, 3) != 0);
            taken = 0;
            while (!taken) begin
                @(posedge clk);
                taken = (in_ready === 1'b1);
                if (!taken) begin
                    @(negedge clk);
                    if (random_backpressure) out_ready = ($urandom_range(0, 3) != 0);
                end
            end
        end
    endtask

    task automatic cancel_with_reset(input bit expect_pending, input bit short_pulse);
        integer pending;
        begin
            // Assert away from a clock edge; a short pulse has no rising edge.
            @(negedge clk);
            #1;
            pending = tail-head;
            if (expect_pending && pending == 0) $fatal(1, "Reset scenario was not exercised");
            if (!expect_pending && pending != 0) $fatal(1, "Expected an empty pipeline");
            cancelled = cancelled + pending;
            resets = resets + 1;
            rst_n = 0;
            in_valid = 0;
            out_ready = 0;
            #1;
            if (out_valid !== 1'b0) $fatal(1, "Asynchronous reset did not clear out_valid");
            if (short_pulse) #1;
            else begin
                repeat (2) @(posedge clk);
                @(negedge clk);
                #1;
            end
            rst_n = 1;
            out_ready = 1;
            repeat (STAGES+3) begin
                @(posedge clk);
                #1;
                if (out_valid !== 1'b0)
                    $fatal(1, "Stale transaction appeared after reset");
            end
        end
    endtask

    initial begin : scenarios
        integer i, before_block;
        if (!$value$plusargs("VECTORS=%s", vector_file)) $fatal(1, "Missing vectors");
        if ($value$plusargs("SEED=%d", random_seed)) begin end
        unused = $urandom(random_seed);
        $readmemh(vector_file, vectors);
        repeat (2) @(posedge clk);
        @(negedge clk);
        #1;
        rst_n = 1;

        // One pending transaction; in deeper variants it is still internal.
        offer(0, 0);
        cancel_with_reset(1, 1);

        // Fill every stage, stall the consumer and leave an unaccepted input.
        out_ready = 0;
        for (i=0; i<STAGES; i=i+1) offer(i % N_VECTORS, 0);
        @(negedge clk);
        if (out_valid !== 1'b1 || in_ready !== 1'b0 || tail-head != STAGES)
            $fatal(1, "Full stalled pipeline scenario was not exercised");
        before_block = accepted;
        {a, b, c, expected_input} = vectors[0];
        in_valid = 1;
        repeat (2) begin
            @(posedge clk);
            #1;
            if (accepted != before_block) $fatal(1, "Blocked input was accepted");
        end
        cancel_with_reset(1, 0);

        // Reset during flowing traffic after some outputs have been consumed.
        for (i=0; i<4; i=i+1) offer(i % N_VECTORS, 0);
        cancel_with_reset(1, 1);
        cancel_with_reset(0, 1);

        // Fresh traffic must recover and preserve the Python-oracle sequence.
        for (i=0; i<N_VECTORS; i=i+1) offer(i, 1);
        @(negedge clk);
        in_valid = 0;
        out_ready = 1;
        while (head != tail) begin
            @(posedge clk);
            #1;
        end
        repeat (STAGES+3) begin
            @(posedge clk);
            #1;
            if (out_valid !== 1'b0) $fatal(1, "Unexpected extra output after draining");
        end
        if (head != N_VECTORS || tail != N_VECTORS || resets != 4 || stall_cycles == 0)
            $fatal(1, "Incomplete scenario coverage");
        if (accepted != received+cancelled || cancelled != 1+2*STAGES)
            $fatal(1, "Transaction accounting mismatch");
        $display("PARAM_RESET_PASS data=%0d acc=%0d stages=%0d checked=%0d cancelled=%0d resets=%0d",
                 DATA_W, ACC_W, STAGES, head, cancelled, resets);
        $finish;
    end
endmodule
