terraform {
  required_version = ">= 1.5"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 5.0"
    }
  }
}

provider "oci" {
  region = var.region
}

variable "region" {
  description = "OCI region"
  type        = string
  default     = "sa-saopaulo-1"
}

variable "compartment_ocid" {
  description = "Compartment OCID"
  type        = string
}

variable "ssh_public_key" {
  description = "SSH public key content"
  type        = string
  sensitive   = true
}

variable "wireguard_private_key" {
  description = "WireGuard server private key"
  type        = string
  sensitive   = true
}

variable "wireguard_public_key" {
  description = "WireGuard server public key"
  type        = string
}

variable "client_public_key" {
  description = "WireGuard client public key"
  type        = string
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.compartment_ocid
}

resource "oci_core_vcn" "freeping_vcn" {
  compartment_id = var.compartment_ocid
  display_name   = "FreePing-VCN"
  cidr_block     = "10.0.0.0/16"
  dns_label      = "freeping"
}

resource "oci_core_subnet" "freeping_subnet" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.freeping_vcn.id
  display_name   = "FreePing-Subnet"
  cidr_block     = "10.0.1.0/24"
  dns_label      = "freepingsubnet"
  route_table_id = oci_core_vcn.freeping_vcn.default_route_table_id
}

resource "oci_core_network_security_group" "freeping_nsg" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.freeping_vcn.id
  display_name   = "FreePing-NSG"
}

resource "oci_core_network_security_group_security_rule" "wireguard_udp" {
  network_security_group_id = oci_core_network_security_group.freeping_nsg.id
  direction                 = "INGRESS"
  protocol                  = "17"
  source                    = "0.0.0.0/0"
  source_type               = "CIDR_BLOCK"
  description               = "WireGuard UDP"

  udp_options {
    destination_port_range {
      min = 51820
      max = 51820
    }
  }
}

resource "oci_core_network_security_group_security_rule" "icmp" {
  network_security_group_id = oci_core_network_security_group.freeping_nsg.id
  direction                 = "INGRESS"
  protocol                  = "1"
  source                    = "0.0.0.0/0"
  source_type               = "CIDR_BLOCK"
  description               = "ICMP Ping"
}

resource "oci_core_network_security_group_security_rule" "egress_all" {
  network_security_group_id = oci_core_network_security_group.freeping_nsg.id
  direction                 = "EGRESS"
  protocol                  = "all"
  destination               = "0.0.0.0/0"
  destination_type          = "CIDR_BLOCK"
}

resource "oci_core_instance" "freeping_vps" {
  compartment_id      = var.compartment_ocid
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name        = "FreePing-VPS"
  shape               = "VM.Standard.A1.Flex"

  shape_config {
    ocpus         = 1
    memory_in_gbs = 6
  }

  source_details {
    source_type             = "image"
    source_id               = lookup(var.image_ids, var.region, "")
    boot_volume_size_in_gbs = 50
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data           = base64encode(templatefile("${path.module}/cloud-init.yaml", {
      server_private_key = var.wireguard_private_key
      server_public_key  = var.wireguard_public_key
      client_public_key  = var.client_public_key
    }))
  }

  create_vnic_details {
    subnet_id     = oci_core_subnet.freeping_subnet.id
    nsg_ids       = [oci_core_network_security_group.freeping_nsg.id]
    assign_public_ip = true
    display_name  = "FreePing-VNIC"
  }
}

output "instance_id" {
  value = oci_core_instance.freeping_vps.id
}

output "public_ip" {
  value = oci_core_instance.freeping_vps.public_ip
}

output "region" {
  value = var.region
}
