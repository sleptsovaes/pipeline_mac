set clk_name core_clock
set clk_period 5.0

create_clock \
    -name $clk_name \
    -period $clk_period \
    [get_ports clk]

set_input_delay \
    0.5 \
    -clock [get_clocks $clk_name] \
    [get_ports in_valid]

set_input_delay \
    0.5 \
    -clock [get_clocks $clk_name] \
    [get_ports out_ready]

set_input_delay \
    0.5 \
    -clock [get_clocks $clk_name] \
    [get_ports a*]

set_input_delay \
    0.5 \
    -clock [get_clocks $clk_name] \
    [get_ports b*]

set_input_delay \
    0.5 \
    -clock [get_clocks $clk_name] \
    [get_ports c*]

set_output_delay \
    0.5 \
    -clock [get_clocks $clk_name] \
    [get_ports in_ready]

set_output_delay \
    0.5 \
    -clock [get_clocks $clk_name] \
    [get_ports out_valid]

set_output_delay \
    0.5 \
    -clock [get_clocks $clk_name] \
    [get_ports y*]

set_false_path \
    -from [get_ports rst_n]
