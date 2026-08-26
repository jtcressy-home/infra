# Renovate Triage Policy

Durable risk policy for triaging Renovate pull requests in this repo. The weekly
Renovate triage automation reads this file at the start of every run, applies the
rules below, and appends new rules here (via PR) whenever the maintainer answers a
question about a previously undecided update.

Renovate PRs already covered by `automerge: true` in `renovate.json` (they carry the
`renovate:automerge` label and are approved by
`.github/workflows/renovate-auto-approve.yml`) are out of scope — triage only handles
PRs that are *not* auto-merging.

## Decision procedure

For each in-scope open Renovate PR:

1. Check the rules in [Auto-approve rules](#auto-approve-rules) and
   [Always ask rules](#always-ask-rules), most specific match wins.
2. If no rule matches, fall back to [Default heuristics](#default-heuristics).
3. When still in doubt, ask. Never merge an update whose blast radius is unclear.

An update may only be approved and merged when all required checks pass and the diff
contains nothing beyond the dependency bump.

## Default heuristics

Treat as **safe** (approve + merge) when all of the following hold:

- The update is a patch or minor bump, or a digest bump of a pinned tag.
- The dependency is a leaf application (its failure does not take down other
  workloads, networking, storage, or the cluster control plane).
- The release notes contain no breaking changes, no CRD changes, and no manual
  migration steps.
- CI is green on the PR.

Treat as **risky** (ask first) when any of the following hold:

- Major version bump of anything.
- Cluster-level or platform components: Talos, Kubernetes/kubelet, CNI (multus,
  cilium), CoreDNS, cert-manager, external-dns, ingress/gateway controllers,
  ArgoCD, Tailscale, storage (volsync, snapshot-controller, CSI drivers, restic),
  databases and operators (CloudNativePG, PostgreSQL, valkey), device plugins,
  and monitoring/logging stacks that other alerting depends on.
- Any update whose changelog mentions CRD changes, schema migrations, removed or
  renamed configuration keys, or default-behaviour changes.
- GitHub Actions workflow updates that change the runner/action major version.
- The dependency has no readable changelog or release notes.

## Auto-approve rules

Rules the maintainer has confirmed are safe to approve and merge without asking.

<!-- BEGIN AUTO-APPROVE RULES -->
_None recorded yet._
<!-- END AUTO-APPROVE RULES -->

## Always ask rules

Rules the maintainer has confirmed must always be asked about, even if the
heuristics above would call them safe.

<!-- BEGIN ALWAYS-ASK RULES -->
_None recorded yet._
<!-- END ALWAYS-ASK RULES -->

## Decision log

Chronological record of maintainer answers, kept so the reasoning behind a rule is
not lost. Newest first. Each entry records the dependency, the update, the answer,
and the reasoning given.

<!-- BEGIN DECISION LOG -->
_None recorded yet._
<!-- END DECISION LOG -->

## Rule format

Add rules as list items under the relevant section, using the marker comments as
insertion points. Each rule states the matcher, the update types it covers, and the
reason:

```markdown
- `ghcr.io/example/app` — minor and patch: approve and merge. Leaf app, no
  persistent state, rollback is a tag revert. (2026-01-15)
- `helm release cert-manager` — all update types: always ask. Cluster-wide
  certificate issuance; a bad upgrade breaks every ingress. (2026-01-15)
```

When a rule proves durable for a package that updates frequently, propose moving it
into `renovate.json` as an `automerge: true` package rule (plus the matching path in
the `.github/workflows/renovate-auto-approve.yml` allowlist) so Renovate handles it
without a triage run.
