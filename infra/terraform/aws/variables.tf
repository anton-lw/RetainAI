variable "project_name" {
  type    = string
  default = "retainai"
}

variable "environment" {
  type    = string
  default = "production"
}

variable "aws_region" {
  type    = string
  default = "eu-north-1"
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "availability_zones" {
  type    = list(string)
  default = ["eu-north-1a", "eu-north-1b"]
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.42.1.0/24", "10.42.2.0/24"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.42.11.0/24", "10.42.12.0/24"]
}

variable "cluster_version" {
  type    = string
  default = "1.31"
}

variable "node_instance_types" {
  type    = list(string)
  default = ["t3.large"]
}

variable "node_desired_size" {
  type    = number
  default = 2
}

variable "node_min_size" {
  type    = number
  default = 2
}

variable "node_max_size" {
  type    = number
  default = 5
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "db_allocated_storage" {
  type    = number
  default = 100
}

variable "db_max_allocated_storage" {
  type    = number
  default = 300
}

variable "db_name" {
  type    = string
  default = "retainai"
}

variable "db_username" {
  type    = string
  default = "retainai"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "db_backup_retention_days" {
  type    = number
  default = 14
}

variable "db_multi_az" {
  type    = bool
  default = true
}

variable "db_deletion_protection" {
  type    = bool
  default = true
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.medium"
}

variable "redis_engine_version" {
  type    = string
  default = "7.1"
}

variable "redis_num_cache_clusters" {
  type    = number
  default = 2
}

variable "artifact_bucket_force_destroy" {
  type    = bool
  default = false
}

variable "retention_days_cloudwatch" {
  type    = number
  default = 30
}

variable "backup_plan_schedule" {
  type    = string
  default = "cron(0 3 * * ? *)"
}

variable "backup_delete_after_days" {
  type    = number
  default = 35
}

variable "allowed_ingress_cidrs" {
  type    = list(string)
  default = ["0.0.0.0/0"]
}

variable "retainai_hostname" {
  type    = string
  default = "retainai.example.org"
}

variable "bootstrap_admin_email" {
  type    = string
  default = "admin@example.org"
}

variable "bootstrap_admin_password" {
  type      = string
  sensitive = true
}

variable "jwt_secret_key" {
  type      = string
  sensitive = true
}

variable "connector_secret_key" {
  type      = string
  sensitive = true
}

variable "privacy_token_key" {
  type      = string
  sensitive = true
}

variable "federated_secret_key" {
  type      = string
  sensitive = true
}
