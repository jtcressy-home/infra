# VCN (Virtual Cloud Network)
resource "oci_core_vcn" "vcn" {
  compartment_id = var.compartment_id
  cidr_block     = var.vcn_cidr
  display_name   = var.vcn_display_name
  dns_label      = "omni"

  is_ipv6enabled = false
}

# Internet Gateway
resource "oci_core_internet_gateway" "igw" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.vcn.id
  display_name   = "${var.vcn_display_name}-igw"
  enabled        = true
}

# Route Table
resource "oci_core_route_table" "route_table" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.vcn.id
  display_name   = "${var.vcn_display_name}-route-table"

  route_rules {
    network_entity_id = oci_core_internet_gateway.igw.id
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    description       = "Default route to internet gateway"
  }
}

# Security List
resource "oci_core_security_list" "security_list" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.vcn.id
  display_name   = "${var.vcn_display_name}-security-list"

  # Egress Rules - Allow all outbound traffic
  egress_security_rules {
    destination      = "0.0.0.0/0"
    protocol         = "all"
    description      = "Allow all outbound traffic"
    destination_type = "CIDR_BLOCK"
    stateless        = false
  }

  # Ingress Rules - SSH (TCP 22)
  ingress_security_rules {
    source      = "0.0.0.0/0"
    protocol    = "6" # TCP
    description = "Allow SSH access"
    source_type = "CIDR_BLOCK"
    stateless   = false

    tcp_options {
      min = 22
      max = 22
    }
  }

  # Ingress Rules - Tailscale UDP (41641)
  ingress_security_rules {
    source      = "0.0.0.0/0"
    protocol    = "17" # UDP
    description = "Allow Tailscale UDP traffic"
    source_type = "CIDR_BLOCK"
    stateless   = false

    udp_options {
      min = 41641
      max = 41641
    }
  }
}

# Subnet
resource "oci_core_subnet" "subnet" {
  compartment_id    = var.compartment_id
  vcn_id            = oci_core_vcn.vcn.id
  cidr_block        = var.subnet_cidr
  display_name      = var.subnet_display_name
  dns_label         = "subnet"
  route_table_id    = oci_core_route_table.route_table.id
  security_list_ids = [oci_core_security_list.security_list.id]

  prohibit_public_ip_on_vnic = false
}
