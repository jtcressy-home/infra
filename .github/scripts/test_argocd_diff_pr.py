#!/usr/bin/env python3

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import argocd_diff_pr as diff


class ArgoDiffPlannerTest(unittest.TestCase):
    def source(self, root: Path, state: str, app: str = "demo", cluster: str = "bastion") -> None:
        path = root / "kubernetes" / "deploy" / "system" / "demo" / app / state / cluster
        path.mkdir(parents=True)
        (path / "kustomization.yaml").write_text("resources: []\n")

    def test_lifecycle_and_app_root_scoping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_root, head_root = root / "base", root / "head"
            self.source(base_root, "clusters")
            self.source(head_root, "disabled")
            base, _ = diff.discover_sources(base_root)
            head, _ = diff.discover_sources(head_root)

            selected, errors, global_change = diff.select_sources(
                ["kubernetes/deploy/system/demo/demo/values.yaml"], base, head
            )

            self.assertEqual(errors, [])
            self.assertFalse(global_change)
            self.assertEqual(len(selected), 1)
            key = selected.pop()
            self.assertEqual(diff.transition(base[key], head[key]), ("disabled", "high"))

    def test_new_deleted_and_rename_are_visible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_root, head_root = root / "base", root / "head"
            self.source(base_root, "clusters", app="old")
            self.source(head_root, "clusters", app="new")
            base, _ = diff.discover_sources(base_root)
            head, _ = diff.discover_sources(head_root)
            selected, errors, _ = diff.select_sources(
                [
                    "kubernetes/deploy/system/demo/old/kustomization.yaml",
                    "kubernetes/deploy/system/demo/new/kustomization.yaml",
                ],
                base,
                head,
            )

            self.assertEqual(errors, [])
            transitions = {diff.transition(base.get(key), head.get(key))[0] for key in selected}
            self.assertEqual(transitions, {"added", "deleted"})

    def test_appset_change_is_explicitly_global(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.source(root, "clusters")
            (root / "kubernetes/argocd/appsets").mkdir(parents=True)
            sources, _ = diff.discover_sources(root)
            selected, errors, global_change = diff.select_sources(
                ["kubernetes/argocd/appsets/apps.yaml"], sources, sources
            )

            self.assertEqual(errors, [])
            self.assertTrue(global_change)
            self.assertIn("static:admin:argocd:appsets:in-cluster", selected)
            self.assertTrue(any(key.startswith("app:") for key in selected))

    def test_unknown_argocd_path_fails_closed(self) -> None:
        selected, errors, _ = diff.select_sources(
            ["kubernetes/argocd/unknown/example.yaml"], {}, {}
        )
        self.assertEqual(selected, set())
        self.assertEqual(errors, ["UNSCOPABLE_CHANGE: kubernetes/argocd/unknown/example.yaml"])

    def test_secret_payload_is_redacted(self) -> None:
        rendered = """apiVersion: v1
kind: Secret
metadata:
  name: credentials
  namespace: demo
data:
  password: c2VjcmV0
"""
        sanitized = diff.redact_secrets(rendered)
        self.assertNotIn("c2VjcmV0", sanitized)
        self.assertIn("data: <redacted>", sanitized)

    def test_live_secret_diff_is_suppressed(self) -> None:
        live = """+apiVersion: v1
+kind: Secret
+data:
+  password: c2VjcmV0
"""
        sanitized = diff.sanitize_live_output(live)
        self.assertNotIn("c2VjcmV0", sanitized)
        self.assertEqual(sanitized, "Live output contained a Secret resource and was redacted.\n")

    def test_infrastructure_failure_updates_result_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            diff.write_json(output / "result.json", {
                "base_sha": "base",
                "head_sha": "head",
                "applications": [],
                "errors": [],
            })
            self.assertEqual(diff.failure(SimpleNamespace(output_dir=directory, message="auth failed")), 0)
            result = json.loads((output / "result.json").read_text())
            self.assertEqual(result["errors"], ["infrastructure: auth failed"])
            self.assertIn("auth failed", (output / "summary.md").read_text())

    def test_plan_renders_real_base_and_head_checkouts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            head, base, output = root / "head", root / "base", root / "output"
            overlay = head / "kubernetes/deploy/system/demo/demo/clusters/bastion"
            overlay.mkdir(parents=True)
            (overlay / "kustomization.yaml").write_text("resources:\n  - configmap.yaml\n")
            configmap = overlay / "configmap.yaml"
            configmap.write_text("apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: demo\ndata:\n  value: base\n")
            project = head / "kubernetes/argocd/projects/system.yaml"
            project.parent.mkdir(parents=True)
            project.write_text("spec:\n  destinations:\n    - namespace: demo\n      name: '*'\n")
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=head, check=True)
            subprocess.run(["git", "config", "user.name", "test"], cwd=head, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=head, check=True)
            subprocess.run(["git", "add", "."], cwd=head, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=head, check=True)
            base_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=head, text=True).strip()
            shutil.copytree(head, base, ignore=shutil.ignore_patterns(".git"))
            configmap.write_text("apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: demo\ndata:\n  value: head\n")
            subprocess.run(["git", "commit", "-qam", "head"], cwd=head, check=True)
            head_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=head, text=True).strip()

            status = diff.plan(SimpleNamespace(
                base_dir=str(base), head_dir=str(head), base_sha=base_sha,
                head_sha=head_sha, output_dir=str(output),
            ))

            result = json.loads((output / "result.json").read_text())
            self.assertEqual(status, 0)
            self.assertEqual(len(result["applications"]), 1)
            self.assertEqual(result["applications"][0]["transition"], "changed")
            self.assertEqual(result["applications"][0]["local"]["status"], "changed")


if __name__ == "__main__":
    unittest.main()
