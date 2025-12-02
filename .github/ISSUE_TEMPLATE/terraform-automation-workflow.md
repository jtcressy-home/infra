---
name: Terraform Automation Workflow
about: Create GitHub Actions workflow for Terraform automation with drift detection
title: 'Create GitHub Actions workflow for Terraform automation with drift detection'
labels: enhancement, automation, terraform
assignees: ''
milestone: Deploy Omni self-hosted
---

## Overview
Implement a comprehensive GitHub Actions workflow for Terraform automation to enable continuous reconciliation similar to Kubernetes GitOps patterns. This is a prerequisite for deploying Omni self-hosted infrastructure (Epic #527).

## Requirements

### 1. Pull Request Validation
- **Trigger**: On pull request to main branch
- **Condition**: Only run if Terraform files (`*.tf`, `*.tfvars`, `terraform.lock.hcl`) have changed
- **Actions**:
  - Run `terraform fmt -check` to validate formatting
  - Run `terraform validate` to check configuration validity
  - Run `terraform plan` and post results as PR comment
  - Save plan artifact for potential apply

### 2. Merge Queue/Train Validation
- **Trigger**: On merge queue/train
- **Purpose**: Validate that the merged result doesn't cause plan failures
- **Actions**:
  - Run `terraform plan` on the merged code
  - If plan fails, deny and remove PR from merge queue
  - Ensure no conflicts or drift issues after merge

### 3. Main Branch Apply
- **Trigger**: Push to main branch
- **Condition**: Only run if Terraform files have changed
- **Actions**:
  - Run `terraform plan` to verify current state
  - Run `terraform apply -auto-approve` to apply changes
  - Post summary of applied changes

### 4. Drift Detection (Cron)
- **Trigger**: Scheduled cron job (e.g., every 6 hours)
- **Actions**:
  - Run `terraform plan` to detect drift
  - If drift detected, create an issue or PR comment with details
  - Optionally auto-apply to reconcile drift (configurable)
  - Run `terraform apply -auto-approve` if drift reconciliation is enabled

## Technical Specifications

### Secrets and Configuration
All Terraform workflows will need:
- **OCI credentials**: Via Doppler or GitHub Secrets
  - `OCI_TENANCY_OCID`
  - `OCI_USER_OCID`
  - `OCI_FINGERPRINT`
  - `OCI_PRIVATE_KEY`
- **Cloudflare R2 credentials**: For Terraform state backend
  - `R2_ACCOUNT_ID`
  - `R2_ACCESS_KEY_ID`
  - `R2_SECRET_ACCESS_KEY`
- **Doppler token**: For retrieving secrets
  - `DOPPLER_TOKEN` (with access to omni project/config)

### Workflow Structure
```yaml
.github/workflows/
├── terraform-pr.yml          # PR validation and planning
├── terraform-merge-queue.yml # Merge queue validation
├── terraform-apply.yml       # Main branch apply
└── terraform-drift.yml       # Cron-based drift detection
```

### Terraform Working Directory
- **Location**: `terraform/omni/` (to be created in Phase 1)
- **Backend**: Cloudflare R2 with state locking
- **Provider**: OCI (Oracle Cloud Infrastructure)

### Job Permissions
Each workflow needs appropriate permissions:
```yaml
permissions:
  id-token: write      # For OIDC if used
  contents: read       # Read repository
  pull-requests: write # Post PR comments
  issues: write        # Create drift issues
```

### Integration Points

#### Task Integration
Create `task omni:*` commands in `.taskfiles/omni/Taskfile.yaml`:
- `task omni:plan` - Run terraform plan locally
- `task omni:apply` - Run terraform apply locally
- `task omni:fmt` - Format terraform files
- `task omni:validate` - Validate terraform configuration
- `task omni:drift` - Check for drift

#### PR Comment Format
Use existing pattern from `argocd-diff.yml`:
- Post plan output as PR comment using `mshick/add-pr-comment@v2`
- Use `message-id` for updating same comment
- Format output with code blocks for readability

#### Drift Detection Behavior
When drift is detected:
1. Create detailed comment/issue with drift summary
2. Include which resources have drifted
3. Provide command to manually reconcile if auto-apply is disabled
4. If auto-apply enabled, apply changes and post summary

### Path Filters
Use `paths` filter to only trigger on Terraform changes:
```yaml
on:
  pull_request:
    paths:
      - 'terraform/omni/**/*.tf'
      - 'terraform/omni/**/*.tfvars'
      - 'terraform/omni/**/terraform.lock.hcl'
      - '.github/workflows/terraform-*.yml'
```

### Terraform Version
- Use `hashicorp/setup-terraform@v3` action
- Pin to specific version (e.g., 1.10.x)
- Consider Renovate automation for version updates

## Success Criteria
- [ ] Never need to run terraform from laptop for omni deployment
- [ ] PRs automatically run `terraform plan` when TF files change
- [ ] Merge queue validates merged result doesn't break plan
- [ ] Main branch automatically applies terraform changes
- [ ] Cron job detects and reports/fixes drift every 6 hours
- [ ] All terraform operations available via `task omni:*` commands
- [ ] Secrets properly managed via Doppler or GitHub Secrets
- [ ] Plan outputs posted as PR comments for review

## Implementation Notes
- Start with PR and Apply workflows (most critical)
- Add merge queue support if repository enables merge queue feature
- Drift detection can be implemented last
- Consider using Terraform Cloud/Spacelift as future enhancement
- Follow patterns from existing `argocd-diff.yml` workflow

## Related Issues
- Epic #527 - Deploy Omni self-hosted on OCI Always Free Tier
