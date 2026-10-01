"""Lecture/contrôle des lecteurs média via l'API Windows (GSMTC).

Un thread tient sa propre boucle asyncio et rafraîchit un instantané des
sessions (titre, artiste, état, position, pochette) toutes les 500 ms.
"""
import asyncio
import io
import logging
import threading
import time

from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as Manager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
)
from winrt.windows.storage.streams import Buffer, DataReader, InputStreamOptions

log = logging.getLogger("knob.media")


class MediaWatcher:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.lock = threading.Lock()
        self.snapshots = {}  # source_app_id -> dict
        self._sessions = {}
        self._thumb_keys = {}
        threading.Thread(target=self._run, daemon=True, name="media").start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._poll_forever())

    async def _poll_forever(self):
        manager = None
        while True:
            try:
                if manager is None:
                    manager = await Manager.request_async()
                await self._poll(manager)
            except Exception as e:
                log.info("media: %s", e)
                manager = None
            await asyncio.sleep(0.5)

    async def _poll(self, manager):
        snaps, sessions = {}, {}
        for s in manager.get_sessions():
            sid = s.source_app_user_model_id
            props = await s.try_get_media_properties_async()
            tl = s.get_timeline_properties()
            pb = s.get_playback_info()
            key = (props.title, props.artist)
            prev = self.snapshots.get(sid, {})
            thumb = prev.get("thumb") if self._thumb_keys.get(sid) == key else None
            if thumb is None and props.thumbnail is not None:
                thumb = await self._read_thumb(props.thumbnail)
                self._thumb_keys[sid] = key
            snaps[sid] = {
                "title": props.title or "",
                "artist": props.artist or "",
                "playing": pb.playback_status == Status.PLAYING,
                "position": tl.position.total_seconds() if tl.position else 0,
                "duration": tl.end_time.total_seconds() if tl.end_time else 0,
                "updated": tl.last_updated_time.timestamp() if tl.last_updated_time else time.time(),
                "thumb": thumb,
            }
            sessions[sid] = s
        with self.lock:
            self.snapshots, self._sessions = snaps, sessions

    @staticmethod
    async def _read_thumb(ref):
        try:
            stream = await ref.open_read_async()
            buf = Buffer(stream.size)
            await stream.read_async(buf, buf.capacity, InputStreamOptions.READ_AHEAD)
            data = bytearray(buf.length)
            DataReader.from_buffer(buf).read_bytes(data)
            return bytes(data)
        except Exception as e:
            log.info("pochette illisible : %s", e)
            return None

    def find(self, match):
        """Session dont l'identifiant contient `match` (ex. "spotify")."""
        match = match.lower()
        with self.lock:
            for sid, snap in self.snapshots.items():
                if match in sid.lower():
                    return sid, dict(snap)
        return None, None

    @staticmethod
    def live_position(snap):
        pos = snap["position"]
        if snap["playing"]:
            pos += max(0.0, time.time() - snap["updated"])
        return min(pos, snap["duration"] or pos)

    def _control(self, sid, method):
        with self.lock:
            s = self._sessions.get(sid)
        if s is None:
            return False
        fut = asyncio.run_coroutine_threadsafe(self._call(s, method), self.loop)
        try:
            return fut.result(timeout=1.5)
        except Exception:
            return False

    @staticmethod
    async def _call(session, method):
        return await getattr(session, method)()

    def next(self, sid):
        return self._control(sid, "try_skip_next_async")

    def prev(self, sid):
        return self._control(sid, "try_skip_previous_async")

    def toggle(self, sid):
        return self._control(sid, "try_toggle_play_pause_async")


def thumb_image(data):
    from PIL import Image
    try:
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:
        return None
