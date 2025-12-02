terraform {
  required_version = ">= 1.10.0"

  backend "s3" {
    bucket = "terraform-state"
    key    = "oci/omni/terraform.tfstate"
    region = "auto"

    # Endpoint configured via TF_S3_ENDPOINT environment variable in CI/CD
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
