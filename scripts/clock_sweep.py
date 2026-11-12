#!/usr/bin/env python3

import argparse
import csv
from datetime import datetime, timezone
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path


from physical_environment import input_hashes, provenance, selected_environment, write_manifest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "build" / "clock_sweep"
SWEEP_WORK = OUTPUT_DIR / "work"

RESULT_DIR = SWEEP_WORK / "results"
REPORT_DIR = SWEEP_WORK / "reports"
LOG_DIR = SWEEP_WORK / "logs"
OBJECT_DIR = SWEEP_WORK / "objects"

FMAX_DIR = OUTPUT_DIR / "best"

SDC_PATH = (
    ROOT
    / "physical"
    / "constraints"
    / "mac_sweep.sdc"
)


DESIGNS = {
    "mac_1stage": {
        "label": "1-stage",
        "latency": 1,
        "config": "mac_1stage_sweep.mk",
    },

    "mac_2stage": {
        "label": "2-stage",
        "latency": 2,
        "config": "mac_2stage_sweep.mk",
    },

    "mac_3stage": {
        "label": "3-stage",
        "latency": 3,
        "config": "mac_3stage_sweep.mk",
    },
}


COARSE_PERIODS = [
    7.00,
    6.50,
    6.00,
    5.75,
    5.50,
    5.25,
    5.00,
]


def ensure_dirs():

    for path in [
        RESULT_DIR,
        REPORT_DIR,
        LOG_DIR,
        OBJECT_DIR,
        OUTPUT_DIR,
        FMAX_DIR,
    ]:
        path.mkdir(
            parents=True,
            exist_ok=True
        )


def sdc_text(period):

    text = f"""set clk_name core_clock
set clk_period {period:.4f}

create_clock \\
    -name $clk_name \\
    -period $clk_period \\
    [get_ports clk]

set_input_delay \\
    0.5 \\
    -clock [get_clocks $clk_name] \\
    [get_ports in_valid]

set_input_delay \\
    0.5 \\
    -clock [get_clocks $clk_name] \\
    [get_ports out_ready]

set_input_delay \\
    0.5 \\
    -clock [get_clocks $clk_name] \\
    [get_ports a*]

set_input_delay \\
    0.5 \\
    -clock [get_clocks $clk_name] \\
    [get_ports b*]

set_input_delay \\
    0.5 \\
    -clock [get_clocks $clk_name] \\
    [get_ports c*]

set_output_delay \\
    0.5 \\
    -clock [get_clocks $clk_name] \\
    [get_ports in_ready]

set_output_delay \\
    0.5 \\
    -clock [get_clocks $clk_name] \\
    [get_ports out_valid]

set_output_delay \\
    0.5 \\
    -clock [get_clocks $clk_name] \\
    [get_ports y*]

set_false_path \\
    -from [get_ports rst_n]
"""

    return text


def write_sdc(period):
    SDC_PATH.write_text(sdc_text(period))


def configure_output(path):
    global OUTPUT_DIR, FMAX_DIR, SWEEP_WORK, RESULT_DIR, REPORT_DIR, LOG_DIR, OBJECT_DIR
    OUTPUT_DIR = Path(path).resolve()
    FMAX_DIR = OUTPUT_DIR / "best"
    SWEEP_WORK = OUTPUT_DIR / "work"
    RESULT_DIR = SWEEP_WORK / "results"
    REPORT_DIR = SWEEP_WORK / "reports"
    LOG_DIR = SWEEP_WORK / "logs"
    OBJECT_DIR = SWEEP_WORK / "objects"


def point_provenance(design, period):
    return provenance(design, period, sdc_text(period), selected_environment(ROOT), ROOT)


def reusable_record(row, design, period):
    if not isinstance(row, dict) or row.get("design") != design or row.get("period_ns") != period:
        return False
    wns = row.get("wns_ns")
    if (row.get("flow_completed") is not True or isinstance(wns, bool)
            or not isinstance(wns, (int, float)) or not math.isfinite(wns)
            or row.get("timing_met") is not (wns >= 0)):
        return False
    return row.get("provenance") == point_provenance(design, period)


def docker_command(design, environment=None):

    config = DESIGNS[design]["config"]
    environment = environment or selected_environment(ROOT)

    return [
        "docker",
        "run",
        "--rm",
        "--platform",
        environment["platform"],

        "-v",
        f"{ROOT}:/work/pipelined-mac",

        "-v",
        f"{RESULT_DIR}:/OpenROAD-flow-scripts/flow/results",

        "-v",
        f"{REPORT_DIR}:/OpenROAD-flow-scripts/flow/reports",

        "-v",
        f"{LOG_DIR}:/OpenROAD-flow-scripts/flow/logs",

        "-v",
        f"{OBJECT_DIR}:/OpenROAD-flow-scripts/flow/objects",

        "-e",
        "MAC_REPO=/work/pipelined-mac",

        environment["image"],

        "bash",
        "-lc",

        f"""
set -e

cd /OpenROAD-flow-scripts/flow

git -C /OpenROAD-flow-scripts rev-parse HEAD || echo 'ORFS Git metadata unavailable in this pinned image'
/usr/local/bin/yosys -V
/OpenROAD-flow-scripts/tools/install/OpenROAD/bin/openroad -version

env -u MAKEFLAGS make -j1 \\
    DESIGN_CONFIG=/work/pipelined-mac/physical/orfs/{config} \\
    YOSYS_EXE=/usr/local/bin/yosys \\
    OPENROAD_EXE=/OpenROAD-flow-scripts/tools/install/OpenROAD/bin/openroad \\
    clean_all

env -u MAKEFLAGS make -j1 \\
    DESIGN_CONFIG=/work/pipelined-mac/physical/orfs/{config} \\
    YOSYS_EXE=/usr/local/bin/yosys \\
    OPENROAD_EXE=/OpenROAD-flow-scripts/tools/install/OpenROAD/bin/openroad
"""
    ]


def load_json(path):

    try:
        return json.loads(
            path.read_text()
        )

    except Exception:
        return {}


def read_text(path):

    if not path.exists():
        return ""

    return path.read_text(
        errors="ignore"
    )


def regex_number(text, pattern):

    match = re.search(
        pattern,
        text,
        re.I | re.M
    )

    if not match:
        return None

    try:
        return float(
            match.group(1)
        )

    except ValueError:
        return None


def json_metric(data, keys):

    for key in keys:

        if key in data:
            value = data[key]

            if isinstance(
                value,
                (int, float)
            ):
                return float(value)

    return None


def parse_metrics(design, period):

    base_log = (
        LOG_DIR
        / "sky130hd"
        / design
        / "base"
    )

    base_result = (
        RESULT_DIR
        / "sky130hd"
        / design
        / "base"
    )

    report_json = load_json(
        base_log
        / "6_report.json"
    )

    report_log = read_text(
        base_log
        / "6_report.log"
    )

    route_log = read_text(
        base_log
        / "5_1_grt.log"
    )


    wns = json_metric(
        report_json,
        [
            "finish__timing__setup__ws",
            "finish__timing__setup__worst_slack",
            "finish__timing__setup__wns",
        ]
    )


    if wns is None:

        for key, value in report_json.items():

            key_lower = key.lower()

            if (
                "finish" in key_lower
                and "timing" in key_lower
                and "setup" in key_lower
                and (
                    "wns" in key_lower
                    or "worst" in key_lower
                    or "slack" in key_lower
                )
            ):
                if isinstance(
                    value,
                    (int, float)
                ):
                    wns = float(value)
                    break


    tns = json_metric(
        report_json,
        [
            "finish__timing__setup__tns"
        ]
    )


    route_slack = regex_number(
        route_log,
        r"Clock\s+\S+\s+slack\s+([+-]?[0-9.]+)"
    )


    area = regex_number(
        report_log,
        r"Design area\s+([0-9.eE+-]+)\s+um\^2"
    )


    utilization = regex_number(
        report_log,
        r"Design area\s+[0-9.eE+-]+\s+um\^2\s+([0-9.eE+-]+)%\s+utilization"
    )


    power = regex_number(
        report_log,
        r"Total power\s*:\s*([0-9.eE+-]+)\s*W"
    )


    sequential_cells = regex_number(
        report_log,
        r"Sequential cell\s+([0-9]+)"
    )


    combinational_cells = regex_number(
        report_log,
        r"Multi-Input combinational cell\s+([0-9]+)"
    )


    frequency_mhz = (
        1000.0 / period
    )


    timing_met = (
        wns is not None
        and wns >= 0.0
    )


    final_gds = (
        base_result
        / "6_final.gds"
    )

    completed = (
        final_gds.exists()
    )


    return {
        "design": design,
        "variant": DESIGNS[design]["label"],

        "latency_cycles":
            DESIGNS[design]["latency"],

        "period_ns": period,
        "frequency_mhz": frequency_mhz,

        "wns_ns": wns,
        "route_slack_ns": route_slack,
        "tns_ns": tns,

        "area_um2": area,
        "utilization_pct": utilization,

        "sequential_cells":
            sequential_cells,

        "combinational_cells":
            combinational_cells,

        "power_w": power,

        "flow_completed":
            completed,

        "timing_met":
            timing_met,
    }


def snapshot_best(design, row):

    destination = (
        FMAX_DIR
        / design
    )

    if destination.exists():
        shutil.rmtree(
            destination
        )

    destination.mkdir(
        parents=True,
        exist_ok=True
    )


    result_source = (
        RESULT_DIR
        / "sky130hd"
        / design
        / "base"
    )


    report_source = (
        REPORT_DIR
        / "sky130hd"
        / design
        / "base"
    )


    log_source = (
        LOG_DIR
        / "sky130hd"
        / design
        / "base"
    )


    for filename in [
        "6_final.gds",
        "6_final.def",
        "6_final.odb",
        "6_final.sdc",
        "6_final.spef",
        "6_final.v",
        "6_final_lec.v",
    ]:

        src = (
            result_source
            / filename
        )

        if src.exists():

            shutil.copy2(
                src,
                destination
                / filename
            )


    for filename in [
        "6_finish.rpt",
        "final_all.webp.png",
        "final_routing.webp.png",
        "final_placement.webp.png",
        "final_worst_path.webp.png",
    ]:

        src = (
            report_source
            / filename
        )

        if src.exists():

            shutil.copy2(
                src,
                destination
                / filename
            )


    for filename in [
        "6_report.log",
        "6_report.json",
        "5_1_grt.log",
    ]:

        src = (
            log_source
            / filename
        )

        if src.exists():

            shutil.copy2(
                src,
                destination
                / filename
            )


    (
        destination
        / "best_run.json"
    ).write_text(
        json.dumps(
            row,
            indent=2
        )
    )


def run_point(
    design,
    period,
    force=False
):

    period = round(period, 4)
    if design not in DESIGNS or not math.isfinite(period) or period <= 0:
        raise ValueError("Unknown design or invalid clock period")
    expected_provenance = point_provenance(design, period)
    result_json = OUTPUT_DIR / design / f"{period:.4f}ns.json"
    result_json.parent.mkdir(parents=True, exist_ok=True)
    if result_json.exists() and not force:
        cached = load_json(result_json)
        if reusable_record(cached, design, period):
            print(f"[CACHE] {design} {period:.4f} ns: verified inputs")
            return cached
        print(f"[STALE] {design} {period:.4f} ns: recomputing")


    print()
    print("=" * 70)

    print(
        f"{design}: "
        f"{period:.4f} ns "
        f"({1000.0 / period:.2f} MHz)"
    )

    print("=" * 70)


    write_sdc(
        period
    )


    command = docker_command(design, expected_provenance["inputs"]["environment"])
    flow_log = result_json.with_suffix(".flow.log")
    with flow_log.open("w") as stream:
        process = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
    if point_provenance(design, period) != expected_provenance:
        raise RuntimeError("Physical inputs changed during the run; result not cached")
    if process.returncode:
        print(f"Physical flow failed; inspect {flow_log}", file=sys.stderr)


    if process.returncode != 0:

        row = {
            "design": design,

            "variant":
                DESIGNS[design]["label"],

            "latency_cycles":
                DESIGNS[design]["latency"],

            "period_ns": period,

            "frequency_mhz":
                1000.0 / period,

            "flow_completed":
                False,

            "timing_met":
                False,

            "wns_ns": None,
            "route_slack_ns": None,
            "tns_ns": None,
            "area_um2": None,
            "utilization_pct": None,
            "sequential_cells": None,
            "combinational_cells": None,
            "power_w": None,
        }

    else:

        row = parse_metrics(
            design,
            period
        )


    row["provenance"] = expected_provenance
    row["executed_at_utc"] = datetime.now(timezone.utc).isoformat()
    row["flow_log"] = str(flow_log.relative_to(OUTPUT_DIR))
    result_json.write_text(
        json.dumps(
            row,
            indent=2
        )
    )


    status = (
        "PASS"
        if row["timing_met"]
        else "FAIL"
    )


    print()
    print(
        f"{design} @ "
        f"{1000.0 / period:.2f} MHz"
    )

    print(
        f"Setup slack: "
        f"{row['wns_ns']}"
    )

    print(
        f"TNS    : "
        f"{row['tns_ns']}"
    )

    print(
        f"Timing : "
        f"{status}"
    )


    return row


def coarse_sweep(
    force=False
):

    rows = []


    for design in DESIGNS:

        for period in COARSE_PERIODS:

            row = run_point(
                design,
                period,
                force
            )

            if not row.get("flow_completed") or row.get("wns_ns") is None:
                raise RuntimeError(f"Incomplete physical run: {design} at {period:.4f} ns")
            rows.append(
                row
            )


    return rows


def find_bracket(
    rows,
    design
):

    design_rows = [
        r
        for r in rows
        if r["design"] == design
        and r.get("flow_completed")
    ]


    design_rows.sort(
        key=lambda x:
            x["period_ns"]
    )


    passes = [
        r
        for r in design_rows
        if r.get("timing_met")
    ]


    fails = [
        r
        for r in design_rows
        if not r.get("timing_met")
    ]


    if not passes:
        return None


    best_pass = min(
        passes,
        key=lambda x:
            x["period_ns"]
    )


    faster_fails = [
        r
        for r in fails
        if r["period_ns"]
        < best_pass["period_ns"]
    ]


    if not faster_fails:

        return None


    nearest_fail = max(
        faster_fails,
        key=lambda x:
            x["period_ns"]
    )


    return (
        nearest_fail[
            "period_ns"
        ],
        best_pass[
            "period_ns"
        ],
    )


def refine_design(
    design,
    rows,
    iterations=4,
    force=False
):

    bracket = find_bracket(
        rows,
        design
    )


    if bracket is None:

        print(
            f"No valid PASS/FAIL "
            f"bracket for {design}"
        )

        return []


    fail_period, pass_period = (
        bracket
    )


    extra_rows = []


    print()
    print(
        f"Refining {design}: "
        f"FAIL={fail_period:.4f} ns, "
        f"PASS={pass_period:.4f} ns"
    )


    for _ in range(iterations):

        middle = (
            fail_period
            + pass_period
        ) / 2.0


        middle = round(
            middle,
            4
        )


        row = run_point(
            design,
            middle,
            force
        )


        extra_rows.append(
            row
        )

        if not row.get("flow_completed") or row.get("wns_ns") is None:
            raise RuntimeError(f"Cannot refine from an incomplete physical run at {middle:.4f} ns")

        if row.get("timing_met"):

            pass_period = middle

        else:

            fail_period = middle


    return extra_rows


def all_saved_rows():
    rows = []
    for design in DESIGNS:
        for path in (OUTPUT_DIR / design).glob("*ns.json"):
            try:
                period = float(path.name.removesuffix("ns.json"))
            except ValueError:
                continue
            row = load_json(path)
            if math.isfinite(period) and period > 0 and reusable_record(row, design, period):
                rows.append(row)
    return rows


def save_summary(rows):

    rows = [
        r
        for r in rows
        if r.get("period_ns")
        is not None
    ]


    rows.sort(
        key=lambda r: (
            r["design"],
            -r["period_ns"]
        )
    )


    csv_path = (
        OUTPUT_DIR
        / "clock_sweep.csv"
    )


    fields = [
        "design",
        "variant",
        "latency_cycles",
        "period_ns",
        "frequency_mhz",
        "wns_ns",
        "route_slack_ns",
        "tns_ns",
        "area_um2",
        "utilization_pct",
        "sequential_cells",
        "combinational_cells",
        "power_w",
        "flow_completed",
        "timing_met",
    ]


    with csv_path.open(
        "w",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields
        )

        writer.writeheader()


        for row in rows:

            writer.writerow({
                field:
                    row.get(field)
                for field in fields
            })


    markdown_path = (
        OUTPUT_DIR
        / "clock_sweep.md"
    )


    lines = [
        "# Clock Sweep",
        "",
        "| Variant | Period (ns) | Frequency (MHz) | Worst setup slack (ns) | TNS (ns) | Area (um²) | Power (mW) | Timing |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]


    for row in rows:

        power_mw = (
            row["power_w"] * 1000
            if row.get("power_w")
            is not None
            else None
        )


        def fmt(
            value,
            digits=3
        ):

            if value is None:
                return "N/A"

            return (
                f"{value:.{digits}f}"
            )


        lines.append(
            f"| {row['variant']} "
            f"| {fmt(row['period_ns'])} "
            f"| {fmt(row['frequency_mhz'], 1)} "
            f"| {fmt(row.get('wns_ns'))} "
            f"| {fmt(row.get('tns_ns'))} "
            f"| {fmt(row.get('area_um2'), 1)} "
            f"| {fmt(power_mw, 2)} "
            f"| {'PASS' if row.get('timing_met') else 'FAIL'} |"
        )


    markdown_path.write_text(
        "\n".join(lines)
        + "\n"
    )


    return (
        csv_path,
        markdown_path
    )


def select_best(rows):

    best = {}


    for design in DESIGNS:

        passes = [
            r
            for r in rows
            if (
                r["design"] == design
                and r.get("timing_met")
            )
        ]


        if not passes:
            continue


        winner = min(
            passes,
            key=lambda r:
                r["period_ns"]
        )


        best[design] = winner


    return best


def write_fmax_summary(best):

    path = (
        OUTPUT_DIR
        / "fmax_summary.md"
    )


    lines = [
        "# Fmax Summary",
        "",
        "| Variant | Best period (ns) | Fmax (MHz) | Worst setup slack (ns) | Area (um²) | Latency |",
        "|---|---:|---:|---:|---:|---:|",
    ]


    for design in DESIGNS:

        if design not in best:
            continue


        row = best[
            design
        ]


        lines.append(
            f"| {row['variant']} "
            f"| {row['period_ns']:.4f} "
            f"| {row['frequency_mhz']:.2f} "
            f"| {row['wns_ns']:.4f} "
            f"| {row['area_um2']:.1f} "
            f"| {row['latency_cycles']} |"
        )


    path.write_text(
        "\n".join(lines)
        + "\n"
    )


    return path


def main():

    parser = argparse.ArgumentParser()


    parser.add_argument(
        "--force",
        action="store_true"
    )


    parser.add_argument(
        "--refine",
        type=int,
        default=4
    )


    parser.add_argument("--output", type=Path, default=OUTPUT_DIR,
                        help="New results/cache/work/snapshots directory (default: build/clock_sweep)")
    parser.add_argument("--check-inputs", action="store_true",
                        help="Validate the image pin and list input hashes without running Docker")
    args = parser.parse_args()
    if args.refine < 0:
        parser.error("--refine must be nonnegative")
    configure_output(args.output)
    environment = selected_environment(ROOT)
    if args.check_inputs:
        print(json.dumps({"environment": environment, "files_sha256": input_hashes(ROOT),
                          "output": str(OUTPUT_DIR)}, indent=2))
        return
    if not shutil.which("docker"):
        parser.error("Docker is required for physical runs; --check-inputs works without it")
    ensure_dirs()
    write_manifest(OUTPUT_DIR / "run_manifest.json", ROOT)


    print()
    print(
        "================================"
    )

    print(
        " Pipelined MAC Clock Sweep"
    )

    print(
        "================================"
    )


    coarse_rows = coarse_sweep(
        force=args.force
    )


    for design in DESIGNS:

        refine_design(
            design,
            coarse_rows,
            iterations=args.refine,
            force=args.force
        )


    rows = all_saved_rows()


    best = select_best(
        rows
    )


    for design, row in list(best.items()):
        refreshed = run_point(design, row["period_ns"], force=True)
        if reusable_record(refreshed, design, row["period_ns"]) and refreshed["timing_met"]:
            snapshot_best(design, refreshed)
            best[design] = refreshed
        else:
            best.pop(design)
            shutil.rmtree(FMAX_DIR / design, ignore_errors=True)

    # Include final confirmation runs rather than the pre-confirmation metrics.
    csv_path, markdown_path = save_summary(all_saved_rows())

    fmax_summary = (
        write_fmax_summary(
            best
        )
    )


    print()

    print(
        " FINAL TIMING-CLOSED RESULTS"
    )


    for design in DESIGNS:

        if design not in best:

            print(
                f"{design}: "
                f"NO PASSING RUN"
            )

            continue


        row = best[
            design
        ]


        print(
            f"{row['variant']:<8} "
            f"{row['period_ns']:.4f} ns  "
            f"{row['frequency_mhz']:.2f} MHz  "
            f"setup_slack={row['wns_ns']:.4f} ns"
        )


    print()
    print(
        f"CSV      : {csv_path}"
    )

    print(
        f"Markdown : {markdown_path}"
    )

    print(
        f"Fmax     : {fmax_summary}"
    )

    print(
        f"Artifacts: {FMAX_DIR}"
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Clock sweep failed: {error}", file=sys.stderr)
        sys.exit(1)
