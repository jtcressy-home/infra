# OCI Provider Configuration
variable "oci_tenancy_ocid" {
  description = "OCI Tenancy OCID"
  type        = string
  sensitive   = true
}

variable "oci_user_ocid" {
  description = "OCI User OCID"
  type        = string
  sensitive   = true
}

variable "oci_fingerprint" {
  description = "OCI API Key Fingerprint"
  type        = string
  sensitive   = true
}

variable "oci_private_key" {
  description = "OCI API Private Key (PEM format)"
  type        = string
  sensitive   = true
}

variable "oci_region" {
  description = "OCI Region"
  type        = string
  default     = "us-phoenix-1"
}

variable "oci_compartment_id" {
  description = "OCI Compartment OCID for resource deployment"
  type        = string
  sensitive   = true
}

variable "oci_availability_domain" {
  description = "OCI Availability Domain"
  type        = string
}

# SSH Configuration
variable "ssh_public_key" {
  description = "SSH public key for VM access"
  type        = string
}

# Tailscale Configuration
variable "tailscale_auth_key" {
  description = "Tailscale authentication key for automatic node registration"
  type        = string
  sensitive   = true
}

# Cloudflare R2 Backend Configuration
variable "cloudflare_account_id" {
  description = "Cloudflare Account ID for R2 storage"
  type        = string
  sensitive   = true
}

variable "cloudflare_r2_access_key_id" {
  description = "Cloudflare R2 Access Key ID"
  type        = string
  sensitive   = true
}

variable "cloudflare_r2_secret_access_key" {
  description = "Cloudflare R2 Secret Access Key"
  type        = string
  sensitive   = true
}
