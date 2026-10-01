#!/usr/bin/env bash

set -euo pipefail

mkdir -p build
mkdir -p results
mkdir -p results/logs
mkdir -p results/waves

run_test() {

    NAME="$1"
    MODULE="$2"
    RTL="$3"

    echo
    echo "Testing: $NAME"

    rm -f results/pipelined_mac.vcd

    iverilog \
        -g2012 \
        -Wall \
        -DDUT="$MODULE" \
        -s tb_pipelined_mac \
        -o "build/${NAME}.vvp" \
        "$RTL" \
        tb/tb_mac_compare.sv

    vvp "build/${NAME}.vvp" \
        | tee "results/logs/${NAME}.log"

    if [ -f results/pipelined_mac.vcd ]; then
        mv \
            results/pipelined_mac.vcd \
            "results/waves/${NAME}.vcd"
    fi
}

run_test \
    "mac_1stage" \
    "mac_1stage" \
    "rtl/mac_1stage.sv"

run_test \
    "mac_2stage" \
    "mac_2stage" \
    "rtl/mac_2stage.sv"

run_test \
    "mac_3stage" \
    "mac_3stage" \
    "rtl/mac_3stage.sv"

echo
echo "ALL REGRESSIONS PASSED"
