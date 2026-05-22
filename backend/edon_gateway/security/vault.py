"""Production vault provider detection for credential storage.

This module does not fetch secrets directly during request handling. It gives
startup/readiness checks one canonical place to determine whether a HIPAA
deployment is wired to an approved secret manager.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class VaultStatus:
    provider: str
    configured: bool
    kms_configured: bool
    secret_reference: Optional[str] = None
    kms_reference: Optional[str] = None


def get_vault_status() -> VaultStatus:
    azure_vault = (os.getenv("AZURE_KEY_VAULT_URL") or "").strip()
    aws_region = (os.getenv("AWS_SECRETS_MANAGER_REGION") or "").strip()
    gcp_project = (os.getenv("GCP_SECRET_MANAGER_PROJECT") or "").strip()
    vault_addr = (os.getenv("VAULT_ADDR") or os.getenv("EDON_VAULT_URL") or "").strip()

    if azure_vault:
        return VaultStatus(
            provider="azure_key_vault",
            configured=True,
            kms_configured=bool((os.getenv("AZURE_KEY_VAULT_KEY_ID") or "").strip()),
            secret_reference=azure_vault,
            kms_reference=(os.getenv("AZURE_KEY_VAULT_KEY_ID") or "").strip() or None,
        )
    if aws_region:
        return VaultStatus(
            provider="aws_secrets_manager",
            configured=True,
            kms_configured=bool((os.getenv("AWS_KMS_KEY_ID") or "").strip()),
            secret_reference=aws_region,
            kms_reference=(os.getenv("AWS_KMS_KEY_ID") or "").strip() or None,
        )
    if gcp_project:
        return VaultStatus(
            provider="gcp_secret_manager",
            configured=True,
            kms_configured=bool((os.getenv("GCP_KMS_KEY_NAME") or "").strip()),
            secret_reference=gcp_project,
            kms_reference=(os.getenv("GCP_KMS_KEY_NAME") or "").strip() or None,
        )
    if vault_addr:
        return VaultStatus(
            provider="hashicorp_vault",
            configured=True,
            kms_configured=bool((os.getenv("EDON_KMS_KEY_ID") or "").strip()),
            secret_reference=vault_addr,
            kms_reference=(os.getenv("EDON_KMS_KEY_ID") or "").strip() or None,
        )
    return VaultStatus(provider="none", configured=False, kms_configured=False)
