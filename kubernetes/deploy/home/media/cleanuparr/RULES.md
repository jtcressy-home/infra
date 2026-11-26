# Cleanuparr rules (C7)

Dry run is a post-deploy UI setting. GitOps does not turn it on.

2.10.12 stores `GeneralConfig.DryRun` in SQLite on the `cleanuparr` PVC. The property defaults to false. After the first login, set **Settings → General → Enable Dry Run** before any strike or block rule is saved. Live enforcement (`dry_run=0`) is configured in the app after that validation, not in git.

Downloads mount only. PVC `purplebox-nfs-media` is mounted at `/media/downloads/nzbs` with `subPath: downloads/nzbs`, read-write, so Orphaned Files Cleaner and Malware Blocker can delete files. No library path is mounted (`/media/movies`, `/media/tv`, or any other subPath).

The process is uid 568 and gid 568 (`runAsUser` / `runAsGroup`), the same owner SABnzbd uses for completed job dirs (directories 775, files 664). `supplementalGroups: [568]` repeats that group. Group 65536 is not added: Sonarr and Lidarr mount this NFS export as uid/gid 568 without it, and nothing in git shows the export is owned by 65536. `fsGroup: 568` stays the existing config-PVC setting. Do not add an fsGroup for the share.

`cleanuparr-secret` keeps `CLEANUPARR_ADMIN_USER` and `CLEANUPARR_ADMIN_PASS` from item `cleanuparr` (`username` / `password`). The same Owner ExternalSecret maps item `grokbot-doyle-webhooks` (vault `jtcressy-net-infra`, section `CLEANUPARR`): `DOYLE_WEBHOOK_URL` from field `cleanuparr_url`, and `DOYLE_WEBHOOK_KEY` from field `cleanuparr_key`. The secret stays unmounted. 2.10.12 does not read it.

*arr API keys are typed into the UI. `cleanuparr-arr-secret` only copies the existing 1Password keys for CASE.

Usenet malware blocklist. `clusters/bastion/blocklist/usenet-malware.txt` is the list, one pattern per line, with a trailing newline. Kustomize generates ConfigMap `cleanuparr-blocklist` from that file and name-references it on the Cleanuparr pod. The ConfigMap is mounted read-only at `/blocklists` (directory mount, no subPath), so the file is `/blocklists/usenet-malware.txt`. Cleanuparr reloads that file every 5 minutes. Edit the file and sync. The ConfigMap name hash changes with the file, and kustomize updates the volume reference.
