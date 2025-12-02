# Note: These outputs reference resources that will be created in main.tf
# This file defines the output structure for when the VM resources are implemented

output "vm_public_ip" {
  description = "Public IP address of the VM"
  value       = try(oci_core_instance.omni.public_ip, null)
}

output "vm_private_ip" {
  description = "Private IP address of the VM"
  value       = try(oci_core_instance.omni.private_ip, null)
}

output "instance_id" {
  description = "OCI instance OCID"
  value       = try(oci_core_instance.omni.id, null)
}

output "instance_ocid" {
  description = "Instance OCID for reference"
  value       = try(oci_core_instance.omni.id, null)
}
