# OpenClaw Config Authority

This overlay keeps the Git-owned base OpenClaw configuration in `openclaw.json`.
Kustomize renders it into the stable `openclaw-config` ConfigMap, and the
`OpenClawInstance` references that ConfigMap through `spec.config.configMapRef`.

The operator owns the generated runtime ConfigMap (`openclaw-gw-config`) and
adds gateway auth, control UI origins, metrics, proxy, and other derived
settings during reconcile. Do not edit the generated runtime ConfigMap in Git.

Do not add a Git-managed `OpenClawSelfConfig` scaffold here. SelfConfig requests
are runtime objects created by the agent and validated by the operator. Config
patches are intentionally not allowed while `configMapRef` is active because the
current operator writes SelfConfig config patches to `spec.config.raw`, and
`spec.config.raw` is ignored when `configMapRef` is set.
