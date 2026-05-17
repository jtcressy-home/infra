# Dograh Runbook

## Dograh Deployment Inputs

Dograh v1 runs from one ArgoCD-discovered `home/dograh/dograh` overlay in namespace `dograh`. Static credentials are stored in 1Password and delivered through ExternalSecrets; this runbook records field names and has-value status only.

### 1Password Field Contract

Dograh-owned item: `1Password item dograh` in vault `jtcressy-net-infra`.

| Field name | Status | Used by |
| --- | --- | --- |
| `POSTGRES_USER` | has value | App database username and init contract |
| `POSTGRES_PASS` | has value | App database credential and init contract |
| `POSTGRES_PASSWORD` | has value | Compatibility field retained on the item |
| `POSTGRES_SUPER_PASS` | has value | CNPG superuser mapping below, not `dograh-secret` |
| `VALKEY_PASSWORD` | has value | Valkey auth and `REDIS_URL` |
| `MINIO_ROOT_USER` | has value | MinIO root user and Dograh MinIO access key |
| `MINIO_ROOT_PASSWORD` | has value | MinIO root credential and Dograh MinIO secret key |
| `OSS_JWT_SECRET` | has value | Dograh OSS session signing |
| `ASTERISK_ARI_PASSWORD` | has value | Asterisk ARI and Dograh ARI provider configuration |
| `UNIFI_TALK_SIP_SERVER` | has value | Asterisk UniFi Talk registration |
| `UNIFI_TALK_SIP_USERNAME` | has value | Asterisk UniFi Talk registration |
| `UNIFI_TALK_SIP_PASSWORD` | has value | Asterisk UniFi Talk registration |
| `UNIFI_TALK_SIP_EXTENSION` | has value | Dograh inbound call assignment |
| `GEMINI_API_KEY` | has value; stored for future use, not wired into v1 runtime manifests | Future workflow work |

CNPG superuser mapping: `POSTGRES_SUPER_PASS -> dograh-db-superuser/password`. Plan 02 owns the Dograh-scoped `dograh-db-superuser` Secret, and Plan 04 consumes that key only from init-only database bootstrap.

### Shared Cloudflare R2 Source

Shared R2 credentials stay deduplicated in `cloudflare-r2-generic`; do not copy them into the Dograh item.

| Shared item | Field name | Status | Later use |
| --- | --- | --- | --- |
| `cloudflare-r2-generic` | `endpoint` | has value | R2 endpoint remoteRef |
| `cloudflare-r2-generic` | `access_key_id` | has value | R2 access key remoteRef |
| `cloudflare-r2-generic` | `secret_access_key` | has value | R2 secret key remoteRef |

Non-secret R2 targets:

```text
CNPG_R2_DESTINATION_PATH=s3://restic-backups/dograh/
MINIO_R2_TARGET=dograh-voice-audio
```

### Accepted Dograh Images

```text
DOGRAH_API_IMAGE=ghcr.io/dograh-hq/dograh-api:1.29.0@sha256:f338d55d56acad6e8ef4054aa8d0bc5d74884f3418bbe24d54235d2378a3fdbe
DOGRAH_UI_IMAGE=ghcr.io/dograh-hq/dograh-ui:1.29.0@sha256:54da6c9877dcdae1d0c37aa4c28a7ba1689dc44a484508f7b1c47b1f2c133deb
```
