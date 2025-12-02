terraform {
  backend "s3" {
    bucket = "terraform-state"
    key    = "oci/omni/terraform.tfstate"
    region = "auto"

    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_s3_checksum            = true
    use_path_style              = true

    endpoints = {
      s3 = "https://${var.cloudflare_account_id}.r2.cloudflarestorage.com"
    }
  }

  required_version = ">= 1.10.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 6.0"
    }
  }
}
