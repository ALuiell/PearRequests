import logging
import sys

logger = logging.getLogger(__name__)

CREDENTIAL_TARGET_NAME = "TwitchPearSongRequests/TwitchOAuth"

class TwitchCredentialStore:
    """Securely stores the Twitch OAuth token using Windows Credential Manager."""

    @staticmethod
    def get_token() -> str | None:
        if sys.platform != "win32":
            return None
        try:
            import win32cred
            cred = win32cred.CredRead(CREDENTIAL_TARGET_NAME, win32cred.CRED_TYPE_GENERIC)
            blob = cred.get('CredentialBlob', b"")
            if isinstance(blob, bytes):
                token_str = blob.decode('utf-8', errors='ignore')
                return token_str.replace('\x00', '')
            return str(blob or "")
        except Exception as e:
            logger.debug(f"Failed to read token from Credential Manager (or not found).")
            return None

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
