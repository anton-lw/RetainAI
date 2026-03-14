terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.90"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "eks_cluster_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "eks_node_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "backup_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["backup.amazonaws.com"]
    }
  }
}

locals {
  name = "${var.project_name}-${var.environment}"
  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
  app_secret_payload = jsonencode({
    DATABASE_URL              = "postgresql+psycopg://${var.db_username}:${var.db_password}@${aws_db_instance.retainai.address}:5432/${var.db_name}"
    REDIS_URL                 = "redis://${aws_elasticache_replication_group.retainai.primary_endpoint_address}:6379/0"
    JWT_SECRET_KEY            = var.jwt_secret_key
    CONNECTOR_SECRET_KEY      = var.connector_secret_key
    PRIVACY_TOKEN_KEY         = var.privacy_token_key
    FEDERATED_SECRET_KEY      = var.federated_secret_key
    BOOTSTRAP_ADMIN_EMAIL     = var.bootstrap_admin_email
    BOOTSTRAP_ADMIN_PASSWORD  = var.bootstrap_admin_password
    DEPLOYMENT_REGION         = var.aws_region
    ENFORCE_RUNTIME_POLICY    = "true"
    JOB_BACKEND               = "celery"
    MLFLOW_EXPERIMENT_NAME    = "retainai-dropout-models"
    RETAINAI_HOSTNAME         = var.retainai_hostname
  })
}

resource "aws_kms_key" "retainai" {
  description             = "RetainAI encryption key"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = merge(local.tags, { Name = "${local.name}-kms" })
}

resource "aws_kms_alias" "retainai" {
  name          = "alias/${local.name}"
  target_key_id = aws_kms_key.retainai.key_id
}

resource "aws_vpc" "retainai" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(local.tags, { Name = "${local.name}-vpc" })
}

resource "aws_internet_gateway" "retainai" {
  vpc_id = aws_vpc.retainai.id
  tags   = merge(local.tags, { Name = "${local.name}-igw" })
}

resource "aws_subnet" "public" {
  count                   = length(var.public_subnet_cidrs)
  vpc_id                  = aws_vpc.retainai.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true
  tags = merge(local.tags, {
    Name                                      = "${local.name}-public-${count.index + 1}"
    "kubernetes.io/cluster/${local.name}"     = "shared"
    "kubernetes.io/role/elb"                  = "1"
  })
}

resource "aws_subnet" "private" {
  count             = length(var.private_subnet_cidrs)
  vpc_id            = aws_vpc.retainai.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]
  tags = merge(local.tags, {
    Name                                      = "${local.name}-private-${count.index + 1}"
    "kubernetes.io/cluster/${local.name}"     = "shared"
    "kubernetes.io/role/internal-elb"         = "1"
  })
}

resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = merge(local.tags, { Name = "${local.name}-nat-eip" })
}

resource "aws_nat_gateway" "retainai" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  tags          = merge(local.tags, { Name = "${local.name}-nat" })
  depends_on    = [aws_internet_gateway.retainai]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.retainai.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.retainai.id
  }
  tags = merge(local.tags, { Name = "${local.name}-public-rt" })
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.retainai.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.retainai.id
  }
  tags = merge(local.tags, { Name = "${local.name}-private-rt" })
}

resource "aws_route_table_association" "private" {
  count          = length(aws_subnet.private)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

resource "aws_security_group" "eks_cluster" {
  name        = "${local.name}-eks-cluster"
  description = "RetainAI EKS cluster"
  vpc_id      = aws_vpc.retainai.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${local.name}-eks-cluster" })
}

resource "aws_security_group" "db" {
  name        = "${local.name}-db"
  description = "RetainAI PostgreSQL"
  vpc_id      = aws_vpc.retainai.id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${local.name}-db" })
}

resource "aws_security_group" "redis" {
  name        = "${local.name}-redis"
  description = "RetainAI Redis"
  vpc_id      = aws_vpc.retainai.id

  ingress {
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${local.name}-redis" })
}

resource "aws_cloudwatch_log_group" "eks" {
  name              = "/aws/eks/${local.name}/cluster"
  retention_in_days = var.retention_days_cloudwatch
  kms_key_id        = aws_kms_key.retainai.arn
  tags              = local.tags
}

resource "aws_iam_role" "eks_cluster" {
  name               = "${local.name}-eks-cluster"
  assume_role_policy = data.aws_iam_policy_document.eks_cluster_assume_role.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "eks_cluster" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_iam_role" "eks_node" {
  name               = "${local.name}-eks-node"
  assume_role_policy = data.aws_iam_policy_document.eks_node_assume_role.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "eks_node_worker" {
  role       = aws_iam_role.eks_node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "eks_node_cni" {
  role       = aws_iam_role.eks_node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "eks_node_ecr" {
  role       = aws_iam_role.eks_node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPullOnly"
}

resource "aws_iam_role_policy_attachment" "eks_node_cloudwatch" {
  role       = aws_iam_role.eks_node.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

resource "aws_eks_cluster" "retainai" {
  name     = local.name
  role_arn = aws_iam_role.eks_cluster.arn
  version  = var.cluster_version

  enabled_cluster_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]

  vpc_config {
    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs     = var.allowed_ingress_cidrs
    security_group_ids      = [aws_security_group.eks_cluster.id]
    subnet_ids              = concat(aws_subnet.public[*].id, aws_subnet.private[*].id)
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_cluster,
    aws_cloudwatch_log_group.eks,
  ]

  tags = local.tags
}

resource "aws_eks_node_group" "retainai" {
  cluster_name    = aws_eks_cluster.retainai.name
  node_group_name = "${local.name}-workers"
  node_role_arn   = aws_iam_role.eks_node.arn
  subnet_ids      = aws_subnet.private[*].id
  instance_types  = var.node_instance_types

  scaling_config {
    desired_size = var.node_desired_size
    min_size     = var.node_min_size
    max_size     = var.node_max_size
  }

  update_config {
    max_unavailable = 1
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_node_worker,
    aws_iam_role_policy_attachment.eks_node_cni,
    aws_iam_role_policy_attachment.eks_node_ecr,
    aws_iam_role_policy_attachment.eks_node_cloudwatch,
  ]

  tags = local.tags
}

resource "aws_s3_bucket" "artifacts" {
  bucket        = "${local.name}-${data.aws_caller_identity.current.account_id}-artifacts"
  force_destroy = var.artifact_bucket_force_destroy
  tags          = merge(local.tags, { Name = "${local.name}-artifacts" })
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.retainai.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "retain-versions"
    status = "Enabled"

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

resource "aws_db_subnet_group" "retainai" {
  name       = "${local.name}-db-subnets"
  subnet_ids = aws_subnet.private[*].id
  tags       = local.tags
}

resource "aws_db_instance" "retainai" {
  identifier                  = "${local.name}-db"
  engine                      = "postgres"
  engine_version              = "16.4"
  instance_class              = var.db_instance_class
  allocated_storage           = var.db_allocated_storage
  max_allocated_storage       = var.db_max_allocated_storage
  storage_type                = "gp3"
  storage_encrypted           = true
  kms_key_id                  = aws_kms_key.retainai.arn
  db_name                     = var.db_name
  username                    = var.db_username
  password                    = var.db_password
  db_subnet_group_name        = aws_db_subnet_group.retainai.name
  vpc_security_group_ids      = [aws_security_group.db.id]
  backup_retention_period     = var.db_backup_retention_days
  backup_window               = "03:00-04:00"
  maintenance_window          = "sun:04:00-sun:05:00"
  auto_minor_version_upgrade  = true
  deletion_protection         = var.db_deletion_protection
  skip_final_snapshot         = false
  final_snapshot_identifier   = "${local.name}-final-snapshot"
  multi_az                    = var.db_multi_az
  publicly_accessible         = false
  performance_insights_enabled = true
  performance_insights_kms_key_id = aws_kms_key.retainai.arn
  monitoring_interval         = 60
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  tags                        = local.tags
}

resource "aws_elasticache_subnet_group" "retainai" {
  name       = "${local.name}-redis-subnets"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_replication_group" "retainai" {
  replication_group_id          = replace("${local.name}-redis", "_", "-")
  description                   = "RetainAI Redis"
  engine                        = "redis"
  engine_version                = var.redis_engine_version
  node_type                     = var.redis_node_type
  port                          = 6379
  parameter_group_name          = "default.redis7"
  subnet_group_name             = aws_elasticache_subnet_group.retainai.name
  security_group_ids            = [aws_security_group.redis.id]
  num_cache_clusters            = var.redis_num_cache_clusters
  automatic_failover_enabled    = var.redis_num_cache_clusters > 1
  multi_az_enabled              = var.redis_num_cache_clusters > 1
  at_rest_encryption_enabled    = true
  transit_encryption_enabled    = true
  auto_minor_version_upgrade    = true
  snapshot_retention_limit      = 7
  snapshot_window               = "04:00-05:00"
  tags                          = local.tags
}

resource "aws_secretsmanager_secret" "retainai_app" {
  name                    = "${local.name}/application"
  recovery_window_in_days = 30
  kms_key_id              = aws_kms_key.retainai.arn
  tags                    = local.tags
}

resource "aws_secretsmanager_secret_version" "retainai_app" {
  secret_id     = aws_secretsmanager_secret.retainai_app.id
  secret_string = local.app_secret_payload
}

resource "aws_backup_vault" "retainai" {
  name        = "${local.name}-vault"
  kms_key_arn = aws_kms_key.retainai.arn
  tags        = local.tags
}

resource "aws_iam_role" "backup" {
  name               = "${local.name}-backup"
  assume_role_policy = data.aws_iam_policy_document.backup_assume_role.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "backup" {
  role       = aws_iam_role.backup.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup"
}

resource "aws_backup_plan" "retainai" {
  name = "${local.name}-plan"

  rule {
    rule_name         = "daily-rds"
    target_vault_name = aws_backup_vault.retainai.name
    schedule          = var.backup_plan_schedule

    lifecycle {
      delete_after = var.backup_delete_after_days
    }
  }

  tags = local.tags
}

resource "aws_backup_selection" "retainai" {
  iam_role_arn = aws_iam_role.backup.arn
  name         = "${local.name}-selection"
  plan_id      = aws_backup_plan.retainai.id
  resources    = [aws_db_instance.retainai.arn]
}
