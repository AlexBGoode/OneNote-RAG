import msal
import requests
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any


class OneNoteAuth:
    def __init__(
        self, token_path: Optional[str] = None, client_id: Optional[str] = None
    ):
        """
        Initialize auth handler for both local and container environments.

        Args:
            token_path: Optional custom path for refresh token storage.
                        If None, auto-detects environment:
                        - Docker: /run/secrets/ms_refresh_token
                        - Local: ~/.onenote_rag/refresh_token
            client_id: Optional Microsoft Client ID. If None:
                       1. Checks environment variable MS_CLIENT_ID
                       2. Loads from .env file for local dev (if exists)
        """
        # Smart environment detection
        self.is_container = os.path.exists("/.dockerenv") or os.path.exists(
            "/run/.containerenv"
        )

        # Load client_id with fallback
        self.client_id = self._get_client_id(client_id)

        self.tenant_id = "common"
        self.scope = ["Notes.Read"]

        # Smart token path resolution
        self.token_path = self._resolve_token_path(token_path)

        self.app = msal.PublicClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
        )
        self.refresh_token = self._load_refresh_token()

    def _get_client_id(self, client_id: Optional[str]) -> str:
        """Get client ID with proper fallback strategy"""
        # Priority 1: Explicit argument
        if client_id:
            return client_id

        # Priority 2: Environment variable (works everywhere)
        env_client_id = os.getenv("MS_CLIENT_ID")
        if env_client_id:
            return env_client_id

        # Priority 3: .env file for local development only
        if not self.is_container:
            try:
                from dotenv import load_dotenv

                load_dotenv()
                env_client_id = os.getenv("MS_CLIENT_ID")
                if env_client_id:
                    return env_client_id
            except ImportError:
                pass  # dotenv not installed, skip

        raise ValueError(
            "MS_CLIENT_ID must be set. Options:\n"
            "1. Pass as argument: OneNoteAuth(client_id='...')\n"
            "2. Set environment variable: export MS_CLIENT_ID='...'\n"
            "3. Create .env file for local development (only if not in container)"
        )

    def _resolve_token_path(self, token_path: Optional[str]) -> Path:
        """Resolve token storage path based on environment"""
        if token_path:
            return Path(token_path)

        # Docker production path
        docker_path = Path("/run/secrets/ms_refresh_token")
        if docker_path.parent.exists():
            return docker_path

        # Local development path
        return Path.home() / ".onenote_rag" / "refresh_token"

    def _ensure_token_dir(self) -> None:
        """Create token directory with secure permissions"""
        if not self.token_path.parent.exists():
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            if os.name != "nt":
                os.chmod(self.token_path.parent, 0o700)

    def _load_refresh_token(self) -> Optional[str]:
        """Load persisted refresh token"""
        try:
            if self.token_path.exists():
                token = self.token_path.read_text().strip()
                print(f"✓ Loaded refresh token from {self.token_path}")
                return token if token else None
        except Exception as e:
            print(f"⚠ Warning: Could not load token from {self.token_path}: {e}")
        return None

    def _save_refresh_token(self, token: str) -> None:
        """Persist refresh token securely"""
        try:
            self._ensure_token_dir()
            self.token_path.write_text(token)
            if os.name != "nt":
                self.token_path.chmod(0o600)
            print(f"✓ Saved refresh token to {self.token_path}")
        except Exception as e:
            print(f"✗ Error saving token to {self.token_path}: {e}")
            raise

    def get_access_token(self) -> str:
        """Get access token using refresh token or initiate device flow"""
        if self.refresh_token:
            print("🔄 Attempting silent token refresh...")
            result = self.app.acquire_token_by_refresh_token(
                self.refresh_token, scopes=self.scope
            )
            if "access_token" in result:
                print("✓ Token refreshed silently")
                if "refresh_token" in result:
                    self._save_refresh_token(result["refresh_token"])
                return result["access_token"]
            else:
                print(
                    f"⚠ Silent refresh failed: {result.get('error_description', 'Unknown error')}"
                )
                print("   Falling back to device code flow...")

        # Device code flow
        flow = self.app.initiate_device_flow(scopes=self.scope)
        if "user_code" not in flow:
            raise ValueError(f"Failed to create device flow: {flow}")

        print("\n" + "=" * 60)
        print("📱 MICROSOFT AUTHENTICATION REQUIRED")
        print("=" * 60)
        print(f"1. Open on any device: {flow['verification_uri']}")
        print(f"2. Enter this code:    {flow['user_code']}")
        print("=" * 60 + "\n")

        result = self.app.acquire_token_by_device_flow(flow)

        if "access_token" in result:
            print("✓ Authentication successful!")
            if "refresh_token" in result:
                self._save_refresh_token(result["refresh_token"])
            return result["access_token"]
        else:
            error = result.get(
                "error_description", result.get("error", "Unknown error")
            )
            raise Exception(f"Authentication failed: {error}")

    def get_notebooks(self, access_token: Optional[str] = None) -> Dict[str, Any]:
        """Get OneNote notebooks"""
        token = access_token or self.get_access_token()
        resp = requests.get(
            "https://graph.microsoft.com/v1.0/me/onenote/notebooks",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()


# Command-line interface
def main():
    """CLI entry point - works everywhere with the same code"""
    import argparse

    parser = argparse.ArgumentParser(description="OneNote Authentication")
    parser.add_argument(
        "--client-id", help="Microsoft Client ID (optional, uses MS_CLIENT_ID env var)"
    )
    parser.add_argument("--token-path", help="Custom path for refresh token storage")

    # No API flag - always test
    args = parser.parse_args()

    try:
        auth = OneNoteAuth(token_path=args.token_path, client_id=args.client_id)

        token = auth.get_access_token()

        print("\n" + "=" * 60)
        print("✅ ACCESS TOKEN OBTAINED")
        print("=" * 60)
        print(f"Token preview: {token[:10]}...{token[-10:]}")
        print(f"Token saved to: {auth.token_path}")
        print("=" * 60 + "\n")

        # Always test API
        print("🔍 Testing OneNote API call...")
        notebooks_data = auth.get_notebooks(token)
        notebooks = notebooks_data.get("value", [])
        print(f"✅ Successfully retrieved {len(notebooks)} notebook(s):\n")
        for nb in notebooks:
            print(f"  • {nb['displayName']} (ID: {nb['id']})")

    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
