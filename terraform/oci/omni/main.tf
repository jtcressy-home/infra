# Configure OCI Provider
provider "oci" {
  tenancy_ocid = var.oci_tenancy_ocid
  user_ocid    = var.oci_user_ocid
  private_key  = var.oci_private_key
  fingerprint  = var.oci_fingerprint
  region       = var.oci_region
}

# Network Module - VCN, Subnet, Internet Gateway, Route Tables, Security Lists
module "network" {
  source = "./modules/network"

  compartment_id      = var.oci_compartment_ocid
  vcn_cidr            = "192.168.120.0/24"
  subnet_cidr         = "192.168.120.0/25"
  vcn_display_name    = "omni-vcn"
  subnet_display_name = "omni-subnet"
  enable_dns          = true
}
