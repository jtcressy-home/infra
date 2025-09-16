#!/usr/bin/env python3
"""Render Kubernetes overlays for base and PR branches and emit a markdown summary."""

from __future__ import annotations

import difflib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

OverlayKey = Tuple[str, str, str, str]


@dataclass
class RenderResult:
    summary: str
    base_state: Optional[str]
    head_state: Optional[str]
    base_output: Optional[str]
    head_output: Optional[str]
    base_error: Optional[str]
    head_error: Optional[str]


def log(message: str) -> None:
    """Print a message to stdout for debugging."""
    print(message, file=sys.stdout)


def collect_overlays(repo_dir: Path) -> Dict[OverlayKey, Path]:
    """Return mapping of overlay key to kustomization path inside the repo."""
    overlays: Dict[OverlayKey, Path] = {}
    search_root = repo_dir / "kubernetes" / "deploy"
    if not search_root.exists():
        return overlays
    for kustomization in search_root.rglob("kustomization.yaml"):
        try:
            rel_path = kustomization.relative_to(repo_dir)
        except ValueError:
            continue
        parts = rel_path.parts
        if len(parts) != 8:
            continue
        if parts[5] not in {"clusters", "disabled"}:
            continue
        key: OverlayKey = (parts[2], parts[3], parts[4], parts[6])
        overlays[key] = rel_path
    return overlays


def run_task(
    repo_dir: Path, project: str, namespace: str, app: str, cluster: str
) -> subprocess.CompletedProcess[str]:
    cmd = [
        "task",
        "--silent",
        "apps:overlays:render",
        f"project={project}",
        f"namespace={namespace}",
        f"app={app}",
        f"cluster={cluster}",
    ]
    return subprocess.run(
        cmd,
        cwd=repo_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def state_from_path(path: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    return "disabled" if path.parts[5] == "disabled" else "enabled"


def summary_label(key: OverlayKey) -> str:
    project, namespace, app, cluster = key
    return f"{project}/{namespace}/{app} ({cluster})"


def describe_state_change(base_state: Optional[str], head_state: Optional[str]) -> Optional[str]:
    if base_state == head_state:
        return None
    if base_state is None and head_state is not None:
        return f"added as {head_state}"
    if head_state is None and base_state is not None:
        return f"removed (was {base_state})"
    if base_state is None and head_state is None:
        return None
    return f"{base_state} → {head_state}"


def unified_diff(base: str, head: str, label: str) -> str:
    return "".join(
        difflib.unified_diff(
            base.splitlines(keepends=True),
            head.splitlines(keepends=True),
            fromfile=f"{label} (base)",
            tofile=f"{label} (head)",
        )
    )


def write_markdown(
    output_path: Path,
    total: int,
    base_count: int,
    head_count: int,
    diffs: List[Tuple[str, str]],
    state_changes: List[str],
    errors: List[RenderResult],
) -> None:
    lines: List[str] = []
    lines.append("## Overlay Render")
    lines.append("")
    lines.append(
        f"Checked **{total}** overlay{'s' if total != 1 else ''} (base: {base_count}, head: {head_count})."
    )
    lines.append("")

    if state_changes:
        lines.append("### Overlay state changes")
        lines.append("")
        lines.extend(state_changes)
        lines.append("")

    if diffs:
        lines.append("### Rendered manifest differences")
        lines.append("")
        for summary, diff_text in diffs:
            lines.append(f"<details><summary>{summary}</summary>")
            lines.append("")
            lines.append("```diff")
            lines.append(diff_text.rstrip())
            lines.append("```")
            lines.append("</details>")
            lines.append("")
    else:
        lines.append("✅ No manifest differences detected.")
        lines.append("")

    if errors:
        lines.append("### ❌ Rendering errors")
        lines.append("")
        for result in errors:
            lines.append(f"<details><summary>{result.summary}</summary>")
            lines.append("")
            if result.base_error:
                lines.append("**Base branch output:**")
                lines.append("")
                lines.append("```")
                lines.append(result.base_error.rstrip())
                lines.append("```")
                lines.append("")
            if result.head_error:
                lines.append("**PR output:**")
                lines.append("")
                lines.append("```")
                lines.append(result.head_error.rstrip())
                lines.append("```")
                lines.append("")
            lines.append("</details>")
            lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: List[str]) -> int:
    if len(argv) != 4:
        print(
            "Usage: render_overlays.py <base_dir> <head_dir> <output_file>",
            file=sys.stderr,
        )
        return 2

    base_dir = Path(argv[1]).resolve()
    head_dir = Path(argv[2]).resolve()
    output_path = Path(argv[3]).resolve()

    base_overlays = collect_overlays(base_dir)
    head_overlays = collect_overlays(head_dir)

    keys = sorted(set(base_overlays.keys()) | set(head_overlays.keys()))
    results: List[RenderResult] = []
    diffs: List[Tuple[str, str]] = []
    state_changes: List[str] = []
    had_failure = False

    for key in keys:
        project, namespace, app, cluster = key
        summary = summary_label(key)
        base_path = base_overlays.get(key)
        head_path = head_overlays.get(key)
        base_state = state_from_path(base_path)
        head_state = state_from_path(head_path)

        base_output: Optional[str] = None
        head_output: Optional[str] = None
        base_error: Optional[str] = None
        head_error: Optional[str] = None

        if base_path is not None:
            log(f"Rendering base overlay: {summary}")
            base_result = run_task(base_dir, project, namespace, app, cluster)
            if base_result.returncode != 0:
                base_error = base_result.stdout
            else:
                base_output = base_result.stdout
        else:
            base_output = ""

        if head_path is not None:
            log(f"Rendering PR overlay: {summary}")
            head_result = run_task(head_dir, project, namespace, app, cluster)
            if head_result.returncode != 0:
                head_error = head_result.stdout
            else:
                head_output = head_result.stdout
        else:
            head_output = ""

        result = RenderResult(
            summary=summary,
            base_state=base_state,
            head_state=head_state,
            base_output=base_output,
            head_output=head_output,
            base_error=base_error,
            head_error=head_error,
        )
        results.append(result)

        if base_error or head_error:
            had_failure = True
            continue

        state_change = describe_state_change(base_state, head_state)
        if state_change:
            state_changes.append(f"* `{summary}` {state_change}.")

        if base_output is None or head_output is None:
            continue

        if base_output != head_output:
            diff_text = unified_diff(base_output, head_output, summary)
            display_summary = summary
            if state_change:
                display_summary = f"{summary} [{state_change}]"
            diffs.append((display_summary, diff_text))

    write_markdown(
        output_path,
        total=len(keys),
        base_count=len(base_overlays),
        head_count=len(head_overlays),
        diffs=diffs,
        state_changes=state_changes,
        errors=[r for r in results if r.base_error or r.head_error],
    )

    return 1 if had_failure else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
