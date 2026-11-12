#!/usr/bin/env python3
"""Check signed widths, backpressure and reset cancellation against Python integers."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WIDTHS = [(1, 1), (2, 3), (4, 4), (4, 8), (4, 12), (8, 16),
          (8, 24), (16, 16), (16, 32), (16, 40), (33, 66)]
BENCH = ROOT / "tb/tb_mac_parameter_reset.sv"


def signed(value, width):
    value &= (1 << width)-1
    return value-(1 << width) if value & (1 << (width-1)) else value


def oracle(a, b, c, data_w, acc_w):
    return (signed(a, data_w)*signed(b, data_w)+signed(c, acc_w)) & ((1 << acc_w)-1)


def write_vectors(path, data_w, acc_w, random_count, seed):
    data_edges = [0, 1, -1, -(1 << (data_w-1)), (1 << (data_w-1))-1]
    acc_edges = [0, 1, -1, -(1 << (acc_w-1)), (1 << (acc_w-1))-1]
    triples = [(a, b, 0) for a in data_edges for b in data_edges]
    triples += [(0, 0, c) for c in acc_edges]
    triples += [(a, b, c) for a, b in [(data_edges[-1], data_edges[-1]),
                                      (data_edges[-2], -1)] for c in acc_edges]
    data_mask, acc_mask = (1 << data_w)-1, (1 << acc_w)-1
    triples = list(dict.fromkeys((a & data_mask, b & data_mask, c & acc_mask)
                                for a, b, c in triples))
    rng = random.Random(seed + 1009*data_w + 9176*acc_w)
    triples += [(rng.getrandbits(data_w), rng.getrandbits(data_w), rng.getrandbits(acc_w))
                for _ in range(random_count)]
    digits = (2*data_w+2*acc_w+3)//4
    lines = []
    for a, b, c in triples:
        expected = oracle(a, b, c, data_w, acc_w)
        packed = (((a << data_w | b) << acc_w | c) << acc_w) | expected
        lines.append(f"{packed:0{digits}x}")
    path.write_text("\n".join(lines)+"\n")
    return len(triples)


def tool_version(command):
    run = subprocess.run(command + ["-V"], text=True, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, timeout=10, check=True)
    return run.stdout.splitlines()[0]


def simulate(directory, rtl, stages, data_w, acc_w, vectors, count, seed, compiler, runtime):
    directory.mkdir(parents=True, exist_ok=True)
    executable = directory / "simulation.vvp"
    command = compiler + ["-g2012", "-s", "tb_mac_parameter_reset", f"-DDUT=mac_{stages}stage",
                          f"-Ptb_mac_parameter_reset.DATA_W={data_w}",
                          f"-Ptb_mac_parameter_reset.ACC_W={acc_w}",
                          f"-Ptb_mac_parameter_reset.STAGES={stages}",
                          f"-Ptb_mac_parameter_reset.N_VECTORS={count}",
                          "-o", str(executable), str(rtl), str(BENCH)]
    build = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=30)
    (directory / "compile.log").write_text(build.stdout)
    if build.returncode:
        raise RuntimeError(f"Compilation failed; inspect {directory / 'compile.log'}\n{build.stdout}")
    run = subprocess.run(runtime + [str(executable), f"+VECTORS={vectors}", f"+SEED={seed}"],
                         text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    (directory / "simulation.log").write_text(run.stdout)
    return run


def write_report(out, report):
    (out / "results.json").write_text(json.dumps(report, indent=2)+"\n")
    lines = ["# MAC signed-width and reset regression", "",
             f"Execution time (UTC): `{report['executed_at_utc']}`.",
             f"Overall result: **{'PASS' if report['passed'] else 'INCOMPLETE / FAIL'}**.", "",
             "Expected arithmetic uses signed Python integers, reduced modulo `2**ACC_W`.",
             "Each run covers one pending operation, a full stalled pipeline with a blocked input,",
             "flowing traffic and an empty repeated reset. Three resets cancel pending work;",
             "one is held across clocks and three are short asynchronous pulses.",
             "Fresh post-reset vectors run with randomized backpressure and stall-stability checks.", "",
             "| DATA_W | ACC_W | Stages | Checked after reset | Cancelled | Reset scenarios |",
             "|---|---|---:|---:|---:|---:|"]
    for row in report["runs"]:
        lines.append(f"| {row['data_w']} | {row['acc_w']} | {row['stages']} | "
                     f"{row['checked']} | {row['cancelled']} | {row['resets']} |")
    lines += ["", "Fault-detection checks:"]
    for fault in report["fault_checks"]:
        lines.append(f"- {fault}: rejected as expected.")
    lines += ["", "Source/vector SHA-256 hashes, tools and seed are recorded in `results.json`.",
              "This finite simulation matrix is not an exhaustive parameter or formal proof.",
              "It does not add physical timing or area measurements."]
    (out / "results.md").write_text("\n".join(lines)+"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/parameter_reset")
    parser.add_argument("--random-vectors", type=int, default=256)
    parser.add_argument("--seed", type=int, default=12345)
    args = parser.parse_args()
    if args.random_vectors < 0:
        parser.error("--random-vectors must be nonnegative")
    # Small, hand-calculated independent goldens guard the vector oracle.
    assert oracle(-1, 1, 0, 8, 24) == 0xffffff
    assert oracle(-128, -128, 0, 8, 8) == 0
    assert oracle(127, 127, 127, 8, 8) == 0x80
    assert oracle(-2, 3, -1, 4, 12) == 0xff9
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    compiler = shlex.split(os.environ.get("IVERILOG", "iverilog"))
    runtime = shlex.split(os.environ.get("VVP", "vvp"))
    sources = [BENCH, Path(__file__).resolve(), *sorted((ROOT / "rtl").glob("mac_[123]stage.sv"))]
    report = {"executed_at_utc": datetime.now(timezone.utc).isoformat(), "passed": False,
              "seed": args.seed, "random_vectors_per_width": args.random_vectors,
              "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sources},
              "tools": {"iverilog": tool_version(compiler), "vvp": tool_version(runtime)},
              "runs": [], "fault_checks": []}
    vectors_by_width = {}
    try:
        for data_w, acc_w in WIDTHS:
            vectors = out / f"vectors_d{data_w}_a{acc_w}.hex"
            count = write_vectors(vectors, data_w, acc_w, args.random_vectors, args.seed)
            vectors_by_width[data_w, acc_w] = vectors, count
            for stages in (1, 2, 3):
                directory = out / f"mac_{stages}stage_d{data_w}_a{acc_w}"
                run = simulate(directory, ROOT / f"rtl/mac_{stages}stage.sv", stages,
                               data_w, acc_w, vectors, count, args.seed, compiler, runtime)
                match = re.search(r"PARAM_RESET_PASS data=(\d+) acc=(\d+) stages=(\d+) "
                                  r"checked=(\d+) cancelled=(\d+) resets=(\d+)", run.stdout)
                wanted = (data_w, acc_w, stages, count, 1+2*stages, 4)
                if run.returncode or not match or tuple(map(int, match.groups())) != wanted:
                    raise RuntimeError(f"RTL check failed; inspect {directory / 'simulation.log'}\n{run.stdout}")
                report["runs"].append(dict(zip(["data_w", "acc_w", "stages", "checked", "cancelled", "resets"], wanted),
                                           vectors_sha256=hashlib.sha256(vectors.read_bytes()).hexdigest()))
                print(f"PASS mac_{stages}stage {data_w}/{acc_w}: {count} vectors, 4 reset scenarios", flush=True)

        original = (ROOT / "rtl/mac_2stage.sv").read_text()
        faults = [
            ("incorrect_sign_extension", 8, 24,
             original.replace("{(ACC_W-PROD_W){product_stage1[PROD_W-1]}}",
                              "{(ACC_W-PROD_W){1'b0}}"), "Arithmetic mismatch"),
            ("retained_pending_stage_on_reset", 16, 32,
             re.sub(r"stage1_valid\s*<=\s*1'b0;",
                    "stage1_valid <= (stage1_valid === 1'b1);", original, count=1),
             "Stale transaction appeared after reset"),
        ]
        for name, data_w, acc_w, mutated, message in faults:
            if mutated == original:
                raise RuntimeError(f"Fault injection did not modify RTL: {name}")
            directory = out / name
            directory.mkdir(exist_ok=True)
            rtl = directory / "mac_2stage.sv"
            rtl.write_text(mutated)
            vectors, count = vectors_by_width[data_w, acc_w]
            run = simulate(directory, rtl, 2, data_w, acc_w, vectors, count, args.seed, compiler, runtime)
            if run.returncode == 0 or message not in run.stdout:
                raise RuntimeError(f"Fault check did not detect {name}:\n{run.stdout}")
            report["fault_checks"].append(name)
            print(f"PASS fault detection: {name}", flush=True)
        report["passed"] = True
    finally:
        write_report(out, report)
    print(f"PARAMETER/RESET MATRIX PASSED: {len(report['runs'])} RTL runs, 2 fault checks")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"PARAMETER/RESET REGRESSION FAILED: {error}", file=sys.stderr)
        sys.exit(1)
