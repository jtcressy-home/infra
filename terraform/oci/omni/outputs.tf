output "vm_public_ip" {
  description = "Public IP address of the VM instance"
  value       = oci_core_instance.omni.public_ip
}

output "vm_private_ip" {
  description = "Private IP address of the VM instance"
  value       = oci_core_instance.omni.private_ip
}

output "instance_id" {
  description = "OCID of the compute instance"
  value       = oci_core_instance.omni.id
}

output "instance_ocid" {
  description = "OCID of the compute instance (for reference)"
  value       = oci_core_instance.omni.id
}
