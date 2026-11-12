#!/usr/bin/env python3
"""Shared immutable-image selection and input provenance for physical runs."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 1


def selected_environment(root=ROOT):
    config = json.loads((root / "physical/environment.json").read_text())
    image = os.environ.get("ORFS_IMAGE", config["image"])
    if not re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", image):
        raise ValueError("ORFS_IMAGE must use an immutable repository@sha256:<64 hex digits> reference")
    return {"image": image, "platform": config["platform"]}


def input_hashes(root=ROOT):
    files = [*root.glob("rtl/*.sv"), *root.glob("physical/orfs/*.mk"),
             *root.glob("scripts/*.py"), root / "physical/run_orfs.sh",
             root / "physical/environment.json"]
    # The sweep writes mac_sweep.sdc for each point. Hash its generated text
    # per point instead; hashing the previous point's file invalidates caches.
    files += [p for p in root.glob("physical/constraints/*.sdc")
              if p.name != "mac_sweep.sdc"]
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(files)}


def provenance(design, period, sdc_text, environment, root=ROOT):
    inputs = {"schema": SCHEMA, "design": design, "period_ns": round(period, 4),
              "environment": environment, "files_sha256": input_hashes(root),
              "sdc_sha256": hashlib.sha256(sdc_text.encode()).hexdigest()}
    fingerprint = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    return {"fingerprint": fingerprint, "inputs": inputs}


def write_manifest(path, root=ROOT):
    environment = selected_environment(root)
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                         text=True, capture_output=True)
    record = {"recorded_at_utc": datetime.now(timezone.utc).isoformat(),
              "environment": environment, "files_sha256": input_hashes(root),
              "git_commit": git.stdout.strip() if git.returncode == 0 else None,
              "scope": "Inputs selected for this new run; completion is recorded in flow logs"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", action="store_true")
    parser.add_argument("--platform", action="store_true")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    try:
        environment = selected_environment()
        if args.image:
            print(environment["image"])
        elif args.platform:
            print(environment["platform"])
        elif args.manifest:
            write_manifest(args.manifest)
        else:
            print(json.dumps(environment, indent=2))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Physical environment: {error}\n")


if __name__ == "__main__":
    main()
