# Network Outputs
output "vcn_id" {
  description = "OCID of the VCN"
  value       = module.network.vcn_id
}

output "subnet_id" {
  description = "OCID of the subnet"
  value       = module.network.subnet_id
}

output "internet_gateway_id" {
  description = "OCID of the internet gateway"
  value       = module.network.internet_gateway_id
}

output "vcn_cidr" {
  description = "CIDR block of the VCN"
  value       = module.network.vcn_cidr
}

output "subnet_cidr" {
  description = "CIDR block of the subnet"
  value       = module.network.subnet_cidr
}

# VM Outputs commented out until VM resources are created in issues #530-#531
# Uncomment when oci_core_instance.omni_vm resource is added

# output "vm_public_ip" {
#   description = "Public IP address of the VM"
#   value       = oci_core_instance.omni_vm.public_ip
# }

# output "vm_private_ip" {
#   description = "Private IP address of the VM"
#   value       = oci_core_instance.omni_vm.private_ip
# }

# output "instance_id" {
#   description = "OCI instance OCID"
#   value       = oci_core_instance.omni_vm.id
# }

# output "instance_ocid" {
#   description = "Instance OCID for reference"
#   value       = oci_core_instance.omni_vm.id
# }
