#!/usr/bin/env bash

set -euo pipefail

REPO="$HOME/pipelined-mac"
IMAGE="openroad/orfs:latest"

WORK="$REPO/physical/work"

mkdir -p \
    "$WORK/results" \
    "$WORK/reports" \
    "$WORK/logs" \
    "$WORK/objects"

run_design() {

    DESIGN="$1"

    echo
    echo "========================================"
    echo "Running ${DESIGN}..."
    echo "========================================"

    docker run --rm \
        -v "$REPO:/work/pipelined-mac" \
        -v "$WORK/results:/OpenROAD-flow-scripts/flow/results" \
        -v "$WORK/reports:/OpenROAD-flow-scripts/flow/reports" \
        -v "$WORK/logs:/OpenROAD-flow-scripts/flow/logs" \
        -v "$WORK/objects:/OpenROAD-flow-scripts/flow/objects" \
        -e MAC_REPO=/work/pipelined-mac \
        "$IMAGE" \
        bash -lc "

            set -e

            cd /OpenROAD-flow-scripts/flow

            echo
            echo '=== CLEAN ${DESIGN} ==='

            env -u MAKEFLAGS make -j1 \
                DESIGN_CONFIG=/work/pipelined-mac/physical/orfs/${DESIGN}.mk \
                YOSYS_EXE=/usr/local/bin/yosys \
                OPENROAD_EXE=/OpenROAD-flow-scripts/tools/install/OpenROAD/bin/openroad \
                clean_all

            echo
            echo '=== RUN ${DESIGN} ==='

            env -u MAKEFLAGS make -j1 \
                DESIGN_CONFIG=/work/pipelined-mac/physical/orfs/${DESIGN}.mk \
                YOSYS_EXE=/usr/local/bin/yosys \
                OPENROAD_EXE=/OpenROAD-flow-scripts/tools/install/OpenROAD/bin/openroad

        "

    echo
    echo "SUCCESS: ${DESIGN}"
}

run_design mac_1stage
run_design mac_2stage
run_design mac_3stage

echo
echo "========================================"
echo "ALL PHYSICAL RUNS FINISHED"
echo "========================================"
