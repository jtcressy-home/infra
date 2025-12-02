# Terraform Infrastructure

This directory contains Terraform configurations for managing infrastructure resources in a GitOps workflow.

## Directory Structure

```
terraform/
└── oci/
    └── omni/          # OCI infrastructure for Omni VM
        ├── backend.tf              # Cloudflare R2 state backend configuration
        ├── variables.tf            # Input variable definitions
        ├── outputs.tf              # Output value definitions
        └── terraform.tfvars.example # Example variable values
```

## State Backend

The Terraform state is stored in **Cloudflare R2** using the S3-compatible backend:

- **Bucket**: `terraform-state`
- **Key Path**: `oci/omni/terraform.tfstate`
- **Endpoint**: `https://<CLOUDFLARE_ACCOUNT_ID>.r2.cloudflarestorage.com`

The backend configuration uses the S3 protocol with various AWS-specific validations disabled to work with Cloudflare R2.

## GitHub Actions Workflows (Primary Method)

The repository includes automated GitHub Actions workflows for Terraform operations. **This is the primary and recommended method** for managing infrastructure.

### Available Workflows

#### 1. Pull Request Validation (`terraform-pr.yml`)

Automatically runs on PRs that modify Terraform files:

```yaml
Triggers on:
  - terraform/oci/omni/**/*.tf
  - terraform/oci/omni/**/*.tfvars
  - terraform/oci/omni/**/terraform.lock.hcl
  - .github/workflows/terraform-*.yml
```

**Actions performed:**
- Terraform format check (`terraform fmt -check`)
- Terraform validation (`terraform validate`)
- Terraform plan with full output
- Posts plan summary as PR comment

**Required Secrets:**
- `CLOUDFLARE_R2_ACCESS_KEY_ID` - R2 access key for state backend
- `CLOUDFLARE_R2_SECRET_ACCESS_KEY` - R2 secret key for state backend
- All OCI credentials (see Variables section)

#### 2. Apply on Main (`terraform-apply.yml`)

Automatically applies changes when PRs are merged to `main`:

```yaml
Triggers on:
  - Push to main branch
  - Changes to terraform/oci/omni/**/*.tf files
```

**Actions performed:**
- Terraform init with R2 backend
- Terraform plan
- Terraform apply (auto-approved)
- Parse and report apply status
- Extract outputs (VM IPs, OCIDs)

#### 3. Drift Detection (`terraform-drift.yml`)

Periodically checks for configuration drift:

```yaml
Schedule: Daily at 6 AM UTC
```

**Actions performed:**
- Runs `terraform plan` to detect drift
- Creates GitHub issue if drift detected
- Reports drift summary

#### 4. Merge Queue Validation (`terraform-merge-queue.yml`)

Validates Terraform changes in GitHub merge queue:

```yaml
Triggers on:
  - merge_group event
```

Ensures changes pass validation before being merged to main.

### Using GitHub Actions

**Standard workflow:**

1. **Create a feature branch**:
   ```bash
   git checkout -b terraform/update-omni-config
   ```

2. **Make Terraform changes**:
   ```bash
   vim terraform/oci/omni/main.tf
   ```

3. **Commit and push**:
   ```bash
   git add terraform/
   git commit -m "feat(terraform): update Omni VM configuration"
   git push origin terraform/update-omni-config
   ```

4. **Create Pull Request**:
   - The `terraform-pr.yml` workflow runs automatically
   - Review the plan output in PR comments
   - Address any validation errors

5. **Merge PR**:
   - Once approved and checks pass, merge to `main`
   - The `terraform-apply.yml` workflow applies changes automatically

## Local Usage (Emergency/Testing Only)

Local Terraform operations should only be used for emergency situations or testing. The GitHub Actions workflows are the primary method.

### Prerequisites

1. **Terraform CLI** (>= 1.10.0):
   ```bash
   # macOS
   brew install terraform

   # Linux
   wget https://releases.hashicorp.com/terraform/1.10.0/terraform_1.10.0_linux_amd64.zip
   unzip terraform_*.zip
   sudo mv terraform /usr/local/bin/
   ```

2. **OCI CLI Configuration**:
   ```bash
   mkdir -p ~/.oci
   # Create ~/.oci/config with your credentials
   # Create ~/.oci/oci_api_key.pem with your API key
   ```

3. **Environment Variables**:
   ```bash
   # Required for R2 backend
   export AWS_ACCESS_KEY_ID="<cloudflare-r2-access-key>"
   export AWS_SECRET_ACCESS_KEY="<cloudflare-r2-secret-key>"

   # Required for Terraform variables (see variables.tf)
   export TF_VAR_oci_tenancy_ocid="ocid1.tenancy..."
   export TF_VAR_oci_user_ocid="ocid1.user..."
   export TF_VAR_oci_fingerprint="aa:bb:cc..."
   export TF_VAR_oci_region="us-ashburn-1"
   export TF_VAR_oci_compartment_ocid="ocid1.compartment..."
   export TF_VAR_oci_availability_domain="AD-1"
   export TF_VAR_ssh_public_key="ssh-ed25519 AAAA..."
   export TF_VAR_tailscale_authkey="tskey-auth-..."
   export TF_VAR_cloudflare_account_id="..."
   export TF_VAR_cloudflare_r2_access_key_id="..."
   export TF_VAR_cloudflare_r2_secret_access_key="..."
   ```

   Alternatively, create a `terraform.tfvars` file (copy from `terraform.tfvars.example`).

### Local Commands

```bash
# Navigate to the configuration directory
cd terraform/oci/omni

# Initialize Terraform (downloads providers, configures backend)
terraform init

# Format code
terraform fmt

# Validate configuration
terraform validate

# Plan changes (review what will be changed)
terraform plan

# Apply changes (requires confirmation)
terraform apply

# View outputs
terraform output

# View specific output
terraform output vm_public_ip

# Destroy resources (use with caution!)
terraform destroy
```

### Important Notes for Local Usage

- **State Locking**: R2 does not support state locking. Avoid running local operations while GitHub Actions workflows are running.
- **Credentials**: Never commit `terraform.tfvars` or any files containing credentials.
- **Testing**: Use `terraform plan` to verify changes before applying.
- **Emergency Use**: Only use local operations if GitHub Actions is unavailable.

## Required Secrets

All secrets must be configured in GitHub repository settings or Doppler (for GitHub Actions):

### OCI Credentials
- `OCI_TENANCY_OCID` - OCID of the OCI tenancy
- `OCI_USER_OCID` - OCID of the OCI user
- `OCI_FINGERPRINT` - API key fingerprint
- `OCI_REGION` - OCI region (e.g., `us-ashburn-1`)
- `OCI_COMPARTMENT_OCID` - OCID of the compartment
- `OCI_AVAILABILITY_DOMAIN` - Availability domain (e.g., `AD-1`)
- `OCI_PRIVATE_KEY` - Private API key (PEM format)

### SSH Access
- `SSH_PUBLIC_KEY` - SSH public key for VM access

### Tailscale
- `TAILSCALE_AUTHKEY` - Tailscale auth key for automatic node registration

### Cloudflare R2
- `CLOUDFLARE_ACCOUNT_ID` - Cloudflare account ID
- `CLOUDFLARE_R2_ACCESS_KEY_ID` - R2 access key ID
- `CLOUDFLARE_R2_SECRET_ACCESS_KEY` - R2 secret access key

## Variables

See `variables.tf` for detailed descriptions of all input variables.

Example values are provided in `terraform.tfvars.example`.

## Outputs

After a successful apply, the following outputs are available:

- `vm_public_ip` - Public IP address of the VM
- `vm_private_ip` - Private IP address of the VM
- `instance_id` - OCI instance OCID
- `instance_ocid` - OCI instance OCID (duplicate for reference)

Access outputs via:
```bash
terraform output vm_public_ip
```

Or via GitHub Actions workflow outputs in the apply job logs.

## Troubleshooting

### Backend Authentication Failures

If you see errors about R2 authentication:

```
Error: error configuring S3 Backend: error validating provider credentials
```

**Solution**: Ensure `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables are set correctly for R2 access.

### OCI Provider Authentication

If you see OCI authentication errors:

```
Error: Service error:NotAuthenticated
```

**Solution**:
- Verify OCI CLI configuration in `~/.oci/config`
- Ensure API key file permissions are `600`
- Verify all `TF_VAR_oci_*` variables are set correctly

### State Lock Errors

```
Error: Error acquiring the state lock
```

**Solution**: Cloudflare R2 does not support state locking. If a GitHub Actions workflow is running, wait for it to complete. If no workflows are running, this may indicate a previous run failed to release the lock (which shouldn't happen with R2, but can occur with local state).

### Format Validation Failures

```
Error: terraform fmt -check failed
```

**Solution**: Run `terraform fmt` to automatically format files, then commit the changes.

## References

- [Terraform S3 Backend Documentation](https://developer.hashicorp.com/terraform/language/settings/backends/s3)
- [Cloudflare R2 Documentation](https://developers.cloudflare.com/r2/)
- [OCI Terraform Provider](https://registry.terraform.io/providers/oracle/oci/latest/docs)
