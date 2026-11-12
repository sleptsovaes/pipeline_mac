# Review of saved MAC setup paths

Review date: 13 November 2026. This is an analysis of the saved physical
outputs, not a new implementation run. The source snapshot before the cleanup
is `eb072acb619ad6516686323eb540c733c9ce1154`; the raw reports are unchanged.
The selected targets use 16-bit operands, a 32-bit addend/result and SKY130 HD.

## Worst setup paths

The table uses the first global `Path Type: max` path in each `6_finish.rpt`.
Mapped flip-flop suffixes are omitted from the displayed register names.
Periods come from `best_run.json`; exact worst setup slack comes from
`finish__timing__setup__ws` in `6_report.json`.

| Variant | Selected period, ns | Worst setup path | Worst setup slack, ns | Saved evidence |
|---|---:|---|---:|---|
| 1-stage | 5.6250 | `b[1]` → `y[31]` | +0.0870295 | [Max setup path](../results/fmax/mac_1stage/6_finish.rpt#L92) · [JSON](../results/fmax/mac_1stage/6_report.json) |
| 2-stage | 5.5781 | `b[2]` → `product_stage1[30]` | +0.0483724 | [Max setup path](../results/fmax/mac_2stage/6_finish.rpt#L92) · [JSON](../results/fmax/mac_2stage/6_report.json) |
| 3-stage | 5.9844 | `b_stage1[2]` → `product_stage2[31]` | +0.0323843 | [Max setup path](../results/fmax/mac_3stage/6_finish.rpt#L92) · [JSON](../results/fmax/mac_3stage/6_report.json) |

The first detailed path printed in these files is a `min` path for hold
analysis. It is not the worst setup path. The `max` sections above answer
the setup-timing question.

## What the endpoints establish

The endpoint names are interpreted together with the current
[1-stage](../rtl/mac_1stage.sv), [2-stage](../rtl/mac_2stage.sv) and
[3-stage](../rtl/mac_3stage.sv) RTL boundaries:

- In 1-stage, the worst setup path goes from an operand port to the result
  register through the combined multiply-add stage.
- In 2-stage, it ends at `product_stage1`, before the separate addition stage.
  The multiplication stage is the limiting path in this selected implementation.
- In 3-stage, it starts at an input register and ends at `product_stage2`.
  Multiplication remains between a single pair of register boundaries; the
  extra input stage has not divided that arithmetic block.

The 2-stage report's
[register-to-register setup section](../results/fmax/mac_2stage/6_finish.rpt#L357)
lists `product_stage1[0]` to `y[28]` with **+2.45 ns** slack. That is distinct
from its global operand-to-product path with about **+0.0484 ns** slack.
The saved evidence does not identify the final addition stage as its limiter.

This locates the bottleneck; it does not isolate a numerical cause for every
frequency difference. The 2-stage path starts at an external input with a
0.5 ns input delay, whereas the 3-stage path starts at a flip-flop and includes
launch clock-tree and clock-to-Q timing. Their selected periods, mapped cells,
clock trees and routing also differ. Total arrival times are therefore not
pure multiplier delays and should not be subtracted to claim a causal speedup.

The defensible conclusion is that the third stage did not split the block
that is critical in its saved implementation. Its lower passing target is an
observation for this experiment. The reports do not establish that adding an
input register always reduces achievable frequency, or how much of the
observed difference is due to routing versus cell or clock effects.

## Worst slack, WNS and frequency estimates

The reports distinguish `report_worst_slack` from `report_wns`. All three
selected runs print **`wns max 0.00`** because they have no negative setup
slack. Their positive worst setup margins are the `ws` values in the table;
calling those positive values WNS obscures that distinction.

The historical JSON/CSV field name `wns_ns` is retained for compatibility.
For new runs, both collectors prefer `finish__timing__setup__ws`, then
`setup__worst_slack`, and use `setup__wns` only as a fallback. New tables and
plots label the quantity as worst setup slack. The saved historical report
files keep their original labels and values.

The raw `report_clock_min_period` sections also print frequency estimates of
**180.57 MHz** (1-stage), **180.84 MHz** (2-stage), **168.01 MHz** (3-stage).
These are estimates from each saved netlist, not extra passing sweep runs.
The project result table retains the tested targets **177.78, 179.27 and
167.10 MHz**, rather than replacing them with the single-run estimates.

The approximately 0.84% difference between the 1- and 2-stage tested targets
remains a run-specific result, alongside the area/latency cost. Repeated
physical runs would be needed to assess how stable that small difference is.
