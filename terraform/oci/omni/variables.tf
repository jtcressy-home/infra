# OCI Provider Authentication
variable "oci_tenancy_ocid" {
  description = "OCID of the OCI tenancy"
  type        = string
  sensitive   = true
}

variable "oci_user_ocid" {
  description = "OCID of the OCI user"
  type        = string
  sensitive   = true
}

variable "oci_private_key" {
  description = "OCI API private key (PEM format)"
  type        = string
  sensitive   = true
}

variable "oci_fingerprint" {
  description = "Fingerprint of the OCI API key"
  type        = string
  sensitive   = true
}

variable "oci_region" {
  description = "OCI region for resources"
  type        = string
  default     = "us-ashburn-1"
}

# OCI Compute Configuration
variable "oci_compartment_ocid" {
  description = "OCID of the OCI compartment"
  type        = string
  sensitive   = true
}

variable "oci_availability_domain" {
  description = "OCI availability domain for VM placement"
  type        = string
}

# SSH Configuration
variable "ssh_public_key" {
  description = "SSH public key for VM access"
  type        = string
  sensitive   = true
}

# Tailscale Configuration
variable "tailscale_auth_key" {
  description = "Tailscale authentication key for automatic node registration"
  type        = string
  sensitive   = true
}

# Cloudflare R2 Backend Configuration
# These are used by the backend configuration and should be set as environment variables:
# - AWS_ACCESS_KEY_ID (R2 access key)
# - AWS_SECRET_ACCESS_KEY (R2 secret key)
# - AWS_ENDPOINT_URL_S3 (R2 endpoint URL)
