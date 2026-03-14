output "vpc_id" {
  value = aws_vpc.retainai.id
}

output "eks_cluster_name" {
  value = aws_eks_cluster.retainai.name
}

output "eks_cluster_endpoint" {
  value = aws_eks_cluster.retainai.endpoint
}

output "eks_cluster_ca" {
  value     = aws_eks_cluster.retainai.certificate_authority[0].data
  sensitive = true
}

output "database_endpoint" {
  value = aws_db_instance.retainai.address
}

output "database_secret_arn" {
  value = aws_secretsmanager_secret.retainai_app.arn
}

output "redis_primary_endpoint" {
  value = aws_elasticache_replication_group.retainai.primary_endpoint_address
}

output "artifacts_bucket_name" {
  value = aws_s3_bucket.artifacts.bucket
}

output "backup_vault_name" {
  value = aws_backup_vault.retainai.name
}
