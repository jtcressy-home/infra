# Hermes Agent Gateway

## The `/opt/data/.env` footgun and its resolution

Hermes reads runtime config, secrets, and feature flags from `/opt/data/.env`
on first boot. Whether a value baked into that file or one injected as a
container environment variable wins is version/code-path dependent upstream
and unsafe to rely on, so this overlay eliminates the ambiguity outright:
**there is exactly one source of truth**.

- The `hermes` ExternalSecret (`external-secrets.io`, 1Password backend) pulls
  every field from the `hermes` 1Password item and renders them, plus all
  non-secret config, into a single Secret key: `hermes-env`'s `.env`.
- A root `seed-env` initContainer copies that key to `/opt/data/.env`
  (`chown 10000:10000`, `chmod 600`) on every pod boot, before the gateway
  container starts.
- The main container carries no conflicting env besides `HERMES_UID`.

Because the `.env` is rebuilt from 1Password on every restart, GitOps/ESO
stays authoritative and a stale value written directly to the PVC can never
silently persist or drift.

## Root-boot, drop-to-10000 privilege model

The upstream image boots as root: s6-overlay's `/init` runs privileged to fix
`/opt/data` ownership, then drops the supervised gateway process to UID
10000 via `s6-setuidgid`. Do **not** set `runAsNonRoot`/`runAsUser` on the pod
or main container — either would break the chown phase and the gateway would
never start. `fsGroup: 10000` aligns PVC ownership with the drop-down user.
`HERMES_ALLOW_ROOT_GATEWAY` is deliberately left unset so the gateway process
itself still refuses to run as root; only `/init` is privileged.

## Dashboard auth

The container's `HERMES_DASHBOARD=1` entrypoint always passes `--host
0.0.0.0` to `hermes dashboard`, and upstream refuses to bind a non-loopback
dashboard unless an auth provider is registered ("Refusing to bind dashboard
to 0.0.0.0 — the OAuth auth gate engages on non-loopback binds, but no auth
providers are registered", [NousResearch/hermes-agent#49567]). Without an
auth provider the dashboard fails to start at all, so `externalsecret.yaml`
wires `HERMES_DASHBOARD_BASIC_AUTH_USERNAME`/`_PASSWORD` from 1Password to
satisfy the gate. Add both fields to the `hermes` 1Password item (see
bootstrap checklist below) before relying on the ingress.

[NousResearch/hermes-agent#49567]: https://github.com/NousResearch/hermes-agent/issues/49567

## Camofox — not yet deployed

`camofox.yaml` is written but deliberately left out of `kustomization.yaml`'s
`resources`. It points at `ghcr.io/jtcressy-home/camofox:latest`, which does
not exist yet (confirmed: GHCR returns 403) and is blocked on
`jtcressy-home/containers` PR #3 merging and publishing the image. Once that
image is published, pin it to a real tag+digest and add `camofox.yaml` back
to `kustomization.yaml`'s `resources`; until then the gateway runs without
browser tooling.

## Unverified / to confirm after first rollout

- **Discord allowlisting.** Only `DISCORD_BOT_TOKEN` is wired through ESO.
  Upstream also supports `DISCORD_ALLOWED_USERS` / `DISCORD_ALLOWED_ROLES` /
  `DISCORD_ALLOWED_CHANNELS` — set at least one before exposing the bot in a
  shared server, otherwise it may respond to every user it can see.

## One-time manual bootstrap (after first successful rollout)

1. `kubectl exec -n hermes deploy/hermes -it -- hermes auth add openai-codex`
   and complete the OAuth device/login flow. The refresh token lands on the
   `hermes-data` PVC (not the `.env`), so it survives restarts and is never
   overwritten by the ESO reseed.
2. Create the Discord bot application, enable the required gateway intents,
   invite it to the target guild, and store its token plus an API/model key,
   a generated `API_SERVER_KEY` (`openssl rand -hex 32`), and a
   `HERMES_DASHBOARD_BASIC_AUTH_USERNAME`/`_PASSWORD` pair in the `hermes`
   1Password item — see the repo-root PR description for the full checklist.
