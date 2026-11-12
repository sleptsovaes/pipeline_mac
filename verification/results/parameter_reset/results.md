# MAC signed-width and reset regression

Execution time (UTC): `2026-11-12T21:58:14.548380+00:00`.
Overall result: **PASS**.

Expected arithmetic uses signed Python integers, reduced modulo `2**ACC_W`.
Each run covers one pending operation, a full stalled pipeline with a blocked input,
flowing traffic and an empty repeated reset. Three resets cancel pending work;
one is held across clocks and three are short asynchronous pulses.
Fresh post-reset vectors run with randomized backpressure and stall-stability checks.

| DATA_W | ACC_W | Stages | Checked after reset | Cancelled | Reset scenarios |
|---|---|---:|---:|---:|---:|
| 1 | 1 | 1 | 262 | 3 | 4 |
| 1 | 1 | 2 | 262 | 5 | 4 |
| 1 | 1 | 3 | 262 | 7 | 4 |
| 2 | 3 | 1 | 284 | 3 | 4 |
| 2 | 3 | 2 | 284 | 5 | 4 |
| 2 | 3 | 3 | 284 | 7 | 4 |
| 4 | 4 | 1 | 293 | 3 | 4 |
| 4 | 4 | 2 | 293 | 5 | 4 |
| 4 | 4 | 3 | 293 | 7 | 4 |
| 4 | 8 | 1 | 293 | 3 | 4 |
| 4 | 8 | 2 | 293 | 5 | 4 |
| 4 | 8 | 3 | 293 | 7 | 4 |
| 4 | 12 | 1 | 293 | 3 | 4 |
| 4 | 12 | 2 | 293 | 5 | 4 |
| 4 | 12 | 3 | 293 | 7 | 4 |
| 8 | 16 | 1 | 293 | 3 | 4 |
| 8 | 16 | 2 | 293 | 5 | 4 |
| 8 | 16 | 3 | 293 | 7 | 4 |
| 8 | 24 | 1 | 293 | 3 | 4 |
| 8 | 24 | 2 | 293 | 5 | 4 |
| 8 | 24 | 3 | 293 | 7 | 4 |
| 16 | 16 | 1 | 293 | 3 | 4 |
| 16 | 16 | 2 | 293 | 5 | 4 |
| 16 | 16 | 3 | 293 | 7 | 4 |
| 16 | 32 | 1 | 293 | 3 | 4 |
| 16 | 32 | 2 | 293 | 5 | 4 |
| 16 | 32 | 3 | 293 | 7 | 4 |
| 16 | 40 | 1 | 293 | 3 | 4 |
| 16 | 40 | 2 | 293 | 5 | 4 |
| 16 | 40 | 3 | 293 | 7 | 4 |
| 33 | 66 | 1 | 293 | 3 | 4 |
| 33 | 66 | 2 | 293 | 5 | 4 |
| 33 | 66 | 3 | 293 | 7 | 4 |

Fault-detection checks:
- incorrect_sign_extension: rejected as expected.
- retained_pending_stage_on_reset: rejected as expected.

Source/vector SHA-256 hashes, tools and seed are recorded in `results.json`.
This finite simulation matrix is not an exhaustive parameter or formal proof.
It does not add physical timing or area measurements.
