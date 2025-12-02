output "vcn_id" {
  description = "OCID of the VCN"
  value       = oci_core_vcn.vcn.id
}

output "subnet_id" {
  description = "OCID of the subnet"
  value       = oci_core_subnet.subnet.id
}

output "internet_gateway_id" {
  description = "OCID of the internet gateway"
  value       = oci_core_internet_gateway.igw.id
}

output "route_table_id" {
  description = "OCID of the route table"
  value       = oci_core_route_table.route_table.id
}

output "security_list_id" {
  description = "OCID of the security list"
  value       = oci_core_security_list.security_list.id
}

output "vcn_cidr" {
  description = "CIDR block of the VCN"
  value       = oci_core_vcn.vcn.cidr_block
}

output "subnet_cidr" {
  description = "CIDR block of the subnet"
  value       = oci_core_subnet.subnet.cidr_block
}
