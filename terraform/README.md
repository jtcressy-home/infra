# Terraform Infrastructure

This directory contains Terraform configurations for managing infrastructure components.

## Directory Structure

```
terraform/
└── oci/
    └── omni/          # OCI VM for Omni control plane
        ├── backend.tf          # Cloudflare R2 state backend
        ├── variables.tf        # Input variables
        ├── outputs.tf          # Output values
        └── terraform.tfvars.example  # Example variable values
```

## State Backend

This project uses **Cloudflare R2** as the Terraform state backend. The state is stored in an S3-compatible bucket configuration:

- **Bucket**: `terraform-state`
- **State Path**: `oci/omni/terraform.tfstate`
- **Endpoint**: Configured via `AWS_ENDPOINT_URL_S3` environment variable
- **Authentication**: Uses R2 access keys via `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`

## GitHub Actions Workflows (Primary Method)

The recommended way to run Terraform is through GitHub Actions workflows:

### Available Workflows

1. **terraform-pr.yml** - Runs on pull requests
   - Executes `terraform plan` to preview changes
   - Posts plan output as a PR comment
   - Validates Terraform configuration

2. **terraform-apply.yml** - Runs on main branch
   - Executes `terraform apply` to deploy changes
   - Runs automatically after merging PRs
   - Updates infrastructure to match configuration

3. **terraform-drift.yml** - Scheduled drift detection
   - Periodically checks for configuration drift
   - Alerts if actual infrastructure differs from code
   - Helps maintain infrastructure consistency

### Required GitHub Secrets

Configure these secrets in your repository settings:

#### OCI Authentication
- `TF_VAR_oci_tenancy_ocid` - OCI tenancy OCID
- `TF_VAR_oci_user_ocid` - OCI user OCID
- `TF_VAR_oci_private_key` - OCI API private key (PEM format)
- `TF_VAR_oci_fingerprint` - OCI API key fingerprint
- `TF_VAR_oci_compartment_ocid` - OCI compartment OCID
- `TF_VAR_oci_availability_domain` - OCI availability domain
- `TF_VAR_oci_region` - OCI region (optional, defaults to us-ashburn-1)

#### SSH Configuration
- `TF_VAR_ssh_public_key` - SSH public key for VM access

#### Tailscale Configuration
- `TF_VAR_tailscale_auth_key` - Tailscale authentication key

#### Cloudflare R2 Backend
- `AWS_ACCESS_KEY_ID` - R2 access key ID
- `AWS_SECRET_ACCESS_KEY` - R2 secret access key
- `AWS_ENDPOINT_URL_S3` - R2 endpoint URL (e.g., `https://<account-id>.r2.cloudflarestorage.com`)

### Workflow Usage

1. **Making Changes**:
   ```bash
   # Make your Terraform changes
   git checkout -b feature/my-change
   # Edit terraform files
   git add terraform/
   git commit -m "feat: add new resource"
   git push origin feature/my-change
   ```

2. **Review Plan**:
   - Open a pull request
   - GitHub Actions will automatically run `terraform plan`
   - Review the plan output in the PR comments

3. **Apply Changes**:
   - Merge the pull request
   - GitHub Actions will automatically run `terraform apply`
   - Monitor the workflow run for completion

## Local Development (Emergency/Testing Only)

For emergency situations or local testing, you can run Terraform locally:

### Prerequisites

1. Install Terraform >= 1.10.0
2. Install OCI CLI and configure credentials
3. Set up environment variables or create `terraform.tfvars`

### Environment Variables

Set these environment variables before running Terraform locally:

```bash
# OCI Authentication
export TF_VAR_oci_tenancy_ocid="ocid1.tenancy.oc1..example"
export TF_VAR_oci_user_ocid="ocid1.user.oc1..example"
export TF_VAR_oci_private_key="$(cat ~/.oci/oci_api_key.pem)"
export TF_VAR_oci_fingerprint="aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99"
export TF_VAR_oci_region="us-ashburn-1"
export TF_VAR_oci_compartment_ocid="ocid1.compartment.oc1..example"
export TF_VAR_oci_availability_domain="aBCD:US-ASHBURN-AD-1"

# SSH Configuration
export TF_VAR_ssh_public_key="$(cat ~/.ssh/id_rsa.pub)"

# Tailscale Configuration
export TF_VAR_tailscale_auth_key="tskey-auth-xxxxxxxxxxxxxxxxxxxxx"

# Cloudflare R2 Backend
export AWS_ACCESS_KEY_ID="your-r2-access-key"
export AWS_SECRET_ACCESS_KEY="your-r2-secret-key"
export AWS_ENDPOINT_URL_S3="https://<account-id>.r2.cloudflarestorage.com"
```

### Local Commands

```bash
# Navigate to the configuration directory
cd terraform/oci/omni

# Initialize Terraform
terraform init

# Validate configuration
terraform validate

# Preview changes
terraform plan

# Apply changes (use with caution)
terraform apply

# Show current state
terraform show

# List outputs
terraform output
```

### Alternative: Using terraform.tfvars

You can also create a `terraform.tfvars` file (DO NOT commit this file):

```bash
# Copy the example file
cp terraform.tfvars.example terraform.tfvars

# Edit with your actual values
nano terraform.tfvars

# Run Terraform (still need R2 env vars)
terraform plan
```

## Important Notes

1. **State File**: The state file is stored in Cloudflare R2 and contains sensitive information. Never commit state files to version control.

2. **Secrets Management**: All sensitive values are managed through GitHub secrets, not Doppler or other secret managers for this project.

3. **Concurrent Runs**: The state backend uses locking to prevent concurrent modifications. Do not run local Terraform while GitHub Actions workflows are running.

4. **R2 Access**: Ensure R2 credentials have appropriate permissions for the `terraform-state` bucket.

## Troubleshooting

### Backend Initialization Fails

If `terraform init` fails with backend errors:
- Verify R2 credentials are correct
- Check that `AWS_ENDPOINT_URL_S3` is properly set
- Ensure the `terraform-state` bucket exists in R2

### Authentication Errors

If you encounter OCI authentication errors:
- Verify all OCI credentials are correctly set
- Check that the private key is in PEM format
- Ensure the fingerprint matches the API key

### State Lock Errors

If you see state lock errors:
- Wait for any running GitHub Actions workflows to complete
- If stuck, check the R2 bucket for lock files and remove if stale
- Consider using `terraform force-unlock` (use with extreme caution)

## Security Considerations

1. **Private Keys**: OCI private keys are sensitive. Store them securely as GitHub secrets.
2. **State Access**: Limit access to the R2 bucket containing Terraform state.
3. **Local Development**: Avoid local development when possible. Use GitHub Actions workflows.
4. **Secrets Rotation**: Regularly rotate OCI API keys and R2 credentials.

## Contributing

When making changes to Terraform configurations:

1. Always open a pull request
2. Review the `terraform plan` output carefully
3. Ensure all tests pass before merging
4. Document any new variables or outputs
5. Update this README if adding new components
