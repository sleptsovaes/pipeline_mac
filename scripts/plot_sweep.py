#!/usr/bin/env python3

import csv
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path.home() / "pipelined-mac"

CSV = (
    ROOT
    / "results"
    / "clock_sweep"
    / "clock_sweep.csv"
)

OUT = (
    ROOT
    / "results"
    / "clock_sweep"
)

OUT.mkdir(
    parents=True,
    exist_ok=True
)


rows = []

with CSV.open() as f:

    reader = csv.DictReader(f)

    for row in reader:

        if (
            not row["frequency_mhz"]
            or not row["wns_ns"]
        ):
            continue

        rows.append({
            "variant":
                row["variant"],

            "frequency":
                float(
                    row["frequency_mhz"]
                ),

            "wns":
                float(
                    row["wns_ns"]
                ),

            "area":
                float(
                    row["area_um2"]
                )
                if row["area_um2"]
                else None,

            "timing_met":
                row["timing_met"]
                == "True",
        })


variants = [
    "1-stage",
    "2-stage",
    "3-stage",
]


plt.figure(
    figsize=(8, 5)
)

for variant in variants:

    data = sorted(
        [
            r
            for r in rows
            if r["variant"]
            == variant
        ],
        key=lambda x:
            x["frequency"]
    )

    plt.plot(
        [
            x["frequency"]
            for x in data
        ],
        [
            x["wns"]
            for x in data
        ],
        marker="o",
        label=variant
    )


plt.axhline(
    0,
    linewidth=1
)

plt.xlabel(
    "Target frequency (MHz)"
)

plt.ylabel(
    "Final WNS (ns)"
)

plt.title(
    "Pipeline Depth vs Timing"
)

plt.grid(True)

plt.legend()

plt.tight_layout()

plt.savefig(
    OUT
    / "frequency_vs_wns.png",
    dpi=180
)

plt.close()


best = {}

for variant in variants:

    passing = [
        r
        for r in rows
        if (
            r["variant"]
            == variant
            and r["timing_met"]
        )
    ]

    if passing:

        best[variant] = max(
            passing,
            key=lambda x:
                x["frequency"]
        )


if best:

    plt.figure(
        figsize=(7, 5)
    )

    names = list(
        best.keys()
    )

    frequencies = [
        best[name][
            "frequency"
        ]
        for name in names
    ]

    plt.bar(
        names,
        frequencies
    )

    plt.ylabel(
        "Maximum timing-closed frequency (MHz)"
    )

    plt.title(
        "Fmax vs Pipeline Depth"
    )

    plt.tight_layout()

    plt.savefig(
        OUT
        / "fmax_comparison.png",
        dpi=180
    )

    plt.close()


    plt.figure(
        figsize=(7, 5)
    )

    areas = [
        best[name][
            "area"
        ]
        for name in names
    ]

    plt.bar(
        names,
        areas
    )

    plt.ylabel(
        "Final cell area (um²)"
    )

    plt.title(
        "Area Cost of Pipelining"
    )

    plt.tight_layout()

    plt.savefig(
        OUT
        / "area_comparison.png",
        dpi=180
    )

    plt.close()


print(
    "Generated:"
)

print(
    OUT
    / "frequency_vs_wns.png"
)

print(
    OUT
    / "fmax_comparison.png"
)

print(
    OUT
    / "area_comparison.png"
)
