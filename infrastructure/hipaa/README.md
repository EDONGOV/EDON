# EDON HIPAA Cloud Deployment Profile

This folder is the production deployment contract for healthcare tenants. It is
provider-neutral, but the first recommended path is Azure for hospitals that
already use Entra ID, Teams, Sentinel, and Microsoft 365.

## Required Before Go-Live

- Signed BAA with the selected cloud provider.
- `EDON_CLOUD_PROVIDER` set to `azure`, `aws`, or `gcp`.
- `EDON_HIPAA_DEPLOYMENT_PROFILE=true`.
- `EDON_BAA_SIGNED=true`.
- Private network enabled: `EDON_PRIVATE_NETWORK_ENABLED=true`.
- WAF/API gateway enabled: `EDON_WAF_ENABLED=true`.
- Managed Postgres enabled: `EDON_MANAGED_POSTGRES=true`.
- Vault provider configured:
  - Azure: `AZURE_KEY_VAULT_URL`
  - AWS: `AWS_SECRETS_MANAGER_REGION`
  - GCP: `GCP_SECRET_MANAGER_PROJECT`
  - HashiCorp: `VAULT_ADDR` or `EDON_VAULT_URL`
- KMS provider configured:
  - Azure: `AZURE_KEY_VAULT_KEY_ID`
  - AWS: `AWS_KMS_KEY_ID`
  - GCP: `GCP_KMS_KEY_NAME`
  - HashiCorp/other: `EDON_KMS_KEY_ID`
- Signing keys injected from vault/KMS:
  - `EDON_SIGNING_KEY_HEX`
  - `EDON_AUDIT_CHAIN_SIGNING_KEY`
  - `EDON_DB_ENCRYPTION_KEY`
- SSO claim mapping configured:
  - `EDON_ENTERPRISE_SSO_ONLY=true`
  - `EDON_SSO_ROLE_CLAIM=edon_role`
  - `EDON_SSO_DEPARTMENT_CLAIM=edon_department`
- Log/SIEM export configured:
  - `EDON_LOG_RETENTION_DAYS=2190` recommended for healthcare evidence.
  - One of `EDON_SIEM_ENDPOINT`, `EDON_SENTINEL_WORKSPACE_ID`, `EDON_SPLUNK_HEC_URL`, or `EDON_LOG_ARCHIVE_BUCKET`.
- Alert routing configured:
  - `EDON_ALERT_WEBHOOK` or `EDON_PAGERDUTY_ROUTING_KEY`.
- Backup/restore configured:
  - `EDON_BACKUP_BUCKET` or `PG_BACKUP_BUCKET`.
  - `EDON_BACKUP_SCHEDULE`.
  - `EDON_RESTORE_DRILL_LAST_RUN_AT` updated after a successful restore drill.

## Azure Reference Stack

- Azure App Service or AKS for the gateway.
- Azure Database for PostgreSQL Flexible Server.
- Azure Key Vault for runtime credentials, signing keys, and encryption keys.
- Azure Application Gateway WAF.
- Private Link for Postgres and Key Vault.
- Entra ID OIDC/SAML for console users.
- Microsoft Sentinel or Log Analytics for SIEM/log retention.
- Azure Monitor alerts to PagerDuty/Teams/webhook.

## AWS Reference Stack

- ECS Fargate or EKS for the gateway.
- RDS PostgreSQL.
- AWS Secrets Manager and KMS.
- AWS WAF + ALB/API Gateway.
- Private subnets, VPC endpoints, security groups.
- Okta/Entra/OIDC/SAML for console users.
- CloudWatch Logs with export to S3/SIEM.
- EventBridge/CloudWatch alarms to PagerDuty/webhook.

## GCP Reference Stack

- Cloud Run or GKE for the gateway.
- Cloud SQL for PostgreSQL.
- Secret Manager and Cloud KMS.
- Cloud Armor.
- Private Service Connect/VPC connectors.
- OIDC/SAML for console users.
- Cloud Logging sink to BigQuery/SIEM/storage.
- Cloud Monitoring alerts to PagerDuty/webhook.

## Readiness Endpoint

After deployment, call:

```text
GET /ops/production-readiness
```

The response must return `ready: true` before a hospital production go-live.
