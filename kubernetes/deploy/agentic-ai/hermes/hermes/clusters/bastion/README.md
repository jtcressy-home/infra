# Hermes Agent Gateway

## Read-only Kubernetes access and persistent tools

The Hermes pod runs as the dedicated `hermes` ServiceAccount. A
ClusterRoleBinding grants that account only the built-in `view` ClusterRole so
`kubectl` can inspect resources covered by that role across all namespaces.
Kubernetes `view` excludes Secrets, does not permit writes or other mutations,
and does not grant unrestricted access to all cluster-scoped or RBAC resources;
do not broaden this binding to `cluster-admin` or add Secret access.

The main container puts `/opt/data/.local/bin` first in `PATH`, followed by the
image's Hermes directories and normal system paths. This makes PVC-persisted
tools such as `kubectl`, `gh`, and `codex` available by name after pod
replacement without hiding image-provided or system binaries.

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
- The main container carries only the explicit process-level environment needed
  by the image and runtime; application configuration remains in `.env`.

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
auth provider the dashboard fails to start at all.

We satisfy the gate with the bundled **self-hosted OIDC** provider
(`plugins/dashboard_auth/self_hosted`) against our own `tsidp`
(`kubernetes/deploy/system/tailscale/tsidp`, hostname `tsidp` →
`https://tsidp.tailnet-4d89.ts.net`) instead of the username/password
provider, since the dashboard is reachable at
`https://hermes.tailnet-4d89.ts.net` for anyone on the tailnet.
`externalsecret.yaml` wires the issuer (static — not a secret) plus
`HERMES_DASHBOARD_OIDC_CLIENT_ID` / `HERMES_DASHBOARD_OIDC_CLIENT_SECRET`
from 1Password. `HERMES_DASHBOARD_PUBLIC_URL` is set explicitly so the OAuth
callback is `https://hermes.tailnet-4d89.ts.net/auth/callback` regardless of
whether the Tailscale ingress forwards `X-Forwarded-*` headers.

tsidp only issues **confidential** clients — every client it registers
(via `/register` DCR or the `/clients` admin UI) gets a `client_secret` and
its `/token` endpoint always requires it (see `server/token.go`
`allowRelyingParty`); there is no public/PKCE-only client type. That lines
up with Hermes's self-hosted OIDC provider, which supports confidential
clients via `HERMES_DASHBOARD_OIDC_CLIENT_SECRET` (env-only for now —
[NousResearch/hermes-agent#55650] tracks file-based secret support for
systemd/Kubernetes-style secret mounts; irrelevant here since we already
render one `.env` from 1Password).

[NousResearch/hermes-agent#49567]: https://github.com/NousResearch/hermes-agent/issues/49567
[NousResearch/hermes-agent#55650]: https://github.com/NousResearch/hermes-agent/issues/55650

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
   invite it to the target guild, and store its token plus an API/model key
   and a generated `API_SERVER_KEY` (`openssl rand -hex 32`) in the `hermes`
   1Password item — see the repo-root PR description for the full checklist.
3. **Register the dashboard as a tsidp OIDC client** (do this from a device
   on the tailnet):
   1. Grant tsidp's `allow_dcr` app capability to the account that will run
      the registration. In the [Tailscale admin console ACL
      policy](https://login.tailscale.com/admin/acls/), add (or extend) a
      `grants` entry, scoping `src` to that account rather than `*`:
      ```hujson
      "grants": [
        {
          "src": ["autogroup:admin"],
          "dst": ["tag:tsidp"],
          "app": {
            "tailscale.com/cap/tsidp": [{"allow_dcr": true}],
          },
        },
      ],
      ```
   2. From that device, register the client via tsidp's Dynamic Client
      Registration endpoint (RFC 7591):
      ```bash
      curl -s -X POST https://tsidp.tailnet-4d89.ts.net/register \
        -H "Content-Type: application/json" \
        -d '{
          "client_name": "hermes-dashboard",
          "redirect_uris": ["https://hermes.tailnet-4d89.ts.net/auth/callback"],
          "token_endpoint_auth_method": "client_secret_basic",
          "grant_types": ["authorization_code", "refresh_token"],
          "response_types": ["code"],
          "scope": "openid profile email"
        }'
      ```
      The response is a JSON object with `client_id` and `client_secret` —
      tsidp only issues confidential clients, so both fields are present.
   3. Immediately copy `client_id` / `client_secret` into the `hermes`
      1Password item as `HERMES_DASHBOARD_OIDC_CLIENT_ID` /
      `HERMES_DASHBOARD_OIDC_CLIENT_SECRET`, then discard the response —
      the secret is shown once and tsidp cannot re-display it later
      (deleting and re-registering the client is the only recovery path).
   4. Revoke the `allow_dcr` grant afterward if it was added just for this
      one-time registration.

## PVC backups (VolSync)

`volsync.yaml` backs up the `hermes-data` PVC nightly (02:15) via a restic
`ReplicationSource` to the shared R2 restic repository (1Password item
`volsync-restic-template`), retaining 7 daily + 4 weekly snapshots. The
repository suffix is `hermes-data` to keep it separate from the CNPG barman
backups already stored under the `hermes/` prefix.

Restore procedure (the live PVC predates VolSync, so it has no
`dataSourceRef` bootstrap — restores are manual):

1. Scale the `hermes` deployment to 0.
2. Create a `ReplicationDestination` with `trigger.manual`, pointing at
   `hermes-restic-secret` (see the metamcp overlay's `persistence.yaml` for
   the shape).
3. Recreate the PVC with `dataSourceRef` referencing that
   `ReplicationDestination`, or copy the restored snapshot's contents onto a
   fresh PVC.
4. Scale the deployment back up.
