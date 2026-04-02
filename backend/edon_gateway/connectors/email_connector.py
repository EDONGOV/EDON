"""Email connector - sandboxed (writes to file instead of sending)."""

import json
import os
from pathlib import Path
from datetime import datetime, UTC
from typing import Dict, Any, Optional


class EmailConnector:
    """Email connector that writes to sandbox instead of actually sending.
    
    This proves "EDON is the only path to side effects" - the agent cannot
    send emails directly because it doesn't have the credentials/access.
    Only EDON can execute email operations.
    """
    
    def __init__(self, sandbox_dir: Path = Path("sandbox/emails"), credential_id: Optional[str] = None):
        """Initialize email connector.
        
        Args:
            sandbox_dir: Directory to write email drafts/sends (sandboxed)
            credential_id: Optional credential ID to load from database
        """
        self.sandbox_dir = sandbox_dir
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self.credential_id = credential_id
        self._credentials = None
        
        # Load credentials if credential_id provided
        if credential_id:
            self._load_credentials()
    
    def _load_credentials(self):
        """Load credentials from database.
        
        Raises:
            RuntimeError: If EDON_CREDENTIALS_STRICT=true and credential not found
        """
        from ..persistence import get_db
        db = get_db()
        credential = db.get_credential(self.credential_id)
        
        if credential:
            self._credentials = credential["credential_data"]
            # Update last_used_at
            db.update_credential_last_used(self.credential_id)
            return
        
        # Check strict mode
        credentials_strict = os.getenv("EDON_CREDENTIALS_STRICT", "false").lower() == "true"
        
        if credentials_strict:
            # PROD mode: fail closed - no fallback
            raise RuntimeError(
                f"Credential '{self.credential_id}' not found in database. "
                "EDON_CREDENTIALS_STRICT=true requires all credentials to be in database. "
                "Set EDON_CREDENTIALS_STRICT=false for development mode."
            )
        
        # DEV mode: fallback to environment variables (for development only)
        self._credentials = {
            "smtp_host": os.getenv("SMTP_HOST", "localhost"),
            "smtp_port": int(os.getenv("SMTP_PORT", "587")),
            "smtp_user": os.getenv("SMTP_USER", ""),
            "smtp_password": os.getenv("SMTP_PASSWORD", ""),
        }
    
    def draft(self, recipients: list, subject: str, body: str, **kwargs) -> Dict[str, Any]:
        """Draft an email (sandboxed - writes to file).
        
        Args:
            recipients: List of recipient email addresses
            subject: Email subject
            body: Email body
            **kwargs: Additional parameters
            
        Returns:
            Result dictionary with success status and draft_id
        """
        draft_id = f"draft_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S_%f')}"
        draft_file = self.sandbox_dir / f"{draft_id}.json"
        
        draft_data = {
            "draft_id": draft_id,
            "recipients": recipients,
            "subject": subject,
            "body": body,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "draft",
            **kwargs
        }
        
        with open(draft_file, 'w') as f:
            json.dump(draft_data, f, indent=2)
        
        return {
            "success": True,
            "draft_id": draft_id,
            "file_path": str(draft_file),
            "message": f"Email draft saved to {draft_file}"
        }
    
    def send(self, recipients: list, subject: str, body: str, **kwargs) -> Dict[str, Any]:
        """Send an email (sandboxed - writes to sent file).
        
        In production, this would use SMTP/API credentials stored in EDON config.
        For now, it writes to a sandbox directory to prove execution path.
        
        Args:
            recipients: List of recipient email addresses
            subject: Email subject
            body: Email body
            **kwargs: Additional parameters
            
        Returns:
            Result dictionary with success status and message_id
        """
        message_id = f"msg_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S_%f')}"
        sent_file = self.sandbox_dir / "sent" / f"{message_id}.json"
        sent_file.parent.mkdir(parents=True, exist_ok=True)
        
        sent_data = {
            "message_id": message_id,
            "recipients": recipients,
            "subject": subject,
            "body": body,
            "sent_at": datetime.now(UTC).isoformat(),
            "status": "sent",
            "note": "Sandboxed - would send via SMTP/API in production",
            **kwargs
        }
        
        with open(sent_file, 'w') as f:
            json.dump(sent_data, f, indent=2)
        
        return {
            "success": True,
            "message_id": message_id,
            "file_path": str(sent_file),
            "message": f"Email sent (sandboxed) to {len(recipients)} recipient(s)"
        }


# Global instance (credentials would be loaded from EDON config in production)
email_connector = EmailConnector()
