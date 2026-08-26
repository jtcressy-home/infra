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
- Leaf applications — patch, minor and digest: approve and merge. Failure is
  contained to the app, rollback is a tag/version revert. Covers `kagent` and
  `kagent-crds`, the `ark-*` charts, `tobiasehlert/teslamateapi`, the metamcp
  sidecar digests (`ghcr.io/jtcressy/bluepopcorn-mcp`,
  `ghcr.io/belphemur/obsidian-headless-sync-docker`), `ghcr.io/bastienwirtz/homer`
  and the searxng valkey image. Majors of these are still asked about. (2026-08-26)
- GitHub Actions and CI tooling — all update types including major: approve and
  merge. Blast radius is CI only and every workflow change is exercised by the
  `argocd-diff` / Terraform checks on the PR itself. Exception: the `helm` binary
  version used by workflows on a major bump — see always-ask. (2026-08-26)
- Go toolchain directive (`go.mod` `toolchain`, `golang` image tag) — minor and
  patch: approve and merge. Build-time only. (2026-08-26)
- `helm release cert-manager`, `helm release external-secrets`,
  `helm release external-dns`, `helm release spegel` — patch and minor: approve
  and merge. Maintainer classified these as low risk to upgrade in place.
  (2026-08-26)
<!-- END AUTO-APPROVE RULES -->

## Always ask rules

Rules the maintainer has confirmed must always be asked about, even if the
heuristics above would call them safe.

<!-- BEGIN ALWAYS-ASK RULES -->
- `siderolabs/talos` — all update types: always ask. Governs the machines
  themselves and requires a reboot, so it needs planning *and* scheduling.
  (2026-08-26)
- `siderolabs/kubelet` / Kubernetes version — all update types: always ask. Part
  of a Kubernetes upgrade, which is planned as a unit. (2026-08-26)
- `helm release cilium`, `helm release multus`,
  `ghcr.io/k8snetworkplumbingwg/multus-cni` — all update types: always ask.
  Cluster-wide networking; multus is gated together with cilium. (2026-08-26)
- `helm` binary version in workflows — major: always ask. Helm majors change chart
  rendering, which silently changes what `argocd-diff` compares. (2026-08-26)
- `helm release app-template` (bjw-s) — all update types: always ask, default to
  closing. Legacy in this repo per `AGENTS.md`; existing usages get migrated off
  rather than upgraded. (2026-08-26)
<!-- END ALWAYS-ASK RULES -->

## Decision log

Chronological record of maintainer answers, kept so the reasoning behind a rule is
not lost. Newest first. Each entry records the dependency, the update, the answer,
and the reasoning given.

<!-- BEGIN DECISION LOG -->
- **2026-08-26 — bjw-s `app-template` v4.6.2 → v5.1.0 (#742).** Close it. The
  chart is legacy in this repo and the ArgoCD diff check fails on the bump.
- **2026-08-26 — Envoy Gateway `gateway-helm` v1.8.1 → 1.9.0 (#876).** Left open,
  no decision. The ArgoCD render check fails on this bump, and it is the
  cluster's Gateway API control plane, so it is not merged while red.
- **2026-08-26 — Stateful leaf-app updates (postgres, teslamate, n8n, valkey,
  ark).** Joel: "if you think the updates are safe with monitoring, merge them and
  spin off follow up sessions to monitor their state through argocd." In-major
  bumps are therefore approved with post-merge ArgoCD monitoring; majors that
  imply a data migration (`postgresql` 17 → 18, `teslamate` 3 → 4, bitnami
  `valkey` chart 5 → 6, n8n's 2.13 → 2.37 jump) still get asked about.
- **2026-08-26 — Cluster platform components.** Joel: external-dns, spegel,
  cert-manager and external-secrets are low risk and can be auto-approved.
  kubelet is part of a Kubernetes upgrade and needs planning; cilium affects all
  networking and needs planning; talos governs the machines themselves, requires a
  reboot, and needs planning *and* scheduling. multus is "just as risky as cilium"
  and shares that gate.
- **2026-08-26 — GitHub Actions / CI tooling bumps.** Joel approved a standing
  auto-approve rule for CI action bumps including majors, because failures surface
  in the PR's own checks. `helm` v3 → v4 was excluded as it changes chart
  rendering in `argocd-diff`.
- **2026-08-26 — Leaf-app patch/minor/digest bumps.** Joel chose the standing
  auto-approve rule *plus* `automerge: true` in `renovate.json` for the
  frequently-updating ones (kagent, teslamateapi, metamcp sidecar digests) so they
  no longer need a triage run at all.
- **2026-08-26 — Merging.** The triage agent can approve but cannot merge into
  `main`; merges are left to the maintainer or to Renovate automerge. Prefer
  encoding durable rules as `automerge: true` package rules for this reason.
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
