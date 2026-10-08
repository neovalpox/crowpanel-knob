"""Serveur HTTP local (127.0.0.1 uniquement) du compagnon.

- GET  /                 éditeur de profils (editor.html)
- GET  /api/state        profils, surcharges, apps récentes, actions possibles
- POST /api/profiles     enregistre les surcharges dans profiles.json
- POST /api/permission   demande de permission Claude Code (attend la réponse de la molette)

Protection : Host vérifié (anti DNS rebinding) et en-tête X-Knob obligatoire sur les POST
(un site web ne peut pas l'ajouter sans pré-vol CORS, que l'on refuse).
"""
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log = logging.getLogger("knob.server")
PORT = 47615  # 8765 est déjà pris par saber_daemon
HERE = Path(__file__).resolve().parent
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}


class Handler(BaseHTTPRequestHandler):
    companion = None  # injecté par start()

    def log_message(self, *_):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self):
        return self.headers.get("Host", "") in ALLOWED_HOSTS

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "host"})
        if self.path in ("/", "/index.html"):
            return self._send(200, (HERE / "editor.html").read_bytes(), "text/html; charset=utf-8")
        if self.path == "/api/ping":
            return self._send(200, {"knob": True})
        if self.path == "/api/state":
            return self._send(200, self.companion.editor_state())
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._host_ok() or self.headers.get("X-Knob") != "1":
            return self._send(403, {"error": "forbidden"})
        try:
            body = self._body()
        except Exception:
            return self._send(400, {"error": "json"})
        if self.path == "/api/profiles":
            self.companion.save_overrides(body.get("overrides", {}))
            return self._send(200, {"ok": True})
        if self.path == "/api/settings":
            self.companion.save_settings(body)
            return self._send(200, {"ok": True, "settings": self.companion.settings})
        if self.path == "/api/media-lock":
            c = self.companion
            # Traité par la boucle principale : seul fil autorisé à piloter le mode dédié.
            c.pending_lock = bool(body.get("on", not c.locked))
            return self._send(200, {"locked": bool(c.locked), "perf": getattr(c, "last_perf", "")})
        if self.path == "/api/firmware":
            self.companion.update_firmware()
            return self._send(200, {"ok": True})
        if self.path == "/api/permission":
            # Bloque jusqu'à la réponse (molette, terminal au premier plan ou délai).
            return self._send(200, self.companion.permissions.ask(body))
        self._send(404, {"error": "not found"})


def start(companion):
    Handler.companion = companion
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        log.info("serveur local indisponible (%s)", e)
        return None
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True, name="http").start()
    log.info("serveur local sur http://127.0.0.1:%d", PORT)
    return httpd
