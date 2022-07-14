variable "regions" {}
variable "machines" {}
variable "cluster_name" {}
variable "ssh_pub_key" {}
variable "ssh_priv_key" {}
variable "ssh_user" {}

# VPC
variable "public_cidrblock" {
  description = "Public CIDR block"
  type        = string
  default     = "0.0.0.0/0"
}

# IAM User Name
variable "user_name" {
  description = "Desired name for AWS IAM User"
  type        = string
  default     = "bdrbench-edb-iam-postgres"
}

# IAM Force Destroy
variable "user_force_destroy" {
  description = "Force destroying AWS IAM User and dependencies"
  type        = bool
  default     = true
}

variable "project_tag" {
  type    = string
  default = "edb_terraform"
}

variable "vpc_tag" {
  default = "edb_terraform_vpc"
}

# Subnets
variable "public_subnet_tag" {
  default = "edb_terraform_public_subnet"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID"
  default     = ""
}

variable "custom_security_group_id" {
  description = "Security Group assign to the instances. Example: 'sg-12345'."
  type        = string
  default     = ""
}

variable "created_by" {
  type        = string
  description = "EDB terraform AWS"
  default     = "EDB terraform AWS"
}

variable "ami_name" {
  type        = string
  description = "AMI substring"
  default     = "Rocky-8-ec2-8.6-20220515.0.x86_64-*"
}

variable "ami_owner" {
  type        = string
  description = "AMI owner"
  default     = "679593333241"
}
