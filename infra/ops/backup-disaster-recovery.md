# RetainAI Backup And Disaster Recovery

## Recovery Targets

- Database: RPO <= 24 hours, target RPO 15 minutes using RDS automated backups and PITR
- Queue state: Redis is operationally recoverable, but queued jobs may be replayed from the application DB where possible
- Artifacts and MLflow history: retained in versioned S3 and replicated by normal S3 durability guarantees

## Backup Sources

### PostgreSQL

- RDS automated backups enabled
- AWS Backup plan attached to the RDS instance
- final snapshots enabled on deletion

### Redis

- ElastiCache snapshots enabled with a 7-day retention window
- Redis is not the system of record; application jobs and intervention state remain in PostgreSQL

### Artifacts And MLflow

- model artifacts and MLflow run data should be mirrored to S3
- S3 versioning is enabled
- server-side encryption with KMS is enabled

## Restore Procedures

### 1. Database Point-In-Time Restore

1. Restore the RDS instance to a new identifier and timestamp.
2. Update the secret in Secrets Manager or the Kubernetes secret payload to point `DATABASE_URL` at the restored instance.
3. Restart API and worker deployments.
4. Validate:
   - `GET /readyz`
   - login
   - `GET /api/v1/ops/runtime-status`

### 2. Redis Restore

1. Restore the ElastiCache replication group from the latest snapshot.
2. Update `REDIS_URL` if the endpoint changed.
3. Restart worker deployments.
4. Review `/api/v1/ops/worker-health` and inspect dead-letter jobs.

### 3. Artifact Recovery

1. Restore the required object versions from the S3 artifact bucket.
2. Rehydrate the mounted artifact path or rebuild the deployment with the recovered objects mounted or synced.
3. Confirm deployed model status through `/api/v1/model/status`.

## Disaster Scenarios

### Region-Level Outage

Phase 1 does not fully automate multi-region failover.

Current recovery approach:

1. Provision the Terraform stack in the secondary region.
2. Restore the database from snapshot / backup copy.
3. Restore artifacts from S3 replication target or cross-region copy.
4. Repoint DNS to the secondary ingress.

This is sufficient for staged recovery planning, not instant failover.

### Application Rollout Failure

1. Roll back API, worker, and web deployments.
2. If the migration job already ran and is incompatible, restore the database from pre-deploy snapshot.
3. Re-run smoke validation.

## Operational Checks

Weekly:

- verify AWS Backup recovery points exist
- verify latest RDS automated backup timestamp
- verify Redis snapshot retention
- verify artifact bucket versioning remains enabled

Quarterly:

- run a non-production restore exercise
- verify an app deployment against a restored database copy
- verify incident steps are still accurate
