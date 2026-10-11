"""Serveur HTTP local (127.0.0.1 uniquement) du compagnon.

- GET  /                 éditeur de profils (editor.html)
- GET  /api/state        profils, surcharges, apps récentes, actions possibles
- POST /api/profiles     enregistre les surcharges dans profiles.json
- GET  /api/wifi         liaison (USB / Wi-Fi) et état du Wi-Fi du module
- GET  /api/screen?v=N   écran réel du module en PNG (miroir), 204 si inchangé
- POST /api/wifi/scan    réseaux vus par le module ; /api/wifi {ssid, password} ou {use_pc} ; /api/wifi/forget
- POST /api/permission   demande de permission Claude Code (attend la réponse de la molette)

Protection : Host vérifié (anti DNS rebinding) et en-tête X-Knob obligatoire sur les POST
(un site web ne peut pas l'ajouter sans pré-vol CORS, que l'on refuse).
"""
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import settings

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
        if self.path.startswith("/static/"):
            # Fichiers statiques de l'éditeur (Three.js…) : noms simples uniquement, pas de chemin.
            name = self.path[len("/static/"):]
            path = HERE / "static" / name
            if "/" in name or "\\" in name or ".." in name or not path.is_file():
                return self._send(404, {"error": "not found"})
            ctype = "text/javascript; charset=utf-8" if name.endswith(".js") else "application/octet-stream"
            return self._send(200, path.read_bytes(), ctype)
        if self.path in ("/", "/index.html"):
            return self._send(200, (HERE / "editor.html").read_bytes(), "text/html; charset=utf-8")
        if self.path == "/api/ping":
            return self._send(200, {"knob": True})
        if self.path == "/api/state":
            return self._send(200, self.companion.editor_state())
        if self.path == "/api/wifi":
            return self._send(200, self.companion.wifi_state())
        if self.path.startswith("/api/screen"):
            # Écran réel du module (PNG 240x240) ; 204 si rien de neuf depuis ?v=<version>.
            try:
                known = int(self.path.partition("v=")[2] or -1)
            except ValueError:
                known = -1
            version, png = self.companion.mirror_frame(known)
            if not png:
                self.send_response(204)
                self.send_header("X-Version", str(version))
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(png)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Version", str(version))
            self.end_headers()
            self.wfile.write(png)
            return
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
            return self._send(200, {"ok": True, "settings": settings.public(self.companion.settings)})
        if self.path == "/api/media-lock":
            c = self.companion
            # Traité par la boucle principale : seul fil autorisé à piloter le mode dédié.
            c.pending_lock = bool(body.get("on", not c.locked))
            return self._send(200, {"locked": bool(c.locked), "perf": getattr(c, "last_perf", "")})
        if self.path == "/api/firmware":
            self.companion.update_firmware()
            return self._send(200, {"ok": True})
        if self.path == "/api/wifi/scan":
            return self._send(200, self.companion.wifi_scan_networks())
        if self.path == "/api/wifi":
            return self._send(200, self.companion.wifi_configure(str(body.get("ssid", "")),
                                                                 str(body.get("password", "")),
                                                                 bool(body.get("use_pc"))))
        if self.path == "/api/wifi/forget":
            return self._send(200, self.companion.wifi_forget())
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
