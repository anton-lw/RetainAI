# RetainAI Deployment Runbook

## Scope

This runbook describes the minimum production deployment path for RetainAI on AWS with:

- EKS for application workloads
- RDS PostgreSQL for the primary datastore
- ElastiCache Redis for Celery broker/result backend
- S3 for artifacts and MLflow run data
- Secrets Manager for application secrets

## Preconditions

1. Build and publish `ghcr.io/example/retainai-api:<tag>` and `ghcr.io/example/retainai-web:<tag>`.
2. Copy `infra/terraform/aws/terraform.tfvars.example` to `terraform.tfvars` and set real secrets.
3. Confirm the chosen AWS region satisfies the residency policy for the target NGO deployment.
4. Confirm the TLS hostname and DNS ownership for `retainai_hostname`.

## Provision Infrastructure

```bash
cd infra/terraform/aws
terraform init
terraform plan
terraform apply
```

Record these outputs:

- `eks_cluster_name`
- `database_secret_arn`
- `database_endpoint`
- `redis_primary_endpoint`
- `artifacts_bucket_name`

## Prepare Cluster Access

```bash
aws eks update-kubeconfig --region <aws-region> --name <eks-cluster-name>
kubectl create namespace retainai
```

## Populate Kubernetes Secret

The manifest expects `retainai-secrets` to exist with resolved endpoints and keys. Either:

- edit `infra/k8s/retainai.yaml` and apply directly for a first deployment, or
- replace the inline secret with External Secrets / Secrets Store CSI and map it to the Terraform-created Secrets Manager secret.

At minimum, provide:

- `DATABASE_URL`
- `REDIS_URL`
- `JWT_SECRET_KEY`
- `CONNECTOR_SECRET_KEY`
- `PRIVACY_TOKEN_KEY`
- `FEDERATED_SECRET_KEY`
- bootstrap admin credentials if you need initial console access

## Deploy Application

Apply the manifest in this order:

```bash
kubectl apply -f infra/k8s/retainai.yaml
kubectl wait --for=condition=complete job/retainai-migrate -n retainai --timeout=10m
kubectl rollout status deployment/api -n retainai
kubectl rollout status deployment/worker -n retainai
kubectl rollout status deployment/web -n retainai
```

## Post-Deploy Validation

Run:

```bash
kubectl get pods -n retainai
kubectl get ingress -n retainai
kubectl logs job/retainai-migrate -n retainai
```

Validate through the ingress:

- `GET /livez`
- `GET /readyz`
- `GET /health`
- login
- `GET /api/v1/ops/runtime-status`
- `GET /api/v1/ops/worker-health`

Operational acceptance criteria:

- API readiness is `ok`
- runtime status has zero violations
- worker health shows zero dead-letter jobs
- Redis and Postgres endpoints resolve from inside the cluster

## Rollback

Application rollback:

```bash
kubectl rollout undo deployment/api -n retainai
kubectl rollout undo deployment/worker -n retainai
kubectl rollout undo deployment/web -n retainai
```

Database rollback:

- prefer point-in-time restore of RDS into a new instance
- repoint `DATABASE_URL`
- run smoke validation before promoting traffic

## Phase 1 Limits

This runbook assumes:

- AWS-managed Postgres and Redis
- single-region deployment
- manual secret population or external-secrets integration
- cluster creation and add-on management are Terraform-managed, but the application release is still `kubectl apply` based
