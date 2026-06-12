import logging
import sys
from typing import Literal

logger = logging.getLogger(__name__)

CREDENTIAL_TARGET_NAME = "TwitchPearSongRequests/TwitchOAuth"
TokenStatus = Literal["ok", "missing", "unsupported_platform", "import_failed", "read_failed"]

class TwitchCredentialStore:
    """Securely stores the Twitch OAuth token using Windows Credential Manager."""

    @staticmethod
    def read_token() -> tuple[str | None, TokenStatus]:
        if sys.platform != "win32":
            return None, "unsupported_platform"
        try:
            import win32cred
        except Exception as e:
            logger.warning(f"Failed to import win32cred for Twitch token storage: {type(e).__name__}: {e}")
            return None, "import_failed"

        try:
            cred = win32cred.CredRead(CREDENTIAL_TARGET_NAME, win32cred.CRED_TYPE_GENERIC)
            blob = cred.get('CredentialBlob', b"")
            if isinstance(blob, bytes):
                token_str = blob.decode('utf-8', errors='ignore')
                token_str = token_str.replace('\x00', '').strip()
            else:
                token_str = str(blob or "").strip()

            if not token_str:
                logger.warning("Twitch token entry was found in Credential Manager but it is empty.")
                return None, "missing"
            return token_str, "ok"
        except Exception as e:
            message = str(e).lower()
            if "not found" in message or "element not found" in message:
                logger.info("No Twitch token entry found in Windows Credential Manager.")
                return None, "missing"
            logger.warning(f"Failed to read Twitch token from Credential Manager: {type(e).__name__}: {e}")
            return None, "read_failed"

    @staticmethod
    def get_token() -> str | None:
        token, _ = TwitchCredentialStore.read_token()
        return token

    @staticmethod
    def set_token(token: str) -> None:
        if sys.platform != "win32":
            return
        try:
            import win32cred
            cred = {
                'Type': win32cred.CRED_TYPE_GENERIC,
                'TargetName': CREDENTIAL_TARGET_NAME,
                'CredentialBlob': token,
                'Persist': win32cred.CRED_PERSIST_LOCAL_MACHINE,
                'UserName': 'TwitchBot'
            }
            win32cred.CredWrite(cred, 0)
            logger.debug("Token securely written to Credential Manager.")
        except Exception as e:
            logger.error("Failed to write token to Credential Manager.")
            raise

    @staticmethod
    def delete_token() -> None:
        if sys.platform != "win32":
            return
        try:
            import win32cred
            win32cred.CredDelete(CREDENTIAL_TARGET_NAME, win32cred.CRED_TYPE_GENERIC, 0)
            logger.debug("Token removed from Credential Manager.")
        except Exception as e:
            logger.debug(f"Failed to delete token from Credential Manager (or not found).")
