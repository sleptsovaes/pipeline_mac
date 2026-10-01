#!/usr/bin/env python3

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

LOG_ROOT = ROOT / "physical" / "work" / "logs" / "sky130hd"
RESULT_ROOT = ROOT / "physical" / "work" / "results" / "sky130hd"

DESIGNS = {
    "mac_1stage": {
        "label": "1-stage",
        "latency": 1,
    },
    "mac_2stage": {
        "label": "2-stage",
        "latency": 2,
    },
    "mac_3stage": {
        "label": "3-stage",
        "latency": 3,
    },
}


def read_text(path):
    if not path.exists():
        return ""
    return path.read_text(errors="ignore")


def load_json(path):
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def first_number(text, patterns):
    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE | re.MULTILINE
        )

        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass

    return None


def find_json_value(data, exact_keys=None, contains=None):
    exact_keys = exact_keys or []
    contains = contains or []

    for key in exact_keys:
        if key in data:
            return data[key]

    for key, value in data.items():
        key_lower = key.lower()

        if all(term.lower() in key_lower for term in contains):
            if isinstance(value, (int, float)):
                return value

    return None


def collect_design(design, info):

    log_dir = LOG_ROOT / design / "base"
    result_dir = RESULT_ROOT / design / "base"

    report_log = read_text(log_dir / "6_report.log")
    report_json = load_json(log_dir / "6_report.json")
    grt_log = read_text(log_dir / "5_1_grt.log")

    clock_file = result_dir / "clock_period.txt"

    clock_period = None

    if clock_file.exists():
        try:
            clock_period = float(clock_file.read_text().strip())
        except ValueError:
            pass


    power_w = first_number(
        report_log,
        [
            r"Total power\s*:\s*([0-9.eE+-]+)\s*W"
        ]
    )


    area_um2 = first_number(
        report_log,
        [
            r"Design area\s+([0-9.eE+-]+)\s+um\^2"
        ]
    )


    utilization_pct = first_number(
        report_log,
        [
            r"Design area\s+[0-9.eE+-]+\s+um\^2\s+([0-9.eE+-]+)%\s+utilization"
        ]
    )


    sequential_cells = first_number(
        report_log,
        [
            r"Sequential cell\s+([0-9]+)"
        ]
    )


    combinational_cells = first_number(
        report_log,
        [
            r"Multi-Input combinational cell\s+([0-9]+)"
        ]
    )


    sequential_area = first_number(
        report_log,
        [
            r"Sequential cell\s+[0-9]+\s+([0-9.eE+-]+)"
        ]
    )


    combinational_area = first_number(
        report_log,
        [
            r"Multi-Input combinational cell\s+[0-9]+\s+([0-9.eE+-]+)"
        ]
    )


    tns = find_json_value(
        report_json,
        exact_keys=[
            "finish__timing__setup__tns"
        ],
        contains=[
            "finish",
            "timing",
            "setup",
            "tns"
        ]
    )


    wns = find_json_value(
        report_json,
        exact_keys=[
            "finish__timing__setup__wns",
            "finish__timing__setup__ws",
            "finish__timing__setup__worst_slack"
        ],
        contains=[
            "finish",
            "timing",
            "setup",
            "wns"
        ]
    )


    if wns is None:
        for terms in [
            ["finish", "timing", "setup", "worst"],
            ["finish", "timing", "setup", "slack"],
            ["finish", "timing", "setup", "ws"],
        ]:

            wns = find_json_value(
                report_json,
                contains=terms
            )

            if wns is not None:
                break


    routed_slack = first_number(
        grt_log,
        [
            r"Clock\s+\S+\s+slack\s+([+-]?[0-9.]+)"
        ]
    )


    fmax_est_mhz = None

    if clock_period is not None and routed_slack is not None:

        critical_delay = clock_period - routed_slack

        if critical_delay > 0:
            fmax_est_mhz = 1000.0 / critical_delay


    return {
        "design": design,
        "variant": info["label"],
        "latency_cycles": info["latency"],

        "clock_period_ns": clock_period,

        "wns_ns": wns,
        "routed_slack_ns": routed_slack,
        "tns_ns": tns,

        "area_um2": area_um2,
        "utilization_pct": utilization_pct,

        "sequential_cells": sequential_cells,
        "combinational_cells": combinational_cells,

        "sequential_area_um2": sequential_area,
        "combinational_area_um2": combinational_area,

        "power_w": power_w,

        "estimated_fmax_mhz": fmax_est_mhz,
    }


def fmt(value, digits=3):

    if value is None:
        return "N/A"

    if isinstance(value, int):
        return str(value)

    if isinstance(value, float):
        return f"{value:.{digits}f}"

    return str(value)


def write_csv(rows, path):

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="") as f:

        writer = csv.DictWriter(
            f,
            fieldnames=rows[0].keys()
        )

        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows, path):

    path.parent.mkdir(parents=True, exist_ok=True)

    lines = []

    lines.append("# PPA Comparison")
    lines.append("")
    lines.append(
        "| Variant | Latency | Period (ns) | WNS (ns) | "
        "Route slack (ns) | TNS (ns) | Area (um²) | "
        "Util. (%) | Seq cells | Comb cells | Power (mW) | "
        "Est. Fmax (MHz) |"
    )

    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )

    for r in rows:

        power_mw = (
            r["power_w"] * 1000
            if r["power_w"] is not None
            else None
        )

        lines.append(
            f"| {r['variant']} "
            f"| {r['latency_cycles']} "
            f"| {fmt(r['clock_period_ns'])} "
            f"| {fmt(r['wns_ns'])} "
            f"| {fmt(r['routed_slack_ns'])} "
            f"| {fmt(r['tns_ns'])} "
            f"| {fmt(r['area_um2'], 1)} "
            f"| {fmt(r['utilization_pct'], 1)} "
            f"| {fmt(r['sequential_cells'], 0)} "
            f"| {fmt(r['combinational_cells'], 0)} "
            f"| {fmt(power_mw, 2)} "
            f"| {fmt(r['estimated_fmax_mhz'], 1)} |"
        )

    path.write_text("\n".join(lines) + "\n")


def print_table(rows):

    print()
    print("=" * 104)
    print("PPA COMPARISON")
    print("=" * 104)

    header = (
        f"{'Variant':<12}"
        f"{'Period':>10}"
        f"{'WNS':>10}"
        f"{'Route':>10}"
        f"{'TNS':>10}"
        f"{'Area':>12}"
        f"{'Util':>10}"
        f"{'Seq':>8}"
        f"{'Comb':>8}"
        f"{'Power':>12}"
    )

    print(header)
    print("-" * 104)

    for r in rows:

        power_mw = (
            r["power_w"] * 1000
            if r["power_w"] is not None
            else None
        )

        print(
            f"{r['variant']:<12}"
            f"{fmt(r['clock_period_ns']):>10}"
            f"{fmt(r['wns_ns']):>10}"
            f"{fmt(r['routed_slack_ns']):>10}"
            f"{fmt(r['tns_ns']):>10}"
            f"{fmt(r['area_um2'], 1):>12}"
            f"{fmt(r['utilization_pct'], 1):>10}"
            f"{fmt(r['sequential_cells'], 0):>8}"
            f"{fmt(r['combinational_cells'], 0):>8}"
            f"{fmt(power_mw, 2):>12}"
        )

    print("=" * 104)
    print()


def main():

    rows = []

    for design, info in DESIGNS.items():

        row = collect_design(
            design,
            info
        )

        rows.append(row)

    print_table(rows)

    output_dir = ROOT / "results" / "ppa"

    csv_path = output_dir / "ppa_summary.csv"
    md_path = output_dir / "ppa_summary.md"

    write_csv(
        rows,
        csv_path
    )

    write_markdown(
        rows,
        md_path
    )

    print(f"CSV      : {csv_path}")
    print(f"Markdown : {md_path}")
    print()

    print("Timing-related keys found in final JSON reports:")
    print()

    for design in DESIGNS:

        json_path = (
            LOG_ROOT
            / design
            / "base"
            / "6_report.json"
        )

        data = load_json(json_path)

        print(f"[{design}]")

        for key, value in data.items():

            low = key.lower()

            if (
                "timing" in low
                or "slack" in low
                or "wns" in low
                or "tns" in low
            ):
                print(f"  {key}: {value}")

        print()


if __name__ == "__main__":
    main()
