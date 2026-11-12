# Pipelined MAC

A signed SystemVerilog multiply-add unit (`y = a * b + c`) with one-, two-
and three-stage elastic pipelines. The experiment compares pipeline placement,
latency, cell area and post-route setup timing in SKY130 HD.

Default widths are `DATA_W=16` and `ACC_W=32`. Each input transaction supplies
its own `c`; the unit does not maintain a running sum across transactions.

## Recorded results

| Variant | Unstalled latency | Best tested setup-passing period | Frequency | Worst setup slack | Cell area |
|---|---:|---:|---:|---:|---:|
| 1-stage | 1 cycle | 5.6250 ns | 177.78 MHz | +0.0870 ns | 15,272 µm² |
| 2-stage | 2 cycles | 5.5781 ns | 179.27 MHz | +0.0484 ns | 18,086 µm² |
| 3-stage | 3 cycles | 5.9844 ns | 167.10 MHz | +0.0324 ns | 19,754 µm² |

These are separate place-and-route runs at each variant's selected period,
not an exact Fmax measurement. All three failed the initial 200 MHz target.
The sweep classifies setup timing using worst setup slack >= 0.

The 2-stage result is about **0.84% higher in frequency** and **18.4% larger
in cell area** than the 1-stage result at their respective selected points.
That small frequency difference is an observation from these runs; repeated
physical runs were not used to establish a general advantage.

The saved setup reports place the worst path in the multiplication stage of
both deeper variants. The extra input stage does not partition that block.
[Timing-path evidence](docs/TIMING_PATHS.md) separates these observations from
causal claims about the frequency difference.

All variants can accept one operation per cycle when the pipeline can advance.
Backpressure increases transaction latency and can reduce throughput.

[Full sweep](results/clock_sweep/clock_sweep.md) ·
[Fixed 200 MHz comparison](results/ppa/ppa_summary.md) ·
[Selected implementations and raw reports](results/fmax/)

## Run RTL verification

From the repository root, with Python 3 and Icarus Verilog (`iverilog`, `vvp`) installed:

```bash
bash verification/run_all.sh
```

The active runner compiles `rtl/mac_1stage.sv`, `rtl/mac_2stage.sv` and
`rtl/mac_3stage.sv` against `tb/tb_mac_compare.sv`. Each variant checks 1000
transactions with directed signed cases, random inputs and random downstream
backpressure. The scoreboard checks values and order; the testbench also
checks output stability during stalls and enforces a timeout.

The same command also runs 33 parameter/reset simulations: all three variants
at 11 width pairs, including product truncation, sign extension and 33-bit
operands. Python integer goldens check fresh traffic after resets of a partially
filled pipeline, a full stalled pipeline and flowing traffic. An empty repeated
reset and two deliberate RTL fault injections check the test's sensitivity.
[Recorded matrix and source hashes](verification/results/parameter_reset/results.md)
describe the finite tested range.

Logs and waveforms are written under `results/logs/` and `results/waves/`.
Cache and physical-runner regression checks run without Docker:

```bash
python3 -m unittest discover -s verification -p 'test_reproducibility.py' -v
```

## Design and measurement guide

See [design, interface and physical methodology](docs/DESIGN_AND_MEASUREMENTS.md)
for pipeline boundaries, signed-width behavior, timing constraints, report
provenance, physical-run commands and saved layout images.

Physical scripts resolve the clone location from their own paths. New runs
use the digest and platform pinned in [`physical/environment.json`](physical/environment.json).
`ORFS_IMAGE` overrides must also use a full digest; mutable tags are rejected.

Sweep caches check hashes of RTL, flow configs, scripts, generated constraints
and the selected image/platform before reuse or summary inclusion. Legacy and
incomplete records are excluded. New sweep outputs go to `build/clock_sweep/`;
the saved historical reports under `results/` are preserved. The environment
pin applies to new runs and is not retroactive evidence for those reports.

The tested width/reset matrix is not an exhaustive parameter or formal proof.
Power values are flow
estimates without workload-derived switching activity and are not used to
claim an energy improvement. No silicon or FPGA-board result is claimed.
