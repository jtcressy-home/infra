# OCI Provider Configuration
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

variable "oci_fingerprint" {
  description = "Fingerprint of the OCI API key"
  type        = string
  sensitive   = true
}

variable "oci_region" {
  description = "OCI region to deploy resources"
  type        = string
}

variable "oci_compartment_ocid" {
  description = "OCID of the OCI compartment for resources"
  type        = string
  sensitive   = true
}

variable "oci_availability_domain" {
  description = "Availability domain for the VM instance"
  type        = string
}

# SSH Configuration
variable "ssh_public_key" {
  description = "SSH public key for instance access"
  type        = string
  sensitive   = true
}

# Tailscale Configuration
variable "tailscale_authkey" {
  description = "Tailscale authentication key for automatic node registration"
  type        = string
  sensitive   = true
}

# Cloudflare R2 Backend Configuration
variable "cloudflare_account_id" {
  description = "Cloudflare account ID for R2 state backend"
  type        = string
  sensitive   = true
}

variable "cloudflare_r2_access_key_id" {
  description = "Cloudflare R2 access key ID for state backend"
  type        = string
  sensitive   = true
}

variable "cloudflare_r2_secret_access_key" {
  description = "Cloudflare R2 secret access key for state backend"
  type        = string
  sensitive   = true
}
