terraform {
  required_version = ">= 1.10.0"

  backend "s3" {
    bucket = "terraform-state"
    key    = "oci/omni/terraform.tfstate"
    region = "auto"

    # Cloudflare R2 endpoint - must be provided via:
    # - TF_CLI_ARGS_init environment variable, or
    # - terraform init -backend-config
    # Cannot use variables here as backend config is evaluated before variables

    # R2 compatibility settings
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    use_path_style              = true
  }

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 6.0"
    }
  }
}
