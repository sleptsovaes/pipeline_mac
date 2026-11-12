# Pipelined MAC

A signed SystemVerilog multiply-add unit (`y = a * b + c`) with one-, two-
and three-stage elastic pipelines. The experiment compares pipeline placement,
latency, cell area and post-route setup timing in SKY130 HD.

Default widths are `DATA_W=16` and `ACC_W=32`. Each input transaction supplies
its own `c`; the unit does not maintain a running sum across transactions.

## Recorded results

| Variant | Unstalled latency | Best tested setup-passing period | Frequency | Final setup WNS | Cell area |
|---|---:|---:|---:|---:|---:|
| 1-stage | 1 cycle | 5.6250 ns | 177.78 MHz | +0.0870 ns | 15,272 µm² |
| 2-stage | 2 cycles | 5.5781 ns | 179.27 MHz | +0.0484 ns | 18,086 µm² |
| 3-stage | 3 cycles | 5.9844 ns | 167.10 MHz | +0.0324 ns | 19,754 µm² |

These are separate place-and-route runs at each variant's selected period,
not an exact Fmax measurement. All three failed the initial 200 MHz target.
The sweep classifies setup timing using final WNS >= 0.

The 2-stage result is about **0.84% higher in frequency** and **18.4% larger
in cell area** than the 1-stage result at their respective selected points.
That small frequency difference is an observation from these runs; repeated
physical runs were not used to establish a general advantage.

All variants can accept one operation per cycle when the pipeline can advance.
Backpressure increases transaction latency and can reduce throughput.

[Full sweep](results/clock_sweep/clock_sweep.md) ·
[Fixed 200 MHz comparison](results/ppa/ppa_summary.md) ·
[Selected implementations and raw reports](results/fmax/)

## Run RTL verification

From the repository root, with Icarus Verilog (`iverilog`, `vvp`) installed:

```bash
bash verification/run_all.sh
```

The active runner compiles `rtl/mac_1stage.sv`, `rtl/mac_2stage.sv` and
`rtl/mac_3stage.sv` against `tb/tb_mac_compare.sv`. Each variant checks 1000
transactions with directed signed cases, random inputs and random downstream
backpressure. The scoreboard checks values and order; the testbench also
checks output stability during stalls and enforces a timeout.

Logs and waveforms are written under `results/logs/` and `results/waves/`.
The older `rtl/mac_2stage_old.sv` and `tb/tb_pipelined_mac.sv` are not used by
this runner or the current physical configurations.

## Design and measurement guide

See [design, interface and physical methodology](docs/DESIGN_AND_MEASUREMENTS.md)
for pipeline boundaries, signed-width behavior, timing constraints, report
provenance, physical-run commands and saved layout images.

Physical reproduction still has known gaps: several scripts assume a clone
at `~/pipelined-mac`, the flow uses the mutable `openroad/orfs:latest` image,
and sweep caches are not tied to source hashes. These are not resolved by
reformatting the reports. Do not reuse old cached metrics after changing RTL,
constraints or tools.

The default-width RTL regression is not evidence of a complete parameter
sweep or reset recovery with transactions in flight. Power values are flow
estimates without workload-derived switching activity and are not used to
claim an energy improvement. No silicon or FPGA-board result is claimed.
