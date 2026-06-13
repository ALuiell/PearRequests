import sys
import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread, QTimer

from app.config import load_config
from app.logging_setup import setup_logging
from app.ui.main_window import MainWindow

from app.twitch_controller import TwitchController
from app.pear_client import PearWorker
from app.song_requests import SongRequestService

logger = logging.getLogger(__name__)

def main():
    import os
    os.environ["QT_QPA_PLATFORM"] = "windows:darkmode=1"

    setup_logging(logging.INFO)
    logger.info("Starting PearSongBot...")

    config = load_config()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Instantiate services
    twitch_ctrl = TwitchController(config)
    song_srv = SongRequestService(config)
    
    # Pear Worker Thread
    pear_thread = QThread()
    pear_worker = PearWorker(
        config.pear.base_url,
        config.pear.request_timeout_seconds,
        config.pear.auth_client_id,
    )
    pear_worker.moveToThread(pear_thread)
    pear_thread.started.connect(pear_worker.initialize)
    pear_thread.start()
    
    # Timer for periodic Pear health check
    pear_timer = QTimer()
    pear_timer.timeout.connect(pear_worker.check_health)
    pear_timer.start(10000)
    pear_state_timer = QTimer()
    pear_state_timer.timeout.connect(pear_worker.refresh_state)
    pear_state_timer.start(3000)

    # Wire signals
    song_srv.request_pear_add.connect(pear_worker.add_song_request)
    pear_worker.song_added.connect(song_srv.handle_pear_success)
    pear_worker.request_failed.connect(song_srv.handle_pear_failure)
    
    song_srv.request_pear_search.connect(pear_worker.request_search)
    song_srv.request_pear_queue.connect(pear_worker.request_queue)
    song_srv.request_pear_current.connect(pear_worker.request_current_song)
    song_srv.request_pear_resync.connect(pear_worker.refresh_state)
    song_srv.request_pear_skip.connect(pear_worker.request_skip)
    song_srv.request_pear_remove.connect(pear_worker.request_remove)
    song_srv.request_pear_remove_index.connect(pear_worker.remove_queue_index)
    song_srv.request_pear_move_index.connect(pear_worker.move_queue_index)
    
    pear_worker.search_completed.connect(song_srv.handle_search_completed)
    pear_worker.queue_fetched.connect(song_srv.handle_queue_fetched)
    pear_worker.current_song_fetched.connect(song_srv.handle_current_song_fetched)
    pear_worker.action_completed.connect(song_srv.handle_action_completed)
    pear_worker.action_failed.connect(song_srv.handle_action_failed)
    pear_worker.queue_updated.connect(song_srv.observe_queue_updated)
    pear_worker.current_song_updated.connect(song_srv.observe_current_song_updated)
    pear_worker.queue_operation_completed.connect(song_srv.handle_queue_operation_completed)
    pear_worker.queue_operation_failed.connect(song_srv.handle_queue_operation_failed)
    song_srv.send_chat_message.connect(twitch_ctrl.send_chat_message)
    
    connected_irc_worker = {"worker": None}

    def on_irc_worker_started():
        if twitch_ctrl.irc_worker and connected_irc_worker["worker"] is not twitch_ctrl.irc_worker:
            twitch_ctrl.irc_worker.chat_message.connect(song_srv.handle_chat_message)
            connected_irc_worker["worker"] = twitch_ctrl.irc_worker
    
    twitch_ctrl.irc_state_changed.connect(lambda s: on_irc_worker_started() if s == "connecting" else None)

    # MainWindow
    window = MainWindow(config, twitch_ctrl, pear_worker, song_srv)
    window.show()
    QTimer.singleShot(0, twitch_ctrl.try_auto_connect)

    # Exec loop
    exit_code = app.exec()
    
    # Cleanup
    pear_worker.stop()
    pear_thread.quit()
    pear_thread.wait(500)
    
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
