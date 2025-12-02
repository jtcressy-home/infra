variable "compartment_id" {
  description = "OCID of the compartment where network resources will be created"
  type        = string
}

variable "vcn_cidr" {
  description = "CIDR block for the VCN"
  type        = string
  default     = "192.168.120.0/24"
}

variable "subnet_cidr" {
  description = "CIDR block for the subnet"
  type        = string
  default     = "192.168.120.0/25"
}

variable "vcn_display_name" {
  description = "Display name for the VCN"
  type        = string
  default     = "omni-vcn"
}

variable "subnet_display_name" {
  description = "Display name for the subnet"
  type        = string
  default     = "omni-subnet"
}

variable "enable_dns" {
  description = "Enable DNS resolution for the VCN"
  type        = bool
  default     = true
}
