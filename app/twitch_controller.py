import logging
from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.config import AppConfig, save_config
from app.twitch_credentials import TwitchCredentialStore
from app.twitch_auth import TwitchAuthWorker
from app.twitch_irc import TwitchIrcWorker

logger = logging.getLogger(__name__)

class TwitchController(QObject):
    # Signals for UI
    auth_state_changed = Signal(bool, str) # is_authenticated, username
    irc_state_changed = Signal(str)
    log_message = Signal(str, str)
    do_send_chat = Signal(str)

    def __init__(self, config: AppConfig):
        super().__init__()
        self.config = config
        self.auth_thread: QThread | None = None
        self.auth_worker: TwitchAuthWorker | None = None
        
        self.irc_thread: QThread | None = None
        self.irc_worker: TwitchIrcWorker | None = None

    @Slot()
    def start_oauth(self):
        if self.auth_thread and self.auth_thread.isRunning():
            self.log_message.emit("warning", "OAuth is already running.")
            return

        self.auth_thread = QThread()
        self.auth_worker = TwitchAuthWorker(self.config.twitch.client_id)
        self.auth_worker.moveToThread(self.auth_thread)
        
        self.auth_worker.auth_success.connect(self._on_auth_success)
        self.auth_worker.auth_failed.connect(self._on_auth_failed)
        
        self.auth_thread.started.connect(self.auth_worker.start_oauth)
        self.auth_thread.start()
        self.log_message.emit("info", "Starting browser for Twitch OAuth...")

    @Slot(str, str)
    def _on_auth_success(self, login: str, user_id: str):
        self.log_message.emit("info", f"Successfully authenticated as {login}")
        self.config.twitch.username = login
        self.config.twitch.user_id = user_id
        save_config(self.config)
        self.auth_state_changed.emit(True, login)
        self._cleanup_auth_thread()

    @Slot(str)
    def _on_auth_failed(self, error: str):
        self.log_message.emit("error", f"OAuth Failed: {error}")
        self.auth_state_changed.emit(False, "")
        self._cleanup_auth_thread()

    def _cleanup_auth_thread(self):
        if self.auth_thread:
            self.auth_thread.quit()
            self.auth_thread.wait(500)
            self.auth_thread = None
            self.auth_worker = None

    @Slot()
    def disconnect_account(self):
        TwitchCredentialStore.delete_token()
        self.config.twitch.username = ""
        self.config.twitch.user_id = ""
        save_config(self.config)
        self.stop_bot()
        self.auth_state_changed.emit(False, "")
        self.log_message.emit("info", "Twitch account disconnected.")

    @Slot()
    def start_bot(self):
        if self.irc_thread and self.irc_thread.isRunning():
            self.log_message.emit("warning", "Bot is already running.")
            return
            
        token, token_status = TwitchCredentialStore.read_token()
        if not token:
            if token_status == "import_failed":
                self.log_message.emit("error", "Cannot start bot: Twitch token storage is unavailable in this build.")
            elif token_status == "read_failed":
                self.log_message.emit("error", "Cannot start bot: Twitch token could not be read from Windows Credential Manager.")
            elif token_status == "missing":
                self.log_message.emit("error", "Cannot start bot: No Twitch token found.")
            else:
                self.log_message.emit("error", "Cannot start bot: Twitch token is unavailable on this platform.")
            return

        channel = self.config.twitch.target_channel or self.config.twitch.username
        if not channel:
            self.log_message.emit("error", "Cannot start bot: Target channel is empty.")
            return

        self.irc_thread = QThread()
        self.irc_worker = TwitchIrcWorker(self.config.twitch.username, channel, token)
        self.irc_worker.moveToThread(self.irc_thread)
        
        self.irc_worker.state_changed.connect(self.irc_state_changed)
        self.irc_worker.log_message.connect(self.log_message)
        
        self.irc_thread.started.connect(self.irc_worker.start_connection)
        self.irc_thread.start()

    @Slot(str)
    def send_chat_message(self, text: str):
        if self.irc_worker:
            self.irc_worker.send_privmsg(text)

    @Slot()
    def stop_bot(self):
        if self.irc_worker:
            self.irc_worker.stop()
        if self.irc_thread:
            self.irc_thread.quit()
            self.irc_thread.wait(500)
            self.irc_thread = None
            self.irc_worker = None
        self.irc_state_changed.emit("disconnected")
