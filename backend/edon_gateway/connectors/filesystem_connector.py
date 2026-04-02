"""Filesystem connector - sandboxed (only writes to sandbox directory)."""

import json
import os
from pathlib import Path
from datetime import datetime, UTC
from typing import Dict, Any, Optional


class FilesystemConnector:
    """Filesystem connector that only allows writes to sandbox directory.
    
    This proves "EDON is the only path to side effects" - the agent cannot
    write files directly because it doesn't have access outside the sandbox.
    Only EDON can execute filesystem operations.
    """
    
    def __init__(self, sandbox_dir: Path = Path("sandbox/filesystem"), credential_id: Optional[str] = None):
        """Initialize filesystem connector.
        
        Args:
            sandbox_dir: Sandbox directory for file operations
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
            "allowed_paths": os.getenv("FILESYSTEM_ALLOWED_PATHS", "").split(","),
            "max_file_size": int(os.getenv("FILESYSTEM_MAX_FILE_SIZE", "10485760")),  # 10 MB
        }
    
    def read_file(self, path: str) -> Dict[str, Any]:
        """Read a file (sandboxed - only from sandbox directory).
        
        Args:
            path: File path (relative to sandbox)
            
        Returns:
            Result dictionary with file contents
        """
        # Security: Only allow reading from sandbox
        file_path = self.sandbox_dir / path.lstrip('/')
        
        # Prevent directory traversal
        if not str(file_path.resolve()).startswith(str(self.sandbox_dir.resolve())):
            raise ValueError(f"Path outside sandbox: {path}")
        
        if not file_path.exists():
            return {
                "success": False,
                "error": f"File not found: {path}"
            }
        
        try:
            content = file_path.read_text()
            return {
                "success": True,
                "path": str(file_path),
                "content": content,
                "size": len(content)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """Write a file (sandboxed - only to sandbox directory).
        
        Args:
            path: File path (relative to sandbox)
            content: File content
            
        Returns:
            Result dictionary with success status
        """
        # Security: Only allow writing to sandbox
        file_path = self.sandbox_dir / path.lstrip('/')
        
        # Prevent directory traversal
        if not str(file_path.resolve()).startswith(str(self.sandbox_dir.resolve())):
            raise ValueError(f"Path outside sandbox: {path}")
        
        # Create parent directories
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            file_path.write_text(content)
            return {
                "success": True,
                "path": str(file_path),
                "size": len(content),
                "message": f"File written to {file_path}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def delete_file(self, path: str) -> Dict[str, Any]:
        """Delete a file (sandboxed - only from sandbox directory).
        
        Args:
            path: File path (relative to sandbox)
            
        Returns:
            Result dictionary with success status
        """
        # Security: Only allow deleting from sandbox
        file_path = self.sandbox_dir / path.lstrip('/')
        
        # Prevent directory traversal
        if not str(file_path.resolve()).startswith(str(self.sandbox_dir.resolve())):
            raise ValueError(f"Path outside sandbox: {path}")
        
        if not file_path.exists():
            return {
                "success": False,
                "error": f"File not found: {path}"
            }
        
        try:
            file_path.unlink()
            return {
                "success": True,
                "path": str(file_path),
                "message": f"File deleted: {file_path}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# Global instance
filesystem_connector = FilesystemConnector()
