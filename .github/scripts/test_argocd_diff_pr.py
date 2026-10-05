#!/usr/bin/env python3

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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

    def test_raw_live_output_is_never_written(self) -> None:
        fixtures = [
            "< kind: Secret\n< data:\n<   token: PRIVATE_SENTINEL\n",
            "+data:\n+  token: PRIVATE_SENTINEL\n",
            '< annotations:\n<   last-applied-configuration: {"token":"PRIVATE_SENTINEL"}\n',
            "< uid: PRIVATE_SENTINEL\n< clusterIP: 10.0.0.9\n",
        ]
        for payload in fixtures:
            for mode in ("diff", "resources"):
                for code in (0, 1, 20):
                    with self.subTest(mode=mode, code=code, payload=payload):
                        with tempfile.TemporaryDirectory() as directory:
                            with patch.object(diff, "command", return_value=subprocess.CompletedProcess(
                                [], code, payload, "PRIVATE_SENTINEL stderr"
                            )):
                                item = diff.run_live_operation("demo", mode, "head", Path(directory), "demo")
                            self.assertNotIn("PRIVATE_SENTINEL", json.dumps(item))
                            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_public_projection_excludes_every_raw_payload_sink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "raw.txt").write_text("PRIVATE_SENTINEL")
            result = {
                "base_sha": "a" * 40, "head_sha": "b" * 40,
                "errors": ["PRIVATE_SENTINEL stderr"],
                "private_extra": "PRIVATE_SENTINEL",
                "applications": [{
                    "key": "app:system:demo:demo:bastion", "transition": "deleted", "risk": "high",
                    "errors": ["PRIVATE_SENTINEL exception"],
                    "local": {"status": "changed", "diff_file": "raw.txt", "base_inventory": ["PRIVATE_SENTINEL"]},
                    "live": [{"status": "error", "application": "PRIVATE_SENTINEL", "output_file": "raw.txt"}],
                }],
            }
            diff.build_summary(result, output)
            for filename in ("summary.md", "public-result.json"):
                text = (output / filename).read_text()
                self.assertNotIn("PRIVATE_SENTINEL", text)
                self.assertNotIn("raw.txt", text)
                self.assertIn("app:system:demo:demo:bastion", text)
            public = json.loads((output / "public-result.json").read_text())
            self.assertEqual(public["status"], "failure")
            self.assertEqual(public["applications"][0]["error_count"], 1)
            # Unexpected upstream status strings cannot become public messages.
            result["applications"][0]["live"][0]["status"] = "PRIVATE_SENTINEL"
            diff.build_summary(result, output)
            self.assertNotIn("PRIVATE_SENTINEL", (output / "summary.md").read_text())

    def test_workflow_public_sinks_use_only_allowlisted_files(self) -> None:
        workflow = (Path(__file__).parents[1] / "workflows/argocd-diff.yml").read_text()
        # Check the literal publication boundary without adding a YAML dependency
        # to the existing standard-library-only CI test suite.
        upload = workflow.split("uses: actions/upload-artifact@", 1)[1].split("\n      - ", 1)[0]
        paths = re.search(r"(?m)^          path: \|\n((?:            .+\n)+)", upload)
        self.assertIsNotNone(paths)
        self.assertEqual([line.strip() for line in paths.group(1).splitlines()], [
            "${{ github.workspace }}/.local/argocd-diff/summary.md",
            "${{ github.workspace }}/.local/argocd-diff/public-result.json",
        ])
        comment = workflow.split("uses: mshick/add-pr-comment@", 1)[1].split("\n      - ", 1)[0]
        self.assertIn("message-path: ${{ github.workspace }}/.local/argocd-diff/summary.md", comment)
        summary = workflow.split("- name: Add job summary", 1)[1].split("\n      - ", 1)[0]
        self.assertIn('run: cat "${OUTPUT_DIR}/summary.md" >> "${GITHUB_STEP_SUMMARY}"', summary)

    def test_all_lifecycle_transitions_survive_public_projection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for before in (None, "enabled", "disabled"):
                for after in (None, "enabled", "disabled"):
                    state, risk = diff.transition({"state": before} if before else None,
                                                  {"state": after} if after else None)
                    result = {"base_sha": "a" * 40, "head_sha": "b" * 40, "errors": [],
                              "applications": [{"key": "demo", "transition": state, "risk": risk}]}
                    diff.build_summary(result, Path(directory))
                    public = json.loads((Path(directory) / "public-result.json").read_text())
                    self.assertEqual(public["applications"][0]["transition"], state)

    def test_live_list_failures_fail_closed_without_public_diagnostics(self) -> None:
        for response in (subprocess.CompletedProcess([], 1, "", "PRIVATE_SENTINEL auth failure"),
                         subprocess.CompletedProcess([], 0, "PRIVATE_SENTINEL invalid JSON", "")):
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                diff.write_json(output / "result.json", {
                    "base_sha": "a" * 40, "head_sha": "b" * 40,
                    "applications": [], "errors": [],
                })
                with patch.object(diff, "command", return_value=response):
                    self.assertEqual(diff.live(SimpleNamespace(output_dir=directory)), 1)
                self.assertEqual(diff.check(SimpleNamespace(output_dir=directory)), 1)
                for name in ("summary.md", "public-result.json"):
                    self.assertNotIn("PRIVATE_SENTINEL", (output / name).read_text())

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
            self.assertNotIn("auth failed", (output / "summary.md").read_text())
            self.assertIn("1 technical error", (output / "summary.md").read_text())

    def test_deleted_source_inventories_resources_without_diffing_removed_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            source = {
                "key": "app:system:demo:demo:bastion",
                "path": "kubernetes/deploy/system/demo/demo/clusters/bastion",
                "state": "enabled",
            }
            diff.write_json(output / "result.json", {
                "base_sha": "base", "head_sha": "head", "errors": [],
                "applications": [{
                    "key": source["key"], "base": source, "head": None,
                    "transition": "deleted", "risk": "high", "errors": [], "live": [],
                }],
            })
            inventory = "GROUP KIND NAMESPACE NAME ORPHANED\napps Deployment demo demo No\n Pod demo child No\n"

            def fake_command(args, **kwargs):
                if args == ["argocd", "app", "list", "--grpc-web", "-o", "json"]:
                    return subprocess.CompletedProcess(args, 0, json.dumps([{
                        "metadata": {"name": "demo-bastion"},
                        "spec": {"source": {"path": source["path"]}},
                    }]), "")
                self.assertEqual(args, ["argocd", "app", "resources", "demo-bastion",
                                        "--grpc-web", "--output", "tree", "--orphaned=false"])
                return subprocess.CompletedProcess(args, 0, inventory, "")

            with patch.object(diff, "command", side_effect=fake_command) as command:
                self.assertEqual(diff.live(SimpleNamespace(output_dir=directory)), 0)
            self.assertEqual(command.call_count, 2)
            result = json.loads((output / "result.json").read_text())
            live = result["applications"][0]["live"][0]
            self.assertEqual(live["status"], "inventory")
            self.assertNotIn("output_file", live)
            self.assertNotIn("child", (output / "summary.md").read_text())
            self.assertEqual(diff.check(SimpleNamespace(output_dir=directory)), 0)

    def test_resource_inventory_failure_is_not_successful_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(diff, "command", return_value=subprocess.CompletedProcess(
                [], 1, "", "permission denied"
            )):
                item = diff.run_live_operation("demo", "resources", "head", Path(directory), "demo")
            self.assertEqual(item["status"], "error")
            self.assertEqual(item["error"], "argocd resources exited 1")

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
