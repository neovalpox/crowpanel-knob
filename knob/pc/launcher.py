"""Lanceur radial : jusqu'à 8 raccourcis affichés en cercle sur le module.

La liste vient de launcher.json (créé avec des valeurs par défaut au premier lancement,
modifiable à la main). Actions :
  "run:<chemin, URI ou .lnk>"   ouvre avec Windows (os.startfile)
  "key:<combo>"                 envoie une combinaison de touches
  "lock"                        verrouille la session
  "url:<adresse>"               ouvre dans le navigateur
Chaque entrée : {"label", "action", "symbol" (nom ci-dessous), "color" (rrggbb), "icon" (exe facultatif)}
"""
import json
import logging
import os
import shutil
import webbrowser
from pathlib import Path

import psutil

log = logging.getLogger("knob.launcher")
CONFIG = Path(__file__).resolve().parent / "launcher.json"
MAX_ITEMS = 8

# Symboles disponibles dans la police du module (Font Awesome intégrée à LVGL).
SYMBOLS = {
    "music": "\uf001", "video": "\uf008", "list": "\uf00b", "ok": "\uf00c", "power": "\uf011",
    "settings": "\uf013", "home": "\uf015", "download": "\uf019", "refresh": "\uf021", "image": "\uf03e",
    "eye": "\uf06e", "lock": "\uf070", "warning": "\uf071", "folder": "\uf07b", "upload": "\uf093",
    "call": "\uf095", "save": "\uf0c7", "mail": "\uf0e0", "bolt": "\uf0e7", "bell": "\uf0f3",
    "keyboard": "\uf11c", "file": "\uf15b", "wifi": "\uf1eb", "usb": "\uf287", "bluetooth": "\uf293",
    "trash": "\uf2ed",
}


def _running_exe(name):
    for p in psutil.process_iter(["name", "exe"]):
        if (p.info["name"] or "").lower() == name and p.info["exe"]:
            return p.info["exe"]
    return None


def _find(name, *candidates):
    for c in candidates:
        if c and Path(os.path.expandvars(c)).exists():
            return os.path.expandvars(c)
    return _running_exe(name) or shutil.which(name)


def default_items():
    bambu = _find("bambu-studio.exe", r"%ProgramFiles%\Bambu Studio\bambu-studio.exe")
    chrome = _find("chrome.exe", r"%ProgramFiles%\Google\Chrome\Application\chrome.exe")
    spotify = _running_exe("spotify.exe")
    items = [
        {"label": "Bambu", "action": f"run:{bambu}" if bambu else "url:https://bambulab.com",
         "symbol": "bolt", "color": "3DDC84", "icon": bambu},
        {"label": "Terminal", "action": "run:wt.exe", "symbol": "keyboard", "color": "22D3EE",
         "icon": _running_exe("windowsterminal.exe")},
        {"label": "Fichiers", "action": "run:explorer.exe", "symbol": "folder", "color": "FFCD42",
         "icon": r"C:\Windows\explorer.exe"},
        {"label": "Spotify", "action": "run:spotify:", "symbol": "music", "color": "1ED760", "icon": spotify},
        {"label": "Chrome", "action": f"run:{chrome}" if chrome else "url:https://google.com",
         "symbol": "eye", "color": "FF4436", "icon": chrome},
        {"label": "Capture", "action": "key:win+shift+s", "symbol": "image", "color": "A78BFA"},
        {"label": "Taches", "action": "key:ctrl+shift+esc", "symbol": "list", "color": "F472B6"},
        {"label": "Verrouiller", "action": "lock", "symbol": "lock", "color": "FF4D5E"},
    ]
    return items


def load_items():
    if not CONFIG.exists():
        CONFIG.write_text(json.dumps(default_items(), indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        items = json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception as e:
        log.info("launcher.json invalide (%s), valeurs par défaut", e)
        items = default_items()
    return items[:MAX_ITEMS]


def run(item, press_combo, lock):
    action = item.get("action") or ""
    log.info("lanceur : %s (%s)", item.get("label"), action)
    if action.startswith("run:"):
        os.startfile(action[4:])
    elif action.startswith("key:"):
        press_combo(action[4:])
    elif action.startswith("url:"):
        webbrowser.open(action[4:])
    elif action == "lock":
        lock()
