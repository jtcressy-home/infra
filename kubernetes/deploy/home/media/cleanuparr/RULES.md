# Cleanuparr rules (C7)

Dry run is a post-deploy UI setting. GitOps does not turn it on.

2.10.12 stores `GeneralConfig.DryRun` in SQLite on the `cleanuparr` PVC. The property defaults to false. After the first login, set **Settings → General → Enable Dry Run** before any strike or block rule is saved.

CASE and DOYLE fill the live rules in the Cleanuparr UI after that. Do not enable auto-remove from this repository.

No media library mount in v1. *arr API keys are typed into the UI. `cleanuparr-arr-secret` only copies the existing 1Password keys for CASE.
