# Terraform Infrastructure

This directory contains Terraform configurations for managing infrastructure components.

## Directory Structure

```
terraform/
└── oci/
    └── omni/          # OCI VM for Omni SaaS-managed Talos cluster
```

## Terraform Operations via GitHub Actions (Primary Method)

All Terraform operations should be performed through GitHub Actions workflows. This ensures:
- Consistent execution environment
- Proper secret management via GitHub Secrets
- Audit trail of infrastructure changes
- State locking and safety checks

### Available Workflows

1. **Terraform Plan on Pull Request** (`terraform-pr.yml`)
   - Automatically runs on PRs that modify Terraform files
   - Posts plan output as PR comment
   - Validates syntax and configuration

2. **Terraform Apply** (`terraform-apply.yml`)
   - Manually triggered workflow
   - Applies Terraform changes after review
   - Updates infrastructure state

3. **Terraform Drift Detection** (`terraform-drift.yml`)
   - Scheduled periodic checks
   - Detects configuration drift
   - Creates issues when drift is detected

### Using the Workflows

#### Running Terraform Plan
Plans are automatically generated when you open a PR with Terraform changes:

1. Make changes to Terraform files
2. Commit and push to a feature branch
3. Open a pull request
4. Review the plan output in the PR comments

#### Applying Changes
After PR approval and merge:

1. Go to Actions → Terraform Apply workflow
2. Click "Run workflow"
3. Select the terraform directory (e.g., `oci/omni`)
4. Confirm execution

The workflow will:
- Initialize Terraform with R2 backend
- Apply the configuration
- Output results including VM IPs and OCIDs

## Required GitHub Secrets

Configure these secrets in your GitHub repository settings (Settings → Secrets and variables → Actions):

### OCI Credentials
- `TF_VAR_oci_tenancy_ocid` - OCI Tenancy OCID
- `TF_VAR_oci_user_ocid` - OCI User OCID
- `TF_VAR_oci_fingerprint` - OCI API Key Fingerprint
- `TF_VAR_oci_private_key` - OCI API Private Key (PEM format)
- `TF_VAR_oci_compartment_id` - OCI Compartment OCID
- `TF_VAR_oci_availability_domain` - OCI Availability Domain
- `TF_VAR_oci_region` - OCI Region (default: us-phoenix-1)

### SSH Configuration
- `TF_VAR_ssh_public_key` - SSH public key for VM access

### Tailscale Configuration
- `TF_VAR_tailscale_auth_key` - Tailscale auth key for node registration

### Cloudflare R2 Backend
- `TF_VAR_cloudflare_account_id` - Cloudflare Account ID
- `AWS_ACCESS_KEY_ID` - R2 Access Key ID (S3-compatible)
- `AWS_SECRET_ACCESS_KEY` - R2 Secret Access Key (S3-compatible)

## State Backend Configuration

Terraform state is stored in Cloudflare R2 (S3-compatible storage):

- **Bucket**: `terraform-state`
- **State file**: `oci/omni/terraform.tfstate`
- **Endpoint**: `https://<CLOUDFLARE_ACCOUNT_ID>.r2.cloudflarestorage.com`

The backend is configured to skip AWS-specific validations for R2 compatibility.

### Backend Initialization

The backend endpoint must be provided during `terraform init`:

```bash
terraform init \
  -backend-config="endpoint=https://${CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com" \
  -backend-config="access_key=${AWS_ACCESS_KEY_ID}" \
  -backend-config="secret_key=${AWS_SECRET_ACCESS_KEY}"
```

GitHub Actions workflows handle this automatically using repository secrets.

## Local Development (Emergency/Testing Only)

Local Terraform execution should only be used for testing or emergency situations. Production changes should go through GitHub Actions.

### Prerequisites

1. Install Terraform >= 1.10.0
2. Install OCI CLI and configure credentials
3. Set up Cloudflare R2 access

### Setup

1. Copy the example tfvars file:
   ```bash
   cd terraform/oci/omni
   cp terraform.tfvars.example terraform.tfvars
   ```

2. Edit `terraform.tfvars` with your actual values

3. Export R2 credentials:
   ```bash
   export AWS_ACCESS_KEY_ID="your-r2-access-key-id"
   export AWS_SECRET_ACCESS_KEY="your-r2-secret-access-key"
   export CLOUDFLARE_ACCOUNT_ID="your-cloudflare-account-id"
   ```

4. Initialize Terraform:
   ```bash
   terraform init \
     -backend-config="endpoint=https://${CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com" \
     -backend-config="access_key=${AWS_ACCESS_KEY_ID}" \
     -backend-config="secret_key=${AWS_SECRET_ACCESS_KEY}"
   ```

### Running Terraform Locally

```bash
# Plan changes
terraform plan

# Apply changes
terraform apply

# Show current state
terraform show

# Destroy resources (use with extreme caution!)
terraform destroy
```

## Outputs

After applying the configuration, the following outputs are available:

- `vm_public_ip` - Public IP address of the VM
- `vm_private_ip` - Private IP address of the VM
- `instance_id` - OCI instance OCID
- `instance_ocid` - Instance OCID for reference

View outputs:
```bash
terraform output
```

Or via GitHub Actions workflow output in the workflow run logs.

## Security Best Practices

1. **Never commit sensitive values**
   - Use GitHub Secrets for all credentials
   - The `.tfvars` file is gitignored
   - Never commit actual keys or tokens

2. **Use GitHub Actions for production**
   - Centralized secret management
   - Audit trail of changes
   - Consistent execution environment

3. **Review plans before applying**
   - Always review the plan output in PR comments
   - Understand what resources will be created/modified/destroyed
   - Get peer review for significant changes

4. **State file security**
   - State is stored in private R2 bucket
   - Access controlled via R2 API tokens
   - State contains sensitive information - protect access

## Troubleshooting

### Backend Initialization Fails

**Problem**: `terraform init` fails with authentication errors

**Solution**: Verify R2 credentials are correctly set:
```bash
# Check environment variables
echo $AWS_ACCESS_KEY_ID
echo $CLOUDFLARE_ACCOUNT_ID

# Verify R2 bucket exists
# Check Cloudflare dashboard → R2 → terraform-state bucket
```

### OCI Provider Authentication Fails

**Problem**: Terraform can't authenticate to OCI

**Solution**: Verify OCI credentials:
- Check OCID format (should start with `ocid1.`)
- Verify fingerprint matches the API key
- Ensure private key is in PEM format with proper line breaks
- Test with OCI CLI: `oci iam region list`

### State Lock Errors

**Problem**: State is locked from a previous operation

**Solution**:
- Wait for the current operation to complete
- If stuck, check GitHub Actions for running workflows
- Force unlock only as last resort: `terraform force-unlock <LOCK_ID>`

### Plan Shows Unexpected Changes

**Problem**: Terraform detects drift or unexpected changes

**Solution**:
- Check for manual changes made outside Terraform
- Review the drift detection issues
- Compare with previous state: `terraform show`
- May need to import existing resources or update configuration

## Additional Resources

- [Terraform Documentation](https://www.terraform.io/docs)
- [OCI Terraform Provider](https://registry.terraform.io/providers/oracle/oci/latest/docs)
- [Cloudflare R2 Documentation](https://developers.cloudflare.com/r2/)
- [GitHub Actions Terraform Workflows](/.github/workflows/)
