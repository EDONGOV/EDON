"""Centralized configuration management for EDON Gateway."""

# 🔐 CRITICAL: Load gateway .env FIRST, before anything else
# This MUST happen before Config class reads os.getenv()
from pathlib import Path
from dotenv import load_dotenv
import os

# 🔐 HARD-OVERRIDE: gateway-only env
ENV_PATH = Path(__file__).resolve().parent / ".env"
if ENV_PATH.exists():
    try:
        # Do not override environment-injected secrets (e.g. Fly secrets) in production.
        load_dotenv(dotenv_path=ENV_PATH, override=False, encoding="utf-8")
    except UnicodeDecodeError:
        # If UTF-8 fails, try to detect and convert encoding
        try:
            # Try reading as UTF-16 (common Windows issue)
            with open(ENV_PATH, "r", encoding="utf-16") as f:
                content = f.read()
            # Write back as UTF-8
            with open(ENV_PATH, "w", encoding="utf-8") as f:
                f.write(content)
            # Reload as UTF-8
            load_dotenv(dotenv_path=ENV_PATH, override=False, encoding="utf-8")
            print(f"⚠️  Converted {ENV_PATH} from UTF-16 to UTF-8")
        except Exception as e:
            raise RuntimeError(
                f"Failed to load {ENV_PATH}: Invalid encoding (not UTF-8). "
                f"Please run: cd edon_gateway && .\\fix_env_encoding.ps1\n"
                f"Or recreate the file with UTF-8 encoding. Error: {e}"
            )

# 🚨 Guardrail: token presence sanity
def _is_production_env() -> bool:
    return os.getenv("ENVIRONMENT") == "production" or os.getenv("EDON_ENV") == "production"

if os.getenv("EDON_AUTH_ENABLED", "true").lower() == "true":
    token = os.getenv("EDON_API_TOKEN")
    if not token:
        raise RuntimeError(
            f"EDON_API_TOKEN missing — gateway cannot start. "
            f"Set EDON_API_TOKEN in {ENV_PATH} or environment variables."
        )
    elif token in ["your-secret-token", "your-secret-token-change-me", "production-token-change-me", "change-me"]:
        if _is_production_env():
            raise RuntimeError(
                f"EDON_API_TOKEN is set to a default value. "
                f"Change EDON_API_TOKEN in {ENV_PATH} before running in production."
            )
        else:
            import warnings
            warnings.warn(
                f"⚠️  Using default API token! Change EDON_API_TOKEN in {ENV_PATH} for production.",
                UserWarning
            )

from typing import Optional, List


class Config:
    """EDON Gateway configuration.

    Reads environment variables at instance creation time to ensure .env is loaded first.
    """

    def __init__(self):
        # =========================
        # Authentication
        # =========================
        self._AUTH_ENABLED = os.getenv("EDON_AUTH_ENABLED", "true").lower() == "true"
        self._API_TOKEN = os.getenv("EDON_API_TOKEN", "your-secret-token")
        self._TOKEN_BINDING_ENABLED = os.getenv("EDON_TOKEN_BINDING_ENABLED", "false").lower() == "true"

        # Bootstrap / admin override:
        # Allow env token auth in production (default false).
        # If false, production forces tenant-scoped API keys (DB lookup).
        self._ALLOW_ENV_TOKEN_IN_PROD = (os.getenv("EDON_ALLOW_ENV_TOKEN_IN_PROD", "false") or "").strip().lower() == "true"

        # =========================
        # Security
        # =========================
        self._CREDENTIALS_STRICT = os.getenv("EDON_CREDENTIALS_STRICT", "false").lower() == "true"
        self._ENTERPRISE_MODE = os.getenv("EDON_ENTERPRISE_MODE", "false").lower() == "true"
        self._ENTERPRISE_SSO_ONLY = os.getenv("EDON_ENTERPRISE_SSO_ONLY", "false").lower() == "true"
        self._REQUIRE_ADMIN_MFA = os.getenv("EDON_REQUIRE_ADMIN_MFA", "false").lower() == "true"
        self._REQUIRE_PHISHING_RESISTANT_MFA = (
            os.getenv("EDON_REQUIRE_PHISHING_RESISTANT_MFA", "false").lower() == "true"
        )
        self._EDGE_REQUIRE_NODE_CERTIFICATE = (
            os.getenv("EDON_EDGE_REQUIRE_NODE_CERTIFICATE", "false").lower() == "true"
        )
        self._EDGE_REQUIRE_ATTESTATION = os.getenv("EDON_EDGE_REQUIRE_ATTESTATION", "false").lower() == "true"
        self._ENTERPRISE_IDENTITY_PROVIDERS = [
            p.strip().lower()
            for p in (os.getenv("EDON_ENTERPRISE_IDENTITY_PROVIDERS", "clerk,oidc,saml")).split(",")
            if p.strip()
        ]
        self._ENTERPRISE_DEFAULT_USER_ROLE = (
            os.getenv("EDON_ENTERPRISE_DEFAULT_USER_ROLE", "viewer" if self._ENTERPRISE_MODE else "user")
        ).strip().lower()
        self._ENTERPRISE_DEFAULT_API_KEY_ROLE = (
            os.getenv("EDON_ENTERPRISE_DEFAULT_API_KEY_ROLE", "operator" if self._ENTERPRISE_MODE else "admin")
        ).strip().lower()

        # Environment
        self._ENVIRONMENT = os.getenv("ENVIRONMENT") or os.getenv("EDON_ENV") or "development"
        self._TOKEN_HARDENING = os.getenv("EDON_TOKEN_HARDENING", "true").lower() == "true"
        self._NETWORK_GATING = os.getenv("EDON_NETWORK_GATING", "false").lower() == "true"
        self._VALIDATE_STRICT = os.getenv("EDON_VALIDATE_STRICT", "true").lower() == "true"
        self._ENCRYPT_AUDIT_PAYLOAD = os.getenv("EDON_ENCRYPT_AUDIT_PAYLOAD", "false").lower() == "true"

        # =========================
        # Database
        # =========================
        self._DATABASE_PATH = Path(os.getenv("EDON_DATABASE_PATH", "edon_gateway.db"))

        # =========================
        # Logging
        # =========================
        self._LOG_LEVEL = os.getenv("EDON_LOG_LEVEL", "INFO").upper()
        self._JSON_LOGGING = os.getenv("EDON_JSON_LOGGING", "false").lower() == "true"

        # =========================
        # Monitoring
        # =========================
        self._METRICS_ENABLED = os.getenv("EDON_METRICS_ENABLED", "true").lower() == "true"
        self._METRICS_PORT = int(os.getenv("EDON_METRICS_PORT", "9090"))

        # =========================
        # Rate Limiting
        # =========================
        self._RATE_LIMIT_ENABLED = os.getenv("EDON_RATE_LIMIT_ENABLED", "true").lower() == "true"
        self._RATE_LIMIT_PER_MINUTE = int(os.getenv("EDON_RATE_LIMIT_PER_MINUTE", "60"))
        self._RATE_LIMIT_PER_HOUR = int(os.getenv("EDON_RATE_LIMIT_PER_HOUR", "1000"))

        # =========================
        # CORS
        # =========================
        cors_origins_str = os.getenv("EDON_CORS_ORIGINS", "*")
        self._CORS_ORIGINS = [o.strip() for o in cors_origins_str.split(",") if o.strip()]

        # =========================
        # Server
        # =========================
        self._HOST = os.getenv("EDON_HOST", "0.0.0.0")
        self._PORT = int(os.getenv("EDON_PORT", "8000"))
        self._WORKERS = int(os.getenv("EDON_WORKERS", "1"))

        # =========================
        # UI (you can keep this even if not used)
        # =========================
        self._BUILD_UI = os.getenv("EDON_BUILD_UI", "false").lower() == "true"
        self._UI_REPO_URL = os.getenv(
            "EDON_UI_REPO_URL",
            "https://github.com/GHOSTCODERRRRAHAHA/edon-console-ui.git",
        )

        # =========================
        # Edonbot (single source of truth for default credential_id)
        # =========================
        self._DEFAULT_CLAWDBOT_CREDENTIAL_ID = "clawdbot_gateway_tenant_dev"
        self._CLAWDBOT_GATEWAY_URL = os.getenv("CLAWDBOT_GATEWAY_URL")
        self._CLAWDBOT_GATEWAY_TOKEN = os.getenv("CLAWDBOT_GATEWAY_TOKEN")
        self._CLAWDBOT_CREDENTIAL_ID = os.getenv("EDON_CLAWDBOT_CREDENTIAL_ID", self._DEFAULT_CLAWDBOT_CREDENTIAL_ID)

        # =========================
        # Stripe / Billing
        # =========================
        self._STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
        self._STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
        self._STRIPE_PRICE_SCALE = os.getenv("STRIPE_PRICE_SCALE")
        self._STRIPE_PRICE_PRO = os.getenv("STRIPE_PRICE_PRO")
        self._STRIPE_PAYMENT_LINK_SCALE = (os.getenv("STRIPE_PAYMENT_LINK_SCALE") or "https://checkout.edoncore.com/b/3cI6oGeKAehceAq5fafIs0a").strip() or None
        self._STRIPE_PAYMENT_LINK_PRO = (os.getenv("STRIPE_PAYMENT_LINK_PRO") or "https://checkout.edoncore.com/b/9B67sK5a04GC4ZQ7nifIs09").strip() or None
        self._EDON_APP_URL = (os.getenv("EDON_APP_URL") or "https://edoncore.com").rstrip("/")

        # =========================
        # Clerk Authentication
        # =========================
        self._CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY")

        # =========================
        # Telegram / Channel bindings
        # =========================
        self._TELEGRAM_BOT_SECRET = os.getenv("EDON_TELEGRAM_BOT_SECRET") or os.getenv("TELEGRAM_BOT_SECRET")
        self._TELEGRAM_CONNECT_TTL_MIN = int(os.getenv("EDON_TELEGRAM_CONNECT_TTL_MIN", "10"))

        # =========================
        # Connect flow (Gmail, Brave, etc.) — base URL for connect pages
        # =========================
        self._CONNECT_BASE_URL = (os.getenv("EDON_CONNECT_BASE_URL") or os.getenv("CONNECT_BASE_URL") or "").rstrip("/")
        self._GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID") or os.getenv("GMAIL_CLIENT_ID")
        self._GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET") or os.getenv("GMAIL_CLIENT_SECRET")
        self._HOME_ASSISTANT_BASE_URL = (os.getenv("HOME_ASSISTANT_BASE_URL") or "").rstrip("/")
        self._HOME_ASSISTANT_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN")
        self._HOME_ASSISTANT_CLIENT_ID = os.getenv("HOME_ASSISTANT_CLIENT_ID")
        self._HOME_ASSISTANT_CLIENT_SECRET = os.getenv("HOME_ASSISTANT_CLIENT_SECRET")

        # =========================
        # MAG Governance
        # =========================
        self._MAG_ENABLED = os.getenv("MAG_ENABLED", os.getenv("EDON_MAG_ENABLED", "false")).lower() == "true"
        self._MAG_URL = os.getenv("MAG_URL", os.getenv("EDON_MAG_URL", "http://localhost:8002")).rstrip("/")
        self._MAG_TIMEOUT_S = float(os.getenv("MAG_TIMEOUT_S", os.getenv("EDON_MAG_TIMEOUT_S", "3")))
        mag_paths = os.getenv("EDON_MAG_ENFORCE_PATHS", "/execute,/agent/invoke,/edon/invoke,/clawdbot/invoke")
        self._MAG_ENFORCE_PATHS = [p.strip() for p in mag_paths.split(",") if p.strip()]

        # =========================
        # Demo Mode
        # =========================
        self._DEMO_MODE = os.getenv("EDON_DEMO_MODE", "false").lower() == "true"
        self._DEMO_TENANT_ID = os.getenv("EDON_DEMO_TENANT_ID", "demo_tenant_001")
        self._DEMO_API_KEY = os.getenv("EDON_DEMO_API_KEY", "")
        if self._DEMO_MODE and not self._DEMO_API_KEY:
            raise RuntimeError(
                "EDON_DEMO_MODE is enabled but EDON_DEMO_API_KEY is not set. "
                "Set a non-default key in your .env file."
            )

        # =========================
        # CAV Engine
        # =========================
        self._CAV_URL = os.getenv("CAV_URL", "http://localhost:8001").rstrip("/")
        self._CAV_ENABLED = os.getenv("CAV_ENABLED", "false").lower() == "true"

    # ===== Properties =====
    @property
    def AUTH_ENABLED(self) -> bool:
        return self._AUTH_ENABLED

    @property
    def API_TOKEN(self) -> str:
        return self._API_TOKEN

    @property
    def TOKEN_BINDING_ENABLED(self) -> bool:
        return self._TOKEN_BINDING_ENABLED

    @property
    def ALLOW_ENV_TOKEN_IN_PROD(self) -> bool:
        return self._ALLOW_ENV_TOKEN_IN_PROD

    @property
    def CREDENTIALS_STRICT(self) -> bool:
        return self._CREDENTIALS_STRICT

    @property
    def ENTERPRISE_MODE(self) -> bool:
        return self._ENTERPRISE_MODE

    @property
    def ENTERPRISE_SSO_ONLY(self) -> bool:
        return self._ENTERPRISE_SSO_ONLY

    @property
    def REQUIRE_ADMIN_MFA(self) -> bool:
        return self._REQUIRE_ADMIN_MFA

    @property
    def REQUIRE_PHISHING_RESISTANT_MFA(self) -> bool:
        return self._REQUIRE_PHISHING_RESISTANT_MFA

    @property
    def EDGE_REQUIRE_NODE_CERTIFICATE(self) -> bool:
        return self._EDGE_REQUIRE_NODE_CERTIFICATE

    @property
    def EDGE_REQUIRE_ATTESTATION(self) -> bool:
        return self._EDGE_REQUIRE_ATTESTATION

    @property
    def ENTERPRISE_IDENTITY_PROVIDERS(self) -> List[str]:
        return self._ENTERPRISE_IDENTITY_PROVIDERS

    @property
    def ENTERPRISE_DEFAULT_USER_ROLE(self) -> str:
        return self._ENTERPRISE_DEFAULT_USER_ROLE

    @property
    def ENTERPRISE_DEFAULT_API_KEY_ROLE(self) -> str:
        return self._ENTERPRISE_DEFAULT_API_KEY_ROLE

    @property
    def TOKEN_HARDENING(self) -> bool:
        return self._TOKEN_HARDENING

    @property
    def NETWORK_GATING(self) -> bool:
        return self._NETWORK_GATING

    @property
    def VALIDATE_STRICT(self) -> bool:
        return self._VALIDATE_STRICT

    @property
    def ENCRYPT_AUDIT_PAYLOAD(self) -> bool:
        return self._ENCRYPT_AUDIT_PAYLOAD

    @property
    def DATABASE_PATH(self) -> Path:
        return self._DATABASE_PATH

    @property
    def LOG_LEVEL(self) -> str:
        return self._LOG_LEVEL

    @property
    def JSON_LOGGING(self) -> bool:
        return self._JSON_LOGGING

    @property
    def METRICS_ENABLED(self) -> bool:
        return self._METRICS_ENABLED

    @property
    def METRICS_PORT(self) -> int:
        return self._METRICS_PORT

    @property
    def RATE_LIMIT_ENABLED(self) -> bool:
        return self._RATE_LIMIT_ENABLED

    @property
    def RATE_LIMIT_PER_MINUTE(self) -> int:
        return self._RATE_LIMIT_PER_MINUTE

    @property
    def RATE_LIMIT_PER_HOUR(self) -> int:
        return self._RATE_LIMIT_PER_HOUR

    @property
    def CORS_ORIGINS(self) -> List[str]:
        return self._CORS_ORIGINS

    @property
    def HOST(self) -> str:
        return self._HOST

    @property
    def PORT(self) -> int:
        return self._PORT

    @property
    def WORKERS(self) -> int:
        return self._WORKERS

    @property
    def BUILD_UI(self) -> bool:
        return self._BUILD_UI

    @property
    def UI_REPO_URL(self) -> str:
        return self._UI_REPO_URL

    @property
    def CLAWDBOT_GATEWAY_URL(self) -> Optional[str]:
        return self._CLAWDBOT_GATEWAY_URL

    @property
    def CLAWDBOT_GATEWAY_TOKEN(self) -> Optional[str]:
        return self._CLAWDBOT_GATEWAY_TOKEN

    @property
    def DEFAULT_CLAWDBOT_CREDENTIAL_ID(self) -> str:
        return self._DEFAULT_CLAWDBOT_CREDENTIAL_ID

    @property
    def CLAWDBOT_CREDENTIAL_ID(self) -> str:
        return self._CLAWDBOT_CREDENTIAL_ID

    @property
    def STRIPE_SECRET_KEY(self) -> Optional[str]:
        return self._STRIPE_SECRET_KEY

    @property
    def STRIPE_WEBHOOK_SECRET(self) -> Optional[str]:
        return self._STRIPE_WEBHOOK_SECRET

    @property
    def STRIPE_PRICE_SCALE(self) -> Optional[str]:
        return self._STRIPE_PRICE_SCALE

    @property
    def STRIPE_PRICE_PRO(self) -> Optional[str]:
        return self._STRIPE_PRICE_PRO

    @property
    def STRIPE_PAYMENT_LINK_SCALE(self) -> Optional[str]:
        return self._STRIPE_PAYMENT_LINK_SCALE

    @property
    def STRIPE_PAYMENT_LINK_PRO(self) -> Optional[str]:
        return self._STRIPE_PAYMENT_LINK_PRO

    @property
    def EDON_APP_URL(self) -> str:
        return self._EDON_APP_URL

    @property
    def CLERK_SECRET_KEY(self) -> Optional[str]:
        return self._CLERK_SECRET_KEY

    @property
    def MAG_ENABLED(self) -> bool:
        return self._MAG_ENABLED

    @property
    def MAG_URL(self) -> str:
        return self._MAG_URL

    @property
    def MAG_TIMEOUT_S(self) -> float:
        return self._MAG_TIMEOUT_S

    @property
    def MAG_ENFORCE_PATHS(self) -> List[str]:
        return self._MAG_ENFORCE_PATHS

    @property
    def DEMO_MODE(self) -> bool:
        return self._DEMO_MODE

    @property
    def DEMO_TENANT_ID(self) -> str:
        return self._DEMO_TENANT_ID

    @property
    def DEMO_API_KEY(self) -> str:
        return self._DEMO_API_KEY

    @property
    def CAV_URL(self) -> str:
        return self._CAV_URL

    @property
    def CAV_ENABLED(self) -> bool:
        return self._CAV_ENABLED

    @property
    def TELEGRAM_BOT_SECRET(self) -> Optional[str]:
        return self._TELEGRAM_BOT_SECRET

    @property
    def TELEGRAM_CONNECT_TTL_MIN(self) -> int:
        return self._TELEGRAM_CONNECT_TTL_MIN

    @property
    def CONNECT_BASE_URL(self) -> str:
        return self._CONNECT_BASE_URL

    @property
    def GOOGLE_CLIENT_ID(self) -> Optional[str]:
        return self._GOOGLE_CLIENT_ID

    @property
    def GOOGLE_CLIENT_SECRET(self) -> Optional[str]:
        return self._GOOGLE_CLIENT_SECRET

    @property
    def HOME_ASSISTANT_BASE_URL(self) -> str:
        return self._HOME_ASSISTANT_BASE_URL

    @property
    def HOME_ASSISTANT_TOKEN(self) -> Optional[str]:
        return self._HOME_ASSISTANT_TOKEN

    @property
    def HOME_ASSISTANT_CLIENT_ID(self) -> Optional[str]:
        return self._HOME_ASSISTANT_CLIENT_ID

    @property
    def HOME_ASSISTANT_CLIENT_SECRET(self) -> Optional[str]:
        return self._HOME_ASSISTANT_CLIENT_SECRET

    @classmethod
    def validate(cls) -> List[str]:
        warnings = []
        instance = cls()

        # Production checks
        if instance.CREDENTIALS_STRICT:
            if not instance.AUTH_ENABLED:
                warnings.append("EDON_CREDENTIALS_STRICT=true but EDON_AUTH_ENABLED=false")

            if instance.API_TOKEN == "your-secret-token":
                warnings.append("Using default API token! Change EDON_API_TOKEN in production")

        if instance.TOKEN_HARDENING and not instance.CREDENTIALS_STRICT:
            warnings.append(
                "EDON_TOKEN_HARDENING=true but EDON_CREDENTIALS_STRICT=false. "
                "Set EDON_CREDENTIALS_STRICT=true for full protection"
            )

        if instance.is_production() and not instance.ENCRYPT_AUDIT_PAYLOAD:
            warnings.append("EDON_ENCRYPT_AUDIT_PAYLOAD must be true in production")

        if "*" in instance.CORS_ORIGINS:
            warnings.append(
                "CORS allows all origins (*). Set EDON_CORS_ORIGINS to specific origins "
                "(e.g., http://localhost:3000,http://localhost:5173)"
            )

        # Not warning for ALLOW_ENV_TOKEN_IN_PROD=false in prod — that's the secure default.
        # Set EDON_ALLOW_ENV_TOKEN_IN_PROD=true only if you need bootstrap (e.g. Telegram).

        if instance.MAG_ENABLED and not instance.MAG_URL:
            warnings.append("EDON_MAG_ENABLED=true but EDON_MAG_URL is empty")

        return warnings

    @classmethod
    def is_production(cls) -> bool:
        instance = cls()
        # Your existing rule, keep it
        return instance._ENVIRONMENT == "production" or (instance.CREDENTIALS_STRICT and instance.AUTH_ENABLED)

    def enterprise_violations(self) -> List[str]:
        """Return hard blockers for an enterprise production deployment."""
        violations: List[str] = []
        if not self.is_production():
            return violations

        if not self.AUTH_ENABLED:
            violations.append("EDON_AUTH_ENABLED must be true in production")

        if not self.API_TOKEN or self.API_TOKEN in {
            "your-secret-token",
            "your-secret-token-change-me",
            "production-token-change-me",
            "change-me",
        }:
            violations.append("EDON_API_TOKEN must be set to a non-default value in production")

        if self.ALLOW_ENV_TOKEN_IN_PROD:
            violations.append("EDON_ALLOW_ENV_TOKEN_IN_PROD must be false in production")

        if not self.TOKEN_BINDING_ENABLED:
            violations.append("EDON_TOKEN_BINDING_ENABLED must be true in production")

        if not self.RATE_LIMIT_ENABLED:
            violations.append("EDON_RATE_LIMIT_ENABLED must be true in production")

        if "*" in self.CORS_ORIGINS:
            violations.append("EDON_CORS_ORIGINS cannot include '*' in production")

        database_url = (os.getenv("DATABASE_URL") or "").strip()
        if not database_url.startswith(("postgresql://", "postgres://")):
            violations.append("DATABASE_URL must point to PostgreSQL in production")

        encryption_key = (os.getenv("EDON_DB_ENCRYPTION_KEY") or "").strip()
        if not encryption_key:
            violations.append("EDON_DB_ENCRYPTION_KEY must be set in production")

        if not self.ENCRYPT_AUDIT_PAYLOAD:
            violations.append("EDON_ENCRYPT_AUDIT_PAYLOAD must be true in production")

        clerk_configured = any(
            (os.getenv(name) or "").strip()
            for name in ("CLERK_SECRET_KEY", "CLERK_PUBLIC_KEY", "CLERK_JWKS_URL")
        )
        if clerk_configured:
            issuer = (os.getenv("CLERK_ISSUER") or "").strip()
            audience = (os.getenv("CLERK_AUDIENCE") or "").strip()
            if not issuer or not audience:
                violations.append("CLERK_ISSUER and CLERK_AUDIENCE must be set when Clerk auth is enabled")

        if self.ENTERPRISE_MODE:
            if not self.ENTERPRISE_SSO_ONLY:
                violations.append("EDON_ENTERPRISE_SSO_ONLY must be true in enterprise mode")
            if not self.REQUIRE_ADMIN_MFA:
                violations.append("EDON_REQUIRE_ADMIN_MFA must be true in enterprise mode")
            if not self.REQUIRE_PHISHING_RESISTANT_MFA:
                violations.append("EDON_REQUIRE_PHISHING_RESISTANT_MFA must be true in enterprise mode")
            if not self.EDGE_REQUIRE_NODE_CERTIFICATE:
                violations.append("EDON_EDGE_REQUIRE_NODE_CERTIFICATE must be true in enterprise mode")
            if not self.EDGE_REQUIRE_ATTESTATION:
                violations.append("EDON_EDGE_REQUIRE_ATTESTATION must be true in enterprise mode")
            if not self.ENTERPRISE_IDENTITY_PROVIDERS:
                violations.append("EDON_ENTERPRISE_IDENTITY_PROVIDERS must list at least one provider in enterprise mode")
            if not self.CLERK_SECRET_KEY:
                violations.append("CLERK_SECRET_KEY must be set in enterprise mode")
            if not issuer or not audience:
                violations.append("CLERK_ISSUER and CLERK_AUDIENCE must be set in enterprise mode")

        return violations

    def assert_enterprise_ready(self) -> None:
        violations = self.enterprise_violations()
        if violations:
            raise RuntimeError("Enterprise production checks failed: " + "; ".join(violations))


# Global config instance (created AFTER .env is loaded)
config = Config()
