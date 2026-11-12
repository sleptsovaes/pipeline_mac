# MAC design and measurement guide

[Project overview and result table](../README.md)

## Arithmetic and interface

Each transaction computes `y = a * b + c` with signed two's-complement
operands. The product is `2*DATA_W` bits. It is sign-extended or truncated to
`ACC_W`, then added to the transaction's `c`. The output wraps to `ACC_W`
bits; there is no saturation or persistent accumulator state.

The active-low `rst_n` asynchronously clears valid bits and pipeline state.
An input is accepted at a rising clock edge with `in_valid && in_ready`.
An output is consumed at a rising edge with `out_valid && out_ready`.
A pending output must retain its value and validity while the consumer stalls.

| Variant | Arithmetic stages | Unstalled latency |
|---|---|---:|
| [`mac_1stage`](../rtl/mac_1stage.sv) | Multiply and add, then output register | 1 cycle |
| [`mac_2stage`](../rtl/mac_2stage.sv) | Registered product and delayed `c`, then add | 2 cycles |
| [`mac_3stage`](../rtl/mac_3stage.sv) | Input registers, registered product/delayed `c`, then add | 3 cycles |

The third variant adds input registers; it does not split the multiplier
internally. The saved worst setup paths for the selected 2- and 3-stage implementations
both traverse the multiplication stage. The [timing-path audit](TIMING_PATHS.md)
records their actual endpoints, setup slack and interpretation limits.

Elastic valid bits and ready propagation preserve transaction order. With no
stalls, the peak input rate is one operation per cycle for every variant;
adding stages changes latency rather than the arithmetic result.

## Verification scope

[`verification/run_all.sh`](../verification/run_all.sh) selects the three
current RTL modules using the `DUT` preprocessor definition and compiles the
shared [`tb_mac_compare.sv`](../tb/tb_mac_compare.sv) testbench.
It exercises 1000 transactions per variant, including directed boundary and
signed cases, random data, valid gaps and random output backpressure.
Accepted inputs enter a reference queue; consumed outputs are checked in
order. The bench also checks stable stalled outputs and detects timeouts.

The original 1000-transaction regression uses `DATA_W=16`, `ACC_W=32`.
[`run_parameter_reset.py`](../verification/run_parameter_reset.py) additionally
checks all three variants at these `(DATA_W, ACC_W)` pairs:
`(1,1)`, `(2,3)`, `(4,4)`, `(4,8)`, `(4,12)`, `(8,16)`, `(8,24)`,
`(16,16)`, `(16,32)`, `(16,40)` and `(33,66)`.

Expected values use signed Python integers reduced modulo `2**ACC_W`, with
hand-calculated oracle goldens, directed boundaries and 256 seeded random
vectors per width pair. Wide operands and addends use all their bits rather
than a 32-bit-only random source. Each of the 33 runs checks four reset
scenarios: one pending operation, a full stalled pipeline with an unaccepted
input, flowing traffic and a repeated empty reset. Three pulses occur entirely
between rising edges, checking asynchronous cancellation; one reset spans two
clock edges. Fresh traffic after reset must match the oracle, preserve order
and hold output stable under randomized backpressure.

The runner also compiles temporary faulty copies of the 2-stage RTL. Incorrect
sign extension must produce an arithmetic mismatch; retaining a pending stage
across reset must produce a stale-transaction failure. These copies stay under
`build/parameter_reset/` and do not alter the design sources.
The [recorded report](../verification/results/parameter_reset/results.md) and
[JSON manifest](../verification/results/parameter_reset/results.json) include
counts, source/vector hashes, tool versions and the seed. New runs write
`build/parameter_reset/`; run the matrix alone with:

```bash
python3 verification/run_parameter_reset.py
```

This finite matrix does not establish all possible parameter combinations or
an unbounded protocol proof. The obsolete `mac_2stage_old.sv` and
`tb_pipelined_mac.sv` were removed from the active checkout. Their previous
versions remain in Git history at `eb072acb619ad6516686323eb540c733c9ce1154`.
The active sources are the three numbered RTL variants and the two testbenches
selected by `run_all.sh` and `run_parameter_reset.py`.

## Physical experiment

The flow uses Yosys, OpenROAD Flow Scripts, OpenROAD/OpenSTA, SKY130 HD and
Docker. Each target proceeds through synthesis, placement, CTS, routing and
final timing analysis. The physical configs select the current RTL modules.

The [fixed constraint](../physical/constraints/mac_5ns.sdc) uses a 5 ns clock,
0.5 ns input/output delays for the data and handshake ports, and a false path
from `rst_n`. All three variants fail final setup timing at that target;
see the [200 MHz metrics](../results/ppa/ppa_summary.md).

The [sweep script](../scripts/clock_sweep.py) changes the period, runs the flow,
refines the observed passing/failing boundary and saves selected outputs.
Its PASS criterion is worst setup slack >= 0. Intermediate global-route slack
is a separate metric and must not be substituted for final setup slack.
The selected `6_report.json` files also report zero hold TNS and zero hold
violations; this is not a multi-corner signoff or measured silicon result.

Each period gets a separate implementation. The best tested passing target
is not an exact maximum operating frequency, and the result need not vary
monotonically with the requested clock. The 0.84% frequency difference is
small and was not assessed across repeated placement/routing runs.

Area comparisons use final cell area at each variant's own selected period.
They are not fixed-frequency area comparisons. In the separate fixed-5 ns
experiment, sequential-cell counts were 33, 98 and 163. The extra 65 bits per
stage agree with the default RTL state: a product or input payload, delayed
`c`, and a valid bit.

Power estimates in the reports do not use workload-derived switching
activity. They do not establish an energy-per-operation advantage.

## Saved evidence

- [Full sweep table](../results/clock_sweep/clock_sweep.md) and
  [machine-readable CSV](../results/clock_sweep/clock_sweep.csv).
- [Selected-period summary](../results/clock_sweep/fmax_summary.md).
- [1-stage record](../results/fmax/mac_1stage/best_run.json),
  [2-stage record](../results/fmax/mac_2stage/best_run.json),
  [3-stage record](../results/fmax/mac_3stage/best_run.json).
- Each selected directory contains final GDS, DEF, netlist, SDC, SPEF,
  `6_report.json`, `6_report.log` and `6_finish.rpt`.

The records are saved experiment outputs. Their values have not been
regenerated by this documentation update, and they do not contain a complete
source-hash or immutable container provenance record. Do not assign a digest
observed today to the historical runs retrospectively.

Selected routing images:

![1-stage routing](../results/fmax/mac_1stage/final_routing.webp.png)

![2-stage routing](../results/fmax/mac_2stage/final_routing.webp.png)

![3-stage routing](../results/fmax/mac_3stage/final_routing.webp.png)

[2-stage worst-path image](../results/fmax/mac_2stage/final_worst_path.webp.png)

## Physical rerun commands

The commands below assume the repository root. The scripts locate the clone
from their own paths, so they also work through absolute paths from another
working directory, including a renamed directory containing spaces.
Physical runs require Docker and Python 3; plotting additionally requires
Matplotlib. The image reference and platform are pinned in
[`physical/environment.json`](../physical/environment.json).

Check the selected environment and input hashes without starting Docker:

```bash
python3 scripts/clock_sweep.py --check-inputs
```

Run the fixed-5 ns physical comparison and collect its metrics:

```bash
bash physical/run_orfs.sh
python3 scripts/collect_ppa.py
```

The fixed-constraint runner saves input hashes and the selected environment
in `physical/work/run_manifest.json`, with tool version output in per-design
`physical/work/logs/*.driver.log`. New summary tables go to `build/ppa/`.
An input manifest records a selected run; only the subsequent flow logs and
reports establish whether it completed.

Run a new sweep and plot its results:

```bash
python3 scripts/clock_sweep.py
python3 scripts/plot_sweep.py
```

The default sweep directory is `build/clock_sweep/`. It contains per-point
JSON records and flow logs, `run_manifest.json`, summary CSV/Markdown, a
`work/` directory for ORFS, and confirmed selected implementations in `best/`.
To keep a separate experiment, use `clock_sweep.py --output <directory>` and
pass its CSV/output directory explicitly to `plot_sweep.py --input ... --output ...`.

To plot the saved historical CSV without rerunning the physical flow:

```bash
python3 scripts/plot_sweep.py \
  --input results/clock_sweep/clock_sweep.csv \
  --output build/historical_plots
```

The default image was resolved from the official ORFS registry metadata on
12 November 2026. This is a new environment selection, not a recovered digest
for the historical MAC runs. An `ORFS_IMAGE` override must be an immutable
`repository@sha256:<64 hex digits>` reference. The platform is fixed by the
configuration; image changes invalidate cache records.

## Cache validity and measurement status

Each new point stores a provenance fingerprint covering all RTL sources,
flow makefiles, physical scripts/configuration, selected image/platform and
the exact generated SDC for that period. The generated SDC text is hashed
instead of the previous point's mutable `mac_sweep.sdc` file. The sweep still
rewrites that file when it starts a point.

A cache hit requires matching provenance, design and period, a completed flow
and consistent final setup metrics. Legacy records without provenance,
malformed records and failed/incomplete flows are not reused. The summary
loader applies the same checks, so old cached points cannot re-enter the
result table through a different path. Input changes during a run prevent
that result from being cached. `--force` bypasses a valid cache hit.

Each selected passing point is rerun before its artifact snapshot is saved.
The summary is then rebuilt from the post-confirmation records. If this rerun
fails, its old selected snapshot/result is removed from the new output area.
The original saved measurements in `results/` are not changed by this process.

The cache tests simulate flow outcomes and input changes; they do not perform
place and route. No new physical measurement or timing-closure result is
claimed by this infrastructure update. Running the full flow with Docker is
still needed to validate the newly pinned image on this design. Parameter
combinations beyond the tested width matrix, formal protocol proofs and
repeated physical runs remain future work.
