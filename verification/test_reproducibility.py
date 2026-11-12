"""Regression checks for stale physical caches, without running place and route."""

from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import clock_sweep as sweep
import physical_environment as environment


class PhysicalCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mac repo ")
        self.root = Path(self.temp.name)
        for pattern in ["rtl/*.sv", "physical/orfs/*.mk", "physical/constraints/*.sdc",
                        "scripts/*.py", "physical/environment.json", "physical/run_orfs.sh"]:
            for source in REPO.glob(pattern):
                target = self.root / source.relative_to(REPO)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        self.original_output = sweep.OUTPUT_DIR
        self.root_patch = patch.object(sweep, "ROOT", self.root)
        self.sdc_patch = patch.object(sweep, "SDC_PATH", self.root / "physical/constraints/mac_sweep.sdc")
        self.env_patch = patch.dict(os.environ)
        for item in [self.root_patch, self.sdc_patch, self.env_patch]:
            item.start()
            self.addCleanup(item.stop)
        os.environ.pop("ORFS_IMAGE", None)
        sweep.configure_output(self.root / "build/clock_sweep")
        sweep.ensure_dirs()
        self.addCleanup(sweep.configure_output, self.original_output)
        self.addCleanup(self.temp.cleanup)

    def row(self, design="mac_2stage", period=6.0):
        return {"design": design, "variant": sweep.DESIGNS[design]["label"],
                "latency_cycles": sweep.DESIGNS[design]["latency"], "period_ns": period,
                "frequency_mhz": 1000 / period, "wns_ns": 0.1, "tns_ns": 0,
                "flow_completed": True, "timing_met": True,
                "provenance": sweep.point_provenance(design, period)}

    def save(self, row):
        path = sweep.OUTPUT_DIR / row["design"] / f"{row['period_ns']:.4f}ns.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(row))
        return path

    def run_point(self, period=6.0, **kwargs):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return sweep.run_point("mac_2stage", period, **kwargs)

    def test_unchanged_inputs_reuse_cache(self):
        self.save(self.row())
        with patch.object(sweep.subprocess, "run") as flow:
            self.assertTrue(self.run_point()["timing_met"])
            flow.assert_not_called()

    def test_each_input_change_forces_flow(self):
        for name in ["rtl/mac_2stage.sv", "physical/orfs/mac_2stage_sweep.mk",
                     "scripts/clock_sweep.py", "scripts/physical_environment.py",
                     "physical/constraints/mac_5ns.sdc", "physical/environment.json"]:
            with self.subTest(name=name):
                self.save(self.row())
                with (self.root / name).open("a") as stream:
                    stream.write("\n")
                with patch.object(sweep.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as flow:
                    with patch.object(sweep, "parse_metrics", side_effect=lambda d, p: self.row(d, p)):
                        self.run_point()
                flow.assert_called_once()

    def test_image_override_invalidates_cache_and_is_used(self):
        self.save(self.row())
        image = "openroad/orfs@sha256:" + "a" * 64
        with patch.dict(os.environ, {"ORFS_IMAGE": image}):
            self.assertEqual(sweep.all_saved_rows(), [])
            self.assertIn(image, sweep.docker_command("mac_2stage"))

    def test_generated_constraints_invalidate_cache(self):
        row = self.row()
        self.save(row)
        original = sweep.sdc_text
        with patch.object(sweep, "sdc_text", side_effect=lambda p: original(p) + "\n# changed constraint\n"):
            self.assertFalse(sweep.reusable_record(row, "mac_2stage", 6.0))
            self.assertEqual(sweep.all_saved_rows(), [])

    def test_other_period_does_not_invalidate_existing_point(self):
        row = self.row()
        self.save(row)
        sweep.write_sdc(7.0)
        self.assertTrue(sweep.reusable_record(row, "mac_2stage", 6.0))
        self.assertEqual(len(sweep.all_saved_rows()), 1)

    def test_legacy_and_malformed_json_are_excluded(self):
        row = self.row()
        row.pop("provenance")
        path = self.save(row)
        for contents in [json.dumps(row), "{invalid", "[]"]:
            path.write_text(contents)
            self.assertEqual(sweep.all_saved_rows(), [])
        with patch.object(sweep.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as flow:
            with patch.object(sweep, "parse_metrics", side_effect=lambda d, p: self.row(d, p)):
                self.run_point()
        flow.assert_called_once()

    def test_failed_flow_is_retried(self):
        with patch.object(sweep.subprocess, "run", return_value=SimpleNamespace(returncode=1)) as flow:
            self.assertFalse(self.run_point()["flow_completed"])
            self.assertFalse(self.run_point()["flow_completed"])
        self.assertEqual(flow.call_count, 2)
        self.assertEqual(sweep.all_saved_rows(), [])

    def test_incomplete_flow_does_not_become_a_timing_boundary(self):
        failed = dict(self.row(), flow_completed=False, timing_met=False, wns_ns=None)
        with patch.object(sweep, "run_point", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, "Incomplete physical run"):
                sweep.coarse_sweep()
            with patch.object(sweep, "find_bracket", return_value=(5.0, 7.0)):
                with redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(RuntimeError, "incomplete physical run"):
                        sweep.refine_design("mac_2stage", [])

    def test_changed_inputs_during_flow_are_not_cached(self):
        def change_inputs(*args, **kwargs):
            with (self.root / "rtl/mac_2stage.sv").open("a") as stream:
                stream.write("\n// changed during run\n")
            return SimpleNamespace(returncode=0)
        with patch.object(sweep.subprocess, "run", side_effect=change_inputs):
            with self.assertRaisesRegex(RuntimeError, "changed during"):
                self.run_point()
        self.assertEqual(sweep.all_saved_rows(), [])

    def test_summary_rejects_stale_design_period_and_incomplete_runs(self):
        self.save(self.row())
        self.assertEqual(len(sweep.all_saved_rows()), 1)
        cases = [{"design": "mac_1stage"}, {"period_ns": 7.0},
                 {"flow_completed": False}, {"wns_ns": None}, {"timing_met": False}]
        for changes in cases:
            row = self.row()
            row.update(changes)
            (sweep.OUTPUT_DIR / "mac_2stage/6.0000ns.json").write_text(json.dumps(row))
            self.assertEqual(sweep.all_saved_rows(), [])

    def test_forced_confirmation_failure_removes_selected_result(self):
        row = self.row()
        self.save(row)
        stale_snapshot = sweep.FMAX_DIR / "mac_2stage"
        stale_snapshot.mkdir()
        (stale_snapshot / "best_run.json").write_text(json.dumps(row))
        with patch.object(sys, "argv", ["clock_sweep.py", "--refine", "0", "--output", str(sweep.OUTPUT_DIR)]):
            with patch.object(sweep.shutil, "which", return_value="docker"):
                with patch.object(sweep, "coarse_sweep", return_value=[row]):
                    with patch.object(sweep.subprocess, "run", return_value=SimpleNamespace(returncode=1, stdout="")):
                        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                            sweep.main()
        self.assertFalse(stale_snapshot.exists())
        self.assertNotIn("2-stage |", (sweep.OUTPUT_DIR / "fmax_summary.md").read_text())

    def test_summary_and_snapshot_use_confirmation_metrics(self):
        row = dict(self.row(), area_um2=100.0)
        self.save(row)
        confirmed = dict(self.row(), wns_ns=0.05, area_um2=123.0)
        with patch.object(sys, "argv", ["clock_sweep.py", "--refine", "0", "--output", str(sweep.OUTPUT_DIR)]):
            with patch.object(sweep.shutil, "which", return_value="docker"):
                with patch.object(sweep, "coarse_sweep", return_value=[row]):
                    with patch.object(sweep.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="")):
                        with patch.object(sweep, "parse_metrics", return_value=confirmed):
                            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                                sweep.main()
        saved = json.loads((sweep.FMAX_DIR / "mac_2stage/best_run.json").read_text())
        self.assertEqual(saved["wns_ns"], 0.05)
        self.assertEqual(saved["area_um2"], 123.0)
        self.assertEqual(saved["provenance"], sweep.point_provenance("mac_2stage", 6.0))
        self.assertIn("0.050", (sweep.OUTPUT_DIR / "clock_sweep.md").read_text())

    def test_physical_runner_resolves_renamed_clone_from_another_directory(self):
        binary_dir = self.root / "fake tools"
        binary_dir.mkdir()
        docker = binary_dir / "docker"
        docker.write_text("#!/usr/bin/env python3\nimport json,os,sys\n"
                          "with open(os.environ['MAC_DOCKER_TRACE'],'a') as f:\n"
                          " f.write(json.dumps(sys.argv[1:])+'\\n')\n")
        docker.chmod(0o755)
        trace = self.root / "docker_arguments.jsonl"
        env = dict(os.environ, PATH=str(binary_dir) + os.pathsep + os.environ["PATH"],
                   MAC_DOCKER_TRACE=str(trace))
        result = subprocess.run(["bash", str(self.root / "physical/run_orfs.sh")],
                                cwd=self.root.parent, env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in trace.read_text().splitlines()]
        self.assertEqual(len(calls), 3)
        for command in calls:
            self.assertIn(str(self.root) + ":/work/pipelined-mac", command)
            self.assertIn(environment.selected_environment(self.root)["image"], command)
            self.assertIn("linux/amd64", command)
        manifest = json.loads((self.root / "physical/work/run_manifest.json").read_text())
        self.assertIn("rtl/mac_2stage.sv", manifest["files_sha256"])


class EnvironmentTests(unittest.TestCase):
    def test_mutable_tags_are_rejected(self):
        for image in ["openroad/orfs:latest", "openroad/orfs:stable", "openroad/orfs@sha256:123"]:
            with self.subTest(image=image), patch.dict(os.environ, {"ORFS_IMAGE": image}):
                with self.assertRaisesRegex(ValueError, "immutable"):
                    environment.selected_environment()

    def test_default_pin_has_platform_and_full_digest(self):
        with patch.dict(os.environ):
            os.environ.pop("ORFS_IMAGE", None)
            selected = environment.selected_environment()
        self.assertRegex(selected["image"], r"^openroad/orfs@sha256:[0-9a-f]{64}$")
        self.assertEqual(selected["platform"], "linux/amd64")


if __name__ == "__main__":
    unittest.main()
