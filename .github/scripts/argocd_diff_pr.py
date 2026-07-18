#!/usr/bin/env python3
"""Plan and run a changed-source Argo CD PR diff."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


SCHEMA_VERSION = 1
MAX_WORKERS = 4
APP_TIMEOUT = 90
GENERATED_FILES = {
    ".github/scripts/argocd_diff_pr.py",
    ".github/workflows/argocd-diff.yml",
    ".taskfiles/apps/overlay/Taskfile.yaml",
}


def command(args: list[str], *, cwd: Path | None = None, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=timeout, check=False)


def source_key(kind: str, project: str, namespace: str, app: str, cluster: str) -> str:
    return ":".join((kind, project, namespace, app, cluster))


def discover_sources(root: Path) -> tuple[dict[str, dict], list[str]]:
    sources: dict[str, dict] = {}
    errors: list[str] = []

    def add(source: dict) -> None:
        key = source["key"]
        if key in sources:
            errors.append(f"duplicate source identity {key}: {sources[key]['path']} and {source['path']}")
        else:
            sources[key] = source

    for state, directory in (("enabled", "clusters"), ("disabled", "disabled")):
        pattern = f"kubernetes/deploy/*/*/*/{directory}/*/kustomization.yaml"
        for manifest in sorted(root.glob(pattern)):
            parts = manifest.relative_to(root).parts
            project, namespace, app, cluster = parts[2], parts[3], parts[4], parts[6]
            add({
                "key": source_key("app", project, namespace, app, cluster),
                "kind": "app",
                "project": project,
                "namespace": namespace,
                "app": app,
                "cluster": cluster,
                "state": state,
                "path": manifest.parent.relative_to(root).as_posix(),
            })

    for manifest in sorted(root.glob("kubernetes/clusters/*/cni/kustomization.yaml")):
        cluster = manifest.relative_to(root).parts[2]
        add({
            "key": source_key("cni", "system", "kube-system", "cni", cluster),
            "kind": "cni",
            "project": "system",
            "namespace": "kube-system",
            "app": "cni",
            "cluster": cluster,
            "state": "enabled",
            "path": manifest.parent.relative_to(root).as_posix(),
        })

    for name, path in (
        ("root", "kubernetes/argocd/static-apps"),
        ("appsets", "kubernetes/argocd/appsets"),
        ("projects", "kubernetes/argocd/projects"),
    ):
        if (root / path).is_dir():
            add({
                "key": source_key("static", "admin", "argocd", name, "in-cluster"),
                "kind": "static",
                "project": "admin",
                "namespace": "argocd",
                "app": name,
                "cluster": "in-cluster",
                "state": "enabled",
                "path": path,
            })
    return sources, errors


def changed_paths(head: Path, base_sha: str, head_sha: str) -> list[str]:
    result = command(["git", "diff", "--name-status", "--find-renames", base_sha, head_sha], cwd=head)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git diff failed")
    paths: set[str] = set()
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if not fields:
            continue
        paths.update(fields[1:])
    return sorted(paths)


def select_sources(paths: list[str], base: dict[str, dict], head: dict[str, dict]) -> tuple[set[str], list[str], bool]:
    all_sources = {**base, **head}
    selected: set[str] = set()
    errors: list[str] = []
    global_change = False

    for path in paths:
        parts = Path(path).parts
        matched: set[str] = set()
        if len(parts) >= 5 and parts[:2] == ("kubernetes", "deploy"):
            identity = parts[2:5]
            matched = {
                key for key, source in all_sources.items()
                if source["kind"] == "app"
                and (source["project"], source["namespace"], source["app"]) == identity
            }
            if not matched:
                errors.append(f"UNSCOPABLE_CHANGE: {path}")
        elif len(parts) >= 4 and parts[:2] == ("kubernetes", "clusters") and parts[3] == "cni":
            matched = {
                key for key, source in all_sources.items()
                if source["kind"] == "cni" and source["cluster"] == parts[2]
            }
            if not matched:
                errors.append(f"UNSCOPABLE_CHANGE: {path}")
        elif parts[:3] == ("kubernetes", "argocd", "appsets"):
            global_change = True
            matched = {
                key for key, source in all_sources.items()
                if source["kind"] in {"app", "cni"} and source["state"] == "enabled"
            }
            matched.update(key for key, source in all_sources.items() if source["kind"] == "static" and source["app"] == "appsets")
        elif parts[:3] == ("kubernetes", "argocd", "projects"):
            project = Path(path).stem if Path(path).suffix in {".yaml", ".yml"} else None
            matched = {
                key for key, source in all_sources.items()
                if source["kind"] == "static" and source["app"] == "projects"
                or project is not None and source["project"] == project and source["state"] == "enabled"
            }
        elif parts[:3] == ("kubernetes", "argocd", "static-apps"):
            matched = {key for key, source in all_sources.items() if source["kind"] == "static" and source["app"] == "root"}
        elif parts[:2] == ("kubernetes", "argocd"):
            errors.append(f"UNSCOPABLE_CHANGE: {path}")
        elif path.startswith("kubernetes/") and not path.startswith("kubernetes/clusters/"):
            errors.append(f"UNSCOPABLE_CHANGE: {path}")
        elif path in GENERATED_FILES:
            pass
        selected.update(matched)
    return selected, errors, global_change


def transition(base: dict | None, head: dict | None) -> tuple[str, str]:
    base_state = base and base["state"]
    head_state = head and head["state"]
    transitions = {
        ("enabled", "enabled"): ("changed", "normal"),
        ("disabled", "disabled"): ("dormant-changed", "normal"),
        (None, "enabled"): ("added", "normal"),
        (None, "disabled"): ("disabled-added", "normal"),
        ("disabled", "enabled"): ("enabled", "normal"),
        ("enabled", "disabled"): ("disabled", "high"),
        ("enabled", None): ("deleted", "high"),
        ("disabled", None): ("disabled-deleted", "normal"),
    }
    return transitions.get((base_state, head_state), ("changed", "normal"))


def redact_secrets(rendered: str) -> str:
    documents = re.split(r"(?m)^---\s*$", rendered)
    sanitized: list[str] = []
    for document in documents:
        if re.search(r"(?m)^kind:\s*Secret\s*$", document):
            fields = []
            for field in ("apiVersion", "kind"):
                match = re.search(rf"(?m)^{field}:\s*(.+)$", document)
                if match:
                    fields.append(f"{field}: {match.group(1)}")
            metadata = re.search(r"(?m)^metadata:\s*\n((?:[ \t]+[^\n]*(?:\n|$))*)", document)
            fields.append("metadata:\n" + (metadata.group(1) if metadata else "  name: unknown\n"))
            fields.append("data: <redacted>\nstringData: <redacted>")
            sanitized.append("\n".join(fields))
        elif document.strip():
            sanitized.append(document.strip())
    return "\n---\n".join(sanitized).rstrip() + "\n" if sanitized else ""


def sanitize_diff(text: str) -> str:
    text = re.sub(r"(?im)^([+\- ]*)(data|stringData):.*$", r"\1\2: <redacted>", text)
    text = re.sub(r"(?i)(authorization:\s*(?:bearer\s+)?)\S+", r"\1<redacted>", text)
    return text


def sanitize_live_output(text: str) -> str:
    if re.search(r"(?im)^[+\- ]*kind:\s*Secret\s*$", text):
        return "Live output contained a Secret resource and was redacted.\n"
    return sanitize_diff(text)


def inventory(rendered: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for document in re.split(r"(?m)^---\s*$", rendered):
        api = re.search(r"(?m)^apiVersion:\s*['\"]?([^'\"\s]+)", document)
        kind = re.search(r"(?m)^kind:\s*['\"]?([^'\"\s]+)", document)
        metadata = re.search(r"(?m)^metadata:\s*\n((?:[ \t]+[^\n]*(?:\n|$))*)", document)
        if not api or not kind or not metadata:
            continue
        block = metadata.group(1)
        name = re.search(r"(?m)^\s+name:\s*['\"]?([^'\"\s]+)", block)
        namespace = re.search(r"(?m)^\s+namespace:\s*['\"]?([^'\"\s]+)", block)
        if name:
            items.append({
                "apiVersion": api.group(1),
                "kind": kind.group(1),
                "namespace": namespace.group(1) if namespace else "",
                "name": name.group(1),
            })
    return items


def render(root: Path, source: dict) -> str:
    path = root / source["path"]
    if (path / "kustomization.yaml").is_file() or (path / "kustomization.yml").is_file():
        result = command(["kustomize", "build", "--enable-helm", str(path)], timeout=APP_TIMEOUT)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or f"kustomize failed for {source['path']}")
        output = result.stdout
    else:
        files = sorted(p for p in path.rglob("*") if p.suffix in {".yaml", ".yml", ".json"} and p.is_file())
        output = "\n---\n".join(file.read_text() for file in files)
    output = redact_secrets(output)
    if not output.strip():
        raise RuntimeError(f"empty render for {source['path']}")
    return output


def project_allows_namespace(root: Path, source: dict) -> bool:
    if source["kind"] not in {"app", "cni"} or source["state"] != "enabled":
        return True
    project_file = root / "kubernetes" / "argocd" / "projects" / f"{source['project']}.yaml"
    if not project_file.is_file():
        return False
    text = project_file.read_text()
    destinations = re.search(r"(?ms)^  destinations:\s*\n(.*?)(?=^  [A-Za-z]|\Z)", text)
    if not destinations:
        return False
    namespaces = re.findall(r"(?m)^\s+-?\s*namespace:\s*['\"]?([^'\"\s]+)", destinations.group(1))
    return source["namespace"] in namespaces or "*" in namespaces


def slug(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", key).strip("-")


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def build_summary(result: dict, output_dir: Path) -> None:
    apps = result["applications"]
    errors = result.get("errors", [])
    status = "failure" if errors or any(app.get("errors") for app in apps) else "success"
    result["status"] = status
    counts: dict[str, int] = {}
    for app in apps:
        counts[app["transition"]] = counts.get(app["transition"], 0) + 1
    lines = [
        "## Argo CD changed-source diff",
        "",
        f"**Status:** {status}  ",
        f"**Base:** `{result['base_sha']}`  ",
        f"**Head:** `{result['head_sha']}`  ",
        f"**Affected sources:** {len(apps)}",
        "",
    ]
    if counts:
        lines.extend(("| Transition | Count |", "|---|---:|"))
        lines.extend(f"| {name} | {count} |" for name, count in sorted(counts.items()))
        lines.append("")
    if errors:
        lines.extend(("### Blocking errors", ""))
        lines.extend(f"- {error}" for error in errors)
        lines.append("")
    if apps:
        lines.extend(("### Sources", "", "| Source | Transition | Risk | Local | Live |", "|---|---|---|---|---|"))
        for app in apps:
            local = app.get("local", {}).get("status", "not-run")
            live = ", ".join(item["status"] for item in app.get("live", [])) or "not-needed"
            lines.append(f"| `{app['key']}` | {app['transition']} | {app['risk']} | {local} | {live} |")
        lines.append("")
    for app in apps:
        details: list[str] = []
        diff_file = app.get("local", {}).get("diff_file")
        if diff_file and (output_dir / diff_file).is_file():
            details.append((output_dir / diff_file).read_text()[:6000])
        for item in app.get("live", []):
            if item.get("output_file") and (output_dir / item["output_file"]).is_file():
                details.append((output_dir / item["output_file"]).read_text()[:6000])
        if details or app.get("errors"):
            lines.extend((f"<details><summary>{app['key']} — {app['transition']}</summary>", ""))
            if app.get("errors"):
                lines.extend(f"- **Error:** {error}" for error in app["errors"])
                lines.append("")
            for detail in details:
                lines.extend(("```diff", detail.rstrip(), "```", ""))
            lines.extend(("</details>", ""))
    summary = "\n".join(lines)
    if len(summary) > 60000:
        summary = summary[:59000] + "\n\n_Output truncated; download the workflow artifact for complete sanitized evidence._\n"
    (output_dir / "summary.md").write_text(summary)


def plan_application(
    key: str,
    base_source: dict | None,
    head_source: dict | None,
    base_root: Path,
    head_root: Path,
    output_dir: Path,
    global_change: bool,
) -> dict:
    state, risk = transition(base_source, head_source)
    app = {
        "key": key,
        "transition": state,
        "risk": "high" if global_change else risk,
        "base": base_source,
        "head": head_source,
        "local": {"status": "not-run"},
        "live": [],
        "errors": [],
    }
    rendered: dict[str, str] = {}
    for side, root, source in (("base", base_root, base_source), ("head", head_root, head_source)):
        if source is None:
            continue
        try:
            rendered[side] = render(root, source)
            app["local"][f"{side}_sha256"] = hashlib.sha256(rendered[side].encode()).hexdigest()
            app["local"][f"{side}_inventory"] = inventory(rendered[side])
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            app["errors"].append(f"{side} render: {error}")
    if head_source and not project_allows_namespace(head_root, head_source):
        app["errors"].append(f"AppProject {head_source['project']} does not allow namespace {head_source['namespace']}")
    if not app["errors"]:
        before, after = rendered.get("base", ""), rendered.get("head", "")
        local_diff = "".join(difflib.unified_diff(
            before.splitlines(keepends=True), after.splitlines(keepends=True),
            fromfile=f"base/{base_source['path'] if base_source else key}",
            tofile=f"head/{head_source['path'] if head_source else key}",
        ))
        app["local"]["status"] = "changed" if local_diff else "no-change"
        if local_diff:
            relative = f"diffs/{slug(key)}-local.diff"
            (output_dir / relative).parent.mkdir(parents=True, exist_ok=True)
            (output_dir / relative).write_text(sanitize_diff(local_diff))
            app["local"]["diff_file"] = relative
    else:
        app["local"]["status"] = "error"
    return app


def plan(args: argparse.Namespace) -> int:
    base_root, head_root, output_dir = Path(args.base_dir), Path(args.head_dir), Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base, base_errors = discover_sources(base_root)
    head, head_errors = discover_sources(head_root)
    try:
        paths = changed_paths(head_root, args.base_sha, args.head_sha)
    except RuntimeError as error:
        paths, diff_errors = [], [str(error)]
    else:
        diff_errors = []
    selected, scope_errors, global_change = select_sources(paths, base, head)
    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "base_sha": args.base_sha,
        "head_sha": args.head_sha,
        "changed_paths": paths,
        "global_change": global_change,
        "applications": [],
        "errors": base_errors + head_errors + diff_errors + scope_errors,
    }

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        result["applications"] = list(executor.map(
            lambda key: plan_application(
                key, base.get(key), head.get(key), base_root, head_root, output_dir, global_change
            ),
            sorted(selected),
        ))

    build_summary(result, output_dir)
    write_json(output_dir / "result.json", result)
    return 1 if result["errors"] or any(app["errors"] for app in result["applications"]) else 0


def live_sources(application: dict) -> list[str]:
    spec = application.get("spec", {})
    paths = []
    if spec.get("source", {}).get("path"):
        paths.append(spec["source"]["path"])
    paths.extend(source["path"] for source in spec.get("sources", []) if source.get("path"))
    return paths


def run_live_operation(app_name: str, mode: str, revision: str, output_dir: Path, key: str) -> dict:
    if mode == "diff":
        proc = command(["argocd", "app", "diff", app_name, "--grpc-web", "--revision", revision, "--diff-exit-code", "20"], timeout=APP_TIMEOUT)
        status = "no-change" if proc.returncode == 0 else "changed" if proc.returncode == 20 else "error"
    else:
        proc = command(["argocd", "app", "resources", app_name, "--grpc-web", "-o", "json"], timeout=APP_TIMEOUT)
        status = "inventory" if proc.returncode == 0 else "error"
    relative = f"diffs/{slug(key)}-{slug(app_name)}-{mode}.txt"
    output = sanitize_live_output(proc.stdout + proc.stderr)
    (output_dir / relative).parent.mkdir(parents=True, exist_ok=True)
    (output_dir / relative).write_text(output)
    item = {"application": app_name, "mode": mode, "status": status, "output_file": relative}
    if status == "error":
        item["error"] = f"argocd {mode} exited {proc.returncode}"
    return item


def live(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    result_path = output_dir / "result.json"
    result = json.loads(result_path.read_text())
    proc = command(["argocd", "app", "list", "--grpc-web", "-o", "json"], timeout=APP_TIMEOUT)
    if proc.returncode:
        result["errors"].append(f"Argo CD inventory failed: {sanitize_diff(proc.stderr.strip())}")
        build_summary(result, output_dir)
        write_json(result_path, result)
        return 1
    try:
        payload = json.loads(proc.stdout)
        live_apps = payload.get("items", []) if isinstance(payload, dict) else payload
    except json.JSONDecodeError as error:
        result["errors"].append(f"Argo CD inventory returned invalid JSON: {error}")
        build_summary(result, output_dir)
        write_json(result_path, result)
        return 1

    by_path: dict[str, list[dict]] = {}
    for application in live_apps:
        for path in live_sources(application):
            by_path.setdefault(path, []).append(application)

    work: list[tuple[dict, str, str]] = []
    for app in result["applications"]:
        head_source, base_source = app.get("head"), app.get("base")
        if head_source and head_source["state"] == "enabled":
            matches = by_path.get(head_source["path"], [])
            if not matches and app["transition"] not in {"added", "enabled"}:
                app["errors"].append(f"no live Application has source path {head_source['path']}")
            work.extend((app, item["metadata"]["name"], "diff") for item in matches)
        elif base_source and base_source["state"] == "enabled":
            matches = by_path.get(base_source["path"], [])
            if not matches:
                app["errors"].append(f"no live Application has source path {base_source['path']}")
            work.extend((app, item["metadata"]["name"], "resources") for item in matches)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(run_live_operation, name, mode, result["head_sha"], output_dir, app["key"]): app
            for app, name, mode in work
        }
        for future, app in futures.items():
            try:
                item = future.result()
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                app["errors"].append(f"live operation: {error}")
                continue
            app["live"].append(item)
            if item.get("error"):
                app["errors"].append(f"{item['application']}: {item['error']}")

    build_summary(result, output_dir)
    write_json(result_path, result)
    return 1 if result["errors"] or any(app["errors"] for app in result["applications"]) else 0


def check(args: argparse.Namespace) -> int:
    result = json.loads((Path(args.output_dir) / "result.json").read_text())
    return 1 if result.get("errors") or any(app.get("errors") for app in result.get("applications", [])) else 0


def failure(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    result_path = output_dir / "result.json"
    result = json.loads(result_path.read_text())
    has_error = result.get("errors") or any(app.get("errors") for app in result.get("applications", []))
    if not has_error:
        result["errors"].append(f"infrastructure: {args.message}")
        build_summary(result, output_dir)
        write_json(result_path, result)
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    plan_parser = commands.add_parser("plan")
    plan_parser.add_argument("--base-dir", required=True)
    plan_parser.add_argument("--head-dir", required=True)
    plan_parser.add_argument("--base-sha", required=True)
    plan_parser.add_argument("--head-sha", required=True)
    plan_parser.add_argument("--output-dir", required=True)
    plan_parser.set_defaults(func=plan)
    for name, function in (("live", live), ("check", check)):
        subparser = commands.add_parser(name)
        subparser.add_argument("--output-dir", required=True)
        subparser.set_defaults(func=function)
    failure_parser = commands.add_parser("failure")
    failure_parser.add_argument("--output-dir", required=True)
    failure_parser.add_argument("--message", required=True)
    failure_parser.set_defaults(func=failure)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    sys.exit(arguments.func(arguments))
