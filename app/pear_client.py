import logging
import httpx
from PySide6.QtCore import QObject, QThread, Signal, Slot
from typing import Any

logger = logging.getLogger(__name__)

class PearClient:
    """Synchronous HTTP client for interacting with the Pear Desktop API."""
    def __init__(self, base_url: str, timeout: int = 8, auth_client_id: str = "twitch-pear-song-requests"):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.Client(timeout=self.timeout)
        self.auth_client_id = auth_client_id
        self.access_token: str | None = None

    def _request(self, method: str, path: str, retry_on_unauthorized: bool = True, **kwargs) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        res = self.client.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
        if res.status_code == 401 and retry_on_unauthorized and self._authenticate():
            return self._request(method, path, retry_on_unauthorized=False, **kwargs)
        return res

    def _authenticate(self) -> bool:
        try:
            res = self.client.post(f"{self.base_url}/auth/{self.auth_client_id}")
            res.raise_for_status()
            token = res.json().get("accessToken")
            if not token:
                logger.error("Pear auth endpoint did not return an access token.")
                return False
            self.access_token = token
            return True
        except Exception as e:
            logger.error(f"Failed to authenticate with Pear API: {e}")
            return False

    def is_available(self) -> bool:
        try:
            # A simple GET request to check if Pear is running and accessible
            res = self._request("GET", "/api/v1/queue")
            res.raise_for_status()
            return True
        except Exception as e:
            logger.debug(f"Pear health check failed: {e}")
            return False

    def add_song(self, video_id: str, insert_position: str = "INSERT_AT_END") -> dict[str, Any] | None:
        """Adds a track by video_id to the queue."""
        try:
            payload = {
                "videoId": video_id,
                "insertPosition": insert_position
            }
            res = self._request("POST", "/api/v1/queue", json=payload)
            res.raise_for_status()
            return {"success": True, "videoId": video_id}
        except httpx.HTTPError as e:
            logger.error(f"HTTP Error adding song to Pear: {e}")
            return {"success": False, "error": str(e), "videoId": video_id}

    def get_queue(self) -> dict[str, Any] | None:
        try:
            res = self._request("GET", "/api/v1/queue")
            res.raise_for_status()
            return res.json()
        except Exception as e:
            logger.error(f"Failed to get queue: {e}")
            return None

    def get_current_song(self) -> dict[str, Any] | None:
        try:
            res = self._request("GET", "/api/v1/song")
            if res.status_code == 204:
                return {}
            res.raise_for_status()
            return res.json()
        except Exception as e:
            logger.error(f"Failed to get current song: {e}")
            return None

    def command_play(self) -> bool:
        try:
            res = self._request("POST", "/api/v1/play")
            res.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to send play command: {e}")
            return False

    def command_pause(self) -> bool:
        try:
            res = self._request("POST", "/api/v1/pause")
            res.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to send pause command: {e}")
            return False

    def command_toggle_play(self) -> bool:
        try:
            res = self._request("POST", "/api/v1/toggle-play")
            res.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to send play/pause toggle command: {e}")
            return False

    def command_next(self) -> bool:
        try:
            res = self._request("POST", "/api/v1/next")
            res.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to send next command: {e}")
            return False

    def remove_song(self, index: int) -> bool:
        try:
            res = self._request("DELETE", f"/api/v1/queue/{index}")
            res.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to remove song: {e}")
            return False

    def clear_queue(self) -> bool:
        try:
            res = self._request("DELETE", "/api/v1/queue")
            res.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to clear queue: {e}")
            return False

    def move_song(self, index: int, to_index: int) -> bool:
        try:
            res = self._request("PATCH", f"/api/v1/queue/{index}", json={"toIndex": to_index})
            res.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to move song: {e}")
            return False

    def search_song(self, query: str) -> dict[str, str] | None:
        try:
            res = self._request("POST", "/api/v1/search", json={"query": query})
            res.raise_for_status()
            data = res.json()

            def extract_text(value: Any) -> str:
                if isinstance(value, str):
                    return value.strip()
                if isinstance(value, dict):
                    runs = value.get("runs")
                    if isinstance(runs, list):
                        return "".join(
                            part.get("text", "")
                            for part in runs
                            if isinstance(part, dict)
                        ).strip()
                    text = value.get("text")
                    if isinstance(text, str):
                        return text.strip()
                return ""

            def extract_artist(value: Any) -> str:
                if not isinstance(value, dict):
                    return ""

                runs = value.get("runs", [])
                if not isinstance(runs, list):
                    return ""

                for run in runs:
                    if not isinstance(run, dict):
                        continue
                    text = run.get("text", "").strip()
                    endpoint = run.get("navigationEndpoint", {})
                    if text and isinstance(endpoint, dict) and endpoint.get("browseEndpoint"):
                        return text

                ignored_values = {"video", "song", "album", "single", "ep"}
                for run in runs:
                    if not isinstance(run, dict):
                        continue
                    text = run.get("text", "").strip()
                    normalized = text.lower()
                    if text and text != "•" and normalized not in ignored_values:
                        return text

                return ""

            def find_first_track(obj: Any) -> dict[str, str] | None:
                if isinstance(obj, dict):
                    video_id = obj.get("videoId")
                    if isinstance(video_id, str) and video_id:
                        title = extract_text(obj.get("title"))
                        artist = extract_artist(obj.get("subtitle")) or extract_artist(obj.get("shortBylineText"))

                        return {
                            "videoId": video_id,
                            "title": title,
                            "artist": artist,
                        }

                    for v in obj.values():
                        result = find_first_track(v)
                        if result:
                            return result
                elif isinstance(obj, list):
                    for item in obj:
                        result = find_first_track(item)
                        if result:
                            return result
                return None

            return find_first_track(data)
        except Exception as e:
            logger.error(f"Failed to search song: {e}")
            return None


class PearWorker(QObject):
    """QObject wrapper for running PearClient requests in a QThread."""
    
    # Signals
    state_changed = Signal(str)         # 'connected', 'unavailable', 'error'
    song_added = Signal(str, dict)      # request_id, Result of adding a song
    request_failed = Signal(str, str)   # request_id, safe message
    queue_updated = Signal(object)
    current_song_updated = Signal(dict)
    
    # Feature signals
    search_completed = Signal(str, object) # request_id, metadata
    queue_fetched = Signal(str, object)   # user_login, queue or None
    current_song_fetched = Signal(str, object) # user_login, song or None
    action_completed = Signal(str, str) # user_login, action
    action_failed = Signal(str, str, str) # user_login, action, safe message
    queue_operation_completed = Signal(str) # request_id
    queue_operation_failed = Signal(str, str) # request_id, safe message
    clear_queue_completed = Signal()
    clear_queue_failed = Signal(str)
    
    def __init__(self, base_url: str, timeout: int = 8, auth_client_id: str = "twitch-pear-song-requests"):
        super().__init__()
        self.base_url = base_url
        self.timeout = timeout
        self.auth_client_id = auth_client_id
        self.client: PearClient | None = None
        self.is_connected = False
        self._is_running = True

    @Slot()
    def initialize(self):
        """Called when thread starts."""
        self.client = PearClient(self.base_url, self.timeout, self.auth_client_id)
        self.check_health()

    def _extract_queue_renderer(self, item: object) -> dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        return (
            item.get("playlistPanelVideoRenderer")
            or item.get("playlistPanelVideoWrapperRenderer", {}).get("primaryRenderer", {}).get("playlistPanelVideoRenderer")
            or {}
        )

    def _extract_runs_text(self, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if not isinstance(value, dict):
            return ""

        runs = value.get("runs")
        if isinstance(runs, list):
            return "".join(
                part.get("text", "")
                for part in runs
                if isinstance(part, dict)
            ).strip()

        text = value.get("text")
        if isinstance(text, str):
            return text.strip()
        return ""

    def _build_song_from_renderer(self, renderer: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(renderer, dict):
            return {}

        song: dict[str, Any] = {}
        video_id = renderer.get("videoId")
        if isinstance(video_id, str) and video_id:
            song["videoId"] = video_id

        title = self._extract_runs_text(renderer.get("title"))
        if title:
            song["title"] = title

        artist = self._extract_runs_text(renderer.get("shortBylineText"))
        if artist:
            song["artist"] = artist
            song["author"] = artist

        is_paused = renderer.get("isPaused")
        if isinstance(is_paused, bool):
            song["isPaused"] = is_paused

        return song

    def _normalize_current_song(self, queue_data: object, song: object) -> dict[str, Any]:
        items = queue_data.get("items", []) if isinstance(queue_data, dict) else []
        selected_renderer: dict[str, Any] = {}
        for item in items:
            renderer = self._extract_queue_renderer(item)
            if renderer.get("selected") is True:
                selected_renderer = renderer
                break

        if not selected_renderer:
            return {}

        normalized = dict(song) if isinstance(song, dict) else {}
        selected_song = self._build_song_from_renderer(selected_renderer)

        selected_video_id = selected_song.get("videoId")
        current_video_id = normalized.get("videoId")
        if selected_video_id and current_video_id and selected_video_id != current_video_id:
            normalized = {}

        normalized.update({k: v for k, v in selected_song.items() if v})
        if "isPaused" in selected_song:
            normalized["isPaused"] = selected_song["isPaused"]
        return normalized

    @Slot()
    def check_health(self):
        if not self._is_running or not self.client: return
        is_up = self.client.is_available()
        
        if is_up != self.is_connected:
            self.is_connected = is_up
            self.state_changed.emit("connected" if is_up else "unavailable")
            self.refresh_state()

    @Slot()
    def refresh_state(self):
        if not self._is_running or not self.client: return
        if not self.is_connected:
            self.queue_updated.emit(None)
            self.current_song_updated.emit({})
            return
        queue_data = self.client.get_queue()
        self.queue_updated.emit(queue_data)
        song = self.client.get_current_song()
        self.current_song_updated.emit(self._normalize_current_song(queue_data, song))

    @Slot(str, str, str)
    def add_song_request(self, request_id: str, video_id: str, insert_position: str):
        if not self._is_running or not self.client: return

        current_song = self.client.get_current_song() or {}
        queue_before = self.client.get_queue() or {}
        should_autoplay = not isinstance(current_song, dict) or not current_song or not current_song.get("videoId")
        queue_was_empty = not isinstance(queue_before, dict) or not queue_before.get("items")

        result = self.client.add_song(video_id, insert_position)
        if result and result.get("success"):
            if should_autoplay:
                if queue_was_empty:
                    if not self.client.command_next():
                        logger.warning(f"Added viewer track {video_id} but failed to auto-start playback with next.")
                elif not self.client.command_play():
                    logger.warning(f"Added viewer track {video_id} but failed to auto-start playback.")
            self.song_added.emit(request_id, result)
            self.refresh_state()
        else:
            self.request_failed.emit(request_id, result.get("error", "Unknown Error") if result else "Unknown Error")

    @Slot()
    def command_play(self):
        if self._is_running and self.client:
            self.client.command_play()

    @Slot()
    def command_pause(self):
        if self._is_running and self.client:
            self.client.command_pause()

    @Slot()
    def command_toggle_play(self):
        if self._is_running and self.client:
            self.client.command_toggle_play()

    @Slot()
    def command_next(self):
        if self._is_running and self.client:
            self.client.command_next()

    @Slot()
    def command_clear_queue(self):
        if not self._is_running or not self.client:
            self.clear_queue_failed.emit("Pear client is not running.")
            return
        if self.client.clear_queue():
            self.clear_queue_completed.emit()
            self.refresh_state()
        else:
            self.clear_queue_failed.emit("Pear Desktop is unavailable or returned an error.")

    @Slot(str, str)
    def request_search(self, request_id: str, query: str):
        if not self._is_running or not self.client: return
        result = self.client.search_song(query) or {}
        self.search_completed.emit(request_id, result)

    @Slot(str)
    def request_queue(self, user_login: str):
        if not self._is_running or not self.client: return
        self.queue_fetched.emit(user_login, self.client.get_queue())

    @Slot(str)
    def request_current_song(self, user_login: str):
        if not self._is_running or not self.client: return
        queue_data = self.client.get_queue()
        song = self.client.get_current_song()
        self.current_song_fetched.emit(user_login, self._normalize_current_song(queue_data, song))

    @Slot(str)
    def request_skip(self, user_login: str):
        if not self._is_running or not self.client: return
        if self.client.command_next():
            self.action_completed.emit(user_login, "skip")
        else:
            self.action_failed.emit(user_login, "skip", "Pear Desktop is unavailable or returned an error.")

    @Slot(str, int)
    def request_remove(self, user_login: str, index: int):
        if not self._is_running or not self.client: return
        if self.client.remove_song(index):
            self.action_completed.emit(user_login, f"remove {index}")
            self.refresh_state()
        else:
            self.action_failed.emit(user_login, "remove", "Pear Desktop is unavailable or returned an error.")

    @Slot(str, int)
    def remove_queue_index(self, request_id: str, index: int):
        if not self._is_running or not self.client:
            self.queue_operation_failed.emit(request_id, "Pear client is not running.")
            return
        if self.client.remove_song(index):
            self.queue_operation_completed.emit(request_id)
            self.refresh_state()
        else:
            self.queue_operation_failed.emit(request_id, "Pear Desktop is unavailable or returned an error.")

    @Slot(str, int, int)
    def move_queue_index(self, request_id: str, index: int, to_index: int):
        if not self._is_running or not self.client:
            self.queue_operation_failed.emit(request_id, "Pear client is not running.")
            return
        if self.client.move_song(index, to_index):
            self.queue_operation_completed.emit(request_id)
            self.refresh_state()
        else:
            self.queue_operation_failed.emit(request_id, "Pear Desktop is unavailable or returned an error.")

    @Slot()
    def stop(self):
        self._is_running = False
