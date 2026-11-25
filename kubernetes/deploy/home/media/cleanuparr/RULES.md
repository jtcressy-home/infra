# Cleanuparr rules (C7)

Dry run is a post-deploy UI setting. GitOps does not turn it on.

2.10.12 stores `GeneralConfig.DryRun` in SQLite on the `cleanuparr` PVC. The property defaults to false. After the first login, set **Settings → General → Enable Dry Run** before any strike or block rule is saved. Live enforcement (`dry_run=0`) is configured in the app after that validation, not in git.

Downloads mount only. PVC `purplebox-nfs-media` is mounted at `/media/downloads/nzbs` with `subPath: downloads/nzbs`, read-write, so Orphaned Files Cleaner and Malware Blocker can delete files. No library path is mounted (`/media/movies`, `/media/tv`, or any other subPath).

The process is uid 568 and gid 568 (`runAsUser` / `runAsGroup`), the same owner SABnzbd uses for completed job dirs (directories 775, files 664). `supplementalGroups: [568]` repeats that group. Group 65536 is not added: Sonarr and Lidarr mount this NFS export as uid/gid 568 without it, and nothing in git shows the export is owned by 65536. `fsGroup: 568` stays the existing config-PVC setting. Do not add an fsGroup for the share.

`cleanuparr-secret` keeps `CLEANUPARR_ADMIN_USER` and `CLEANUPARR_ADMIN_PASS` from item `cleanuparr` (`username` / `password`). Item `DOYLE_WEBHOOK_URL` is extracted in that same ExternalSecret with key prefix `DOYLE_WEBHOOK_URL_`, because its field labels are not verified (Joel: a URL and a key). There is no single key named `DOYLE_WEBHOOK_URL`; pinning a label would fail the admin sync if the label is wrong. The secret stays unmounted. 2.10.12 does not read it.

*arr API keys are typed into the UI. `cleanuparr-arr-secret` only copies the existing 1Password keys for CASE.
