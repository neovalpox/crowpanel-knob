"""Icône dans la zone de notification : état de la liaison et raccourcis."""
import logging
import os
import threading
import webbrowser

import pystray
from PIL import Image, ImageDraw

log = logging.getLogger("knob.tray")


def _icon_image(color):
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, size - 5, size - 5), outline=color, width=7)       # la bague
    d.ellipse((22, 22, size - 23, size - 23), fill=color)              # l'écran
    return img


CONNECTED = _icon_image((34, 211, 238))
DISCONNECTED = _icon_image((124, 132, 148))


class Tray:
    def __init__(self, companion, editor_url, log_path):
        self.companion = companion
        self.editor_url = editor_url
        self.log_path = log_path
        self.connected = None
        menu = pystray.Menu(
            pystray.MenuItem(lambda _: self.status_text(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Editer les profils", self.open_editor, default=True),
            pystray.MenuItem("Ouvrir le journal", lambda: os.startfile(self.log_path)),
            pystray.MenuItem("Recharger les profils", lambda: companion.request_reload()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quitter", self.quit),
        )
        self.icon = pystray.Icon("crowpanel_knob", DISCONNECTED, "CrowPanel Knob", menu)
        threading.Thread(target=self.icon.run, daemon=True, name="tray").start()

    def status_text(self):
        c = self.companion
        if not c.ser:
            return "Module non connecte"
        app = (c.app or {}).get("name", "-")
        return f"Connecte ({c.ser.port}) - {app}"

    def set_connected(self, connected):
        if connected == self.connected:
            return
        self.connected = connected
        self.icon.icon = CONNECTED if connected else DISCONNECTED
        self.icon.title = "CrowPanel Knob - " + ("connecte" if connected else "non connecte")

    def open_editor(self):
        webbrowser.open(self.editor_url)

    def quit(self):
        log.info("arrêt demandé depuis la zone de notification")
        self.icon.stop()
        os._exit(0)
