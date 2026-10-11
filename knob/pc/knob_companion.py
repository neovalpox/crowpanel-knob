"""Compagnon PC du CrowPanel Knob.

- Pousse le volume général Windows vers le module (tuile « volume »).
- Suit la fenêtre au premier plan : envoie son nom, sa vraie icône, une couleur
  d'accent tirée de l'icône et le mode de la molette (tuile « application »).
- Exécute les actions de la molette selon le profil de l'app (profiles.json).
- Widgets : lecteur média (titre, pochette), imprimantes Bambu, statut Claude Code.

Protocole : voir firmware/src/main.cpp.
"""
import colorsys
import ctypes
import ctypes.wintypes as wt
import hashlib
import json
import re
import logging
import os
import subprocess
import threading
import time
import unicodedata
import webbrowser
from datetime import datetime
from pathlib import Path

import comtypes
import numpy as np
import psutil
import serial
from PIL import Image, ImageDraw, ImageFont
from serial.tools import list_ports
from pycaw.pycaw import AudioUtilities

import base64
import io

import bambu
import camera
import dashboard
import hue
import link
import audio_out
import launcher
import media
import meeting
import settings
import spectrum
import sysmon
import netspeed
import permissions
import server
import tray

HERE = Path(__file__).resolve().parent
VID_ESPRESSIF = 0x303A
# PID défini par le firmware (USB.PID). Surtout pas 0x1001 : c'est le port
# USB-JTAG du bootloader, l'ouvrir bloquerait le module en mode flash.
PID_KNOB = 0x4C4B
ICON_SIZE = 72
DEFAULT_COLOR = (0x22, 0xD3, 0xEE)
VOL_STEP = 0.02

# Fenêtres transitoires : on garde l'app précédente affichée.
IGNORED_EXES = {
    "searchhost.exe", "startmenuexperiencehost.exe", "shellexperiencehost.exe",
    "lockapp.exe", "shellhost.exe", "pythonw.exe", "taskmgr.exe",
}
IGNORED_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow",
                   "TopLevelWindowForOverflowXamlIsland", "XamlExplorerHostIslandWindow"}
DESKTOP_CLASSES = {"Progman", "WorkerW"}

logging.basicConfig(filename=HERE / "knob_companion.log", level=logging.INFO,
                    format="%(asctime)s %(message)s")
log = logging.getLogger("knob")

user32 = ctypes.windll.user32


# ---------------------------------------------------------------- Entrées clavier/souris

VK = {
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "tab": 0x09, "enter": 0x0D,
    "esc": 0x1B, "space": 0x20, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "pgup": 0x21, "pgdn": 0x22, "home": 0x24, "end": 0x23, "f5": 0x74, "delete": 0x2E,
    ".": 0xBE, ",": 0xBC,  # touches OEM : ord() donnerait Suppr / autre chose
    "playpause": 0xB3, "next": 0xB0, "prev": 0xB1,
}
MIRROR_RE = re.compile(rb"^s(\d+) (\d+) (\d+) (\d+) (\d+)$")

# Touches multimédia demandées par le module en Wi-Fi (usage HID -> touche virtuelle Windows).
HID_TO_VK = {0xE9: 0xAF, 0xEA: 0xAE, 0xE2: 0xAD, 0xCD: 0xB3, 0xB5: 0xB0, 0xB6: 0xB1}


def press_combo(combo):
    keys = [VK.get(k) or ord(k.upper()) for k in combo.lower().split("+")]
    for k in keys:
        user32.keybd_event(k, 0, 0, 0)
    for k in reversed(keys):
        user32.keybd_event(k, 0, 2, 0)


def press_media(usage):
    vk = HID_TO_VK.get(usage)
    if vk:
        user32.keybd_event(vk, 0, 1, 0)  # touche étendue, comme le clavier multimédia USB
        user32.keybd_event(vk, 0, 3, 0)


def scroll(steps):
    # Horaire = vers le bas.
    user32.mouse_event(0x0800, 0, 0, ctypes.c_uint32(-120 * steps).value, 0)


# ---------------------------------------------------------------- Fenêtre au premier plan

def window_class(hwnd):
    buf = ctypes.create_unicode_buffer(128)
    user32.GetClassNameW(hwnd, buf, 128)
    return buf.value


def window_pid(hwnd):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def uwp_child_pid(hwnd, host_pid):
    """Les apps UWP sont hébergées par ApplicationFrameHost : on cherche le vrai process."""
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(child, _):
        pid = window_pid(child)
        if pid != host_pid:
            found.append(pid)
            return False
        return True

    user32.EnumChildWindows(hwnd, cb, 0)
    return found[0] if found else host_pid


def foreground_app():
    """Renvoie (exe_path, exe_name) ou "desktop" ou None (à ignorer)."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    cls = window_class(hwnd)
    if cls in DESKTOP_CLASSES:
        return "desktop"
    if cls in IGNORED_CLASSES:
        return None
    pid = window_pid(hwnd)
    try:
        proc = psutil.Process(pid)
        if proc.name().lower() == "applicationframehost.exe":
            proc = psutil.Process(uwp_child_pid(hwnd, pid))
        name = proc.name()
        if name.lower() in IGNORED_EXES:
            return None
        return proc.exe(), name
    except (psutil.Error, OSError):
        return None


# ---------------------------------------------------------------- Icône, nom, couleur

def ascii_text(s, maxlen):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.replace("\t", " ").strip()
    return s if len(s) <= maxlen else s[: maxlen - 1].rstrip() + "."


def exe_description(exe):
    try:
        import win32api
        lang, cp = win32api.GetFileVersionInfo(exe, "\\VarFileInfo\\Translation")[0]
        desc = win32api.GetFileVersionInfo(exe, f"\\StringFileInfo\\{lang:04X}{cp:04X}\\FileDescription")
        if desc and desc.strip():
            return desc.strip()
    except Exception:
        pass
    return None


def load_exe_icon(exe):
    try:
        from icoextract import IconExtractor
        ico = Image.open(IconExtractor(exe).get_icon(num=0))
        sizes = sorted(ico.ico.sizes())
        ico.size = sizes[-1]
        return ico.convert("RGBA")
    except Exception as e:
        log.info("pas d'icône pour %s (%s)", exe, e)
        return None


def monogram(name, color):
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, ICON_SIZE - 3, ICON_SIZE - 3), fill=color + (255,))
    try:
        font = ImageFont.truetype("segoeuib.ttf", 40)
    except OSError:
        font = ImageFont.load_default()
    letter = (name[:1] or "?").upper()
    d.text((ICON_SIZE / 2, ICON_SIZE / 2 + 1), letter, font=font, fill=(255, 255, 255, 255), anchor="mm")
    return img


def accent_from_icon(img):
    """Couleur dominante parmi les pixels saturés de l'icône, ravivée pour l'écran."""
    a = np.asarray(img.resize((32, 32), Image.LANCZOS)).reshape(-1, 4).astype(float) / 255
    a = a[a[:, 3] > 0.7][:, :3]
    if len(a) == 0:
        return DEFAULT_COLOR
    hsv = np.array([colorsys.rgb_to_hsv(*p) for p in a])
    mask = (hsv[:, 1] > 0.35) & (hsv[:, 2] > 0.3)
    if mask.sum() < 8:
        return DEFAULT_COLOR
    hsv = hsv[mask]
    bins = (hsv[:, 0] * 24).astype(int) % 24
    weights = hsv[:, 1] * hsv[:, 2]
    best = np.bincount(bins, weights=weights, minlength=24).argmax()
    sel = hsv[bins == best]
    h = float(np.median(sel[:, 0]))
    s = max(float(np.median(sel[:, 1])), 0.6)
    r, g, b = colorsys.hsv_to_rgb(h, s, 1.0)
    return int(r * 255), int(g * 255), int(b * 255)


def icon_payload(img, size=ICON_SIZE):
    """RGBA -> RGB565 little-endian + alpha (format LV_IMG_CF_TRUE_COLOR_ALPHA)."""
    img = img.resize((size, size), Image.LANCZOS)
    px = np.asarray(img).astype(np.uint16)
    r, g, b, a = px[..., 0], px[..., 1], px[..., 2], px[..., 3]
    c = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    out = np.stack([c & 0xFF, c >> 8, a], axis=-1).astype(np.uint8)
    return out.tobytes()


def round_cover(img):
    """Pochette recadrée en carré puis découpée en disque (bord lissé)."""
    w, h = img.size
    side = min(w, h)
    img = img.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
    img = img.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS).convert("RGBA")
    big = Image.new("L", (ICON_SIZE * 4, ICON_SIZE * 4), 0)
    ImageDraw.Draw(big).ellipse((0, 0, ICON_SIZE * 4 - 1, ICON_SIZE * 4 - 1), fill=255)
    img.putalpha(big.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS))
    return img


# Symboles de la police LVGL (Font Awesome), envoyés tels quels en UTF-8.
SYM_PLAY, SYM_PAUSE, SYM_NEXT, SYM_PREV = "", "", "", ""
SYM_OK, SYM_WARN, SYM_REFRESH, SYM_CLOSE = "", "", "", ""
SYM_UP, SYM_DOWN = "", ""


def hex_color(rgb):
    return "%02X%02X%02X" % tuple(rgb)


def fmt_minutes(m):
    return f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m} min"


# ---------------------------------------------------------------- Profils

# knob : "appvol" | "master" | "scroll" | "auto" (appvol si l'app joue du son)
#        | "keys" (touches "cw"/"ccw" à chaque cran)
# widget : "media" (titre + pochette), "bambu" (impression), "claude" (statut des sessions)
# click / long : "playpause", "next", "prev", "mute", "appmute", "key:<combo>",
#        "toggle:<knob>" (bascule temporaire du mode molette), null
TAB_PROFILE = {"knob": "scroll", "click": "key:ctrl+tab", "long": "key:ctrl+shift+tab"}
CHAT_PROFILE = {"knob": "keys", "cw": "ctrl+tab", "ccw": "ctrl+shift+tab", "knob_label": "conversations",
                "click": "key:esc", "long": None}

DEFAULT_PROFILES = {
    "_default": {"knob": "auto", "click": "playpause", "long": "next"},
    "_desktop": {"name": "Bureau", "knob": "master", "click": "mute", "long": "playpause", "color": "22D3EE"},
    # Tuiles : "local" = comportement propre au module (volume HID, mute, historique…),
    # "app" = fait ce que ferait l'app au premier plan (son profil).
    "_tile_volume": {"name": "Tuile Volume", "knob": "local", "click": "local", "long": "audio"},
    "_tile_dashboard": {"name": "Tuile Tableau de bord", "knob": "none", "click": "local", "long": None},
    "_tile_network": {"name": "Tuile Reseau", "knob": "none", "click": None, "long": None},
    "_tile_system": {"name": "Tuile Systeme", "knob": "none", "click": None, "long": None},
    # ignore : la fenêtre ne change pas l'écran (on garde l'app précédente).
    "explorer.exe": {"name": "Explorateur", "ignore": True, "knob": "scroll", "click": "key:alt+up", "long": None},
    "spotify.exe": {"name": "Spotify", "widget": "media", "media_source": "spotify",
                    "click": "playpause", "long": "media:lock"},
    "vlc.exe": {"name": "VLC", "widget": "media", "media_source": "vlc", "click": "playpause", "long": "media:lock"},
    "chrome.exe": TAB_PROFILE | {"ignore": True}, "msedge.exe": TAB_PROFILE, "firefox.exe": TAB_PROFILE,
    "brave.exe": TAB_PROFILE, "opera.exe": TAB_PROFILE,
    "discord.exe": {"name": "Discord", "knob": "appvol", "click": "key:ctrl+shift+m", "long": "appmute"},
    "code.exe": {"name": "VS Code", "knob": "scroll", "click": "key:ctrl+s", "long": "key:ctrl+shift+p"},
    "cursor.exe": {"name": "Cursor", "knob": "scroll", "click": "key:ctrl+s", "long": "key:ctrl+shift+p"},
    # Terminal : flèches haut/bas pour naviguer les menus de Claude Code, clic = Entrée.
    "windowsterminal.exe": {"name": "Terminal", "ignore": True, "widget": "claude", "knob": "keys", "cw": "down", "ccw": "up",
                            "knob_label": "fleches", "click": "key:enter", "long": "key:esc"},
    "bambu-studio.exe": {"name": "Bambu Studio", "widget": "bambu", "knob": "scroll",
                         "click": "key:ctrl+r", "long": "bambu:camera"},
    "chatgpt.exe": {"name": "ChatGPT", "knob": "scroll", "click": "key:ctrl+shift+o", "long": None},
    "telegram.exe": CHAT_PROFILE | {"name": "Telegram"},
    "whatsapp.root.exe": CHAT_PROFILE | {"name": "WhatsApp"},
    "whatsapp.exe": CHAT_PROFILE | {"name": "WhatsApp"},
    "mattermost.exe": {"name": "Mattermost", "knob": "keys", "cw": "alt+down", "ccw": "alt+up",
                       "knob_label": "canaux", "click": "key:ctrl+k", "long": None},
    "ms-teams.exe": {"name": "Teams", "knob": "scroll", "click": "key:ctrl+shift+m", "long": "key:ctrl+shift+o"},
    "outlook.exe": {"name": "Outlook", "knob": "keys", "cw": "ctrl+.", "ccw": "ctrl+,", "knob_label": "messages",
                    "click": "key:ctrl+q", "long": "key:ctrl+r"},
    "olk.exe": {"name": "Outlook", "knob": "keys", "cw": "ctrl+.", "ccw": "ctrl+,", "knob_label": "messages",
                "click": "key:ctrl+q", "long": "key:ctrl+r"},
    "steamwebhelper.exe": {"name": "Steam", "knob": "scroll", "click": "playpause", "long": None},
    "steam.exe": {"name": "Steam", "knob": "scroll", "click": "playpause", "long": None},
    "mstsc.exe": {"name": "Bureau a distance", "knob": "master", "click": "mute", "long": None},
    "rustdesk.exe": {"name": "RustDesk", "knob": "master", "click": "mute", "long": None},
    # Deskflow : c'est le moteur (deskflow-core) qui passe au premier plan quand la souris
    # part sur l'autre PC ; deskflow.exe n'est que la fenêtre de configuration.
    "deskflow-core.exe": {"name": "Deskflow", "ignore": True, "knob": "master", "click": "mute", "long": None},
    "deskflow.exe": {"name": "Deskflow (reglages)", "knob": "master", "click": "mute", "long": None},
    "lightburn.exe": {"name": "LightBurn", "knob": "scroll", "click": None, "long": None},
    "excel.exe": {"name": "Excel", "knob": "scroll", "click": "key:ctrl+s", "long": None},
}

ACTION_LABELS = {
    "playpause": "play/pause", "next": "suivant", "prev": "precedent", "mute": "mute",
    "appmute": "mute app", "key:ctrl+tab": "onglet suivant", "key:ctrl+s": "enregistrer",
    "key:ctrl+shift+m": "mute micro", "key:alt+up": "dossier parent", "key:enter": "entree",
    "key:ctrl+r": "trancher", "key:ctrl+shift+o": "nouveau chat", "key:esc": "echap",
    "key:ctrl+k": "recherche", "key:ctrl+q": "marquer lu", "toggle:appvol": "volume",
    "local": "defaut de la tuile", "app": "comme l'app", "audio": "sortie audio", "media:lock": "mode dedie",
}
KNOB_LABELS = {"scroll": "defiler", "appvol": "volume app", "master": "volume", "media": "pistes"}
TILE_PROFILES = {1: "_tile_volume", 2: "_tile_dashboard", 3: "_tile_network", 4: "_tile_system"}  # Q -> profil


def load_profiles():
    """Profils par défaut + surcharges de profiles.json (une entrée remplace celle par défaut)."""
    path = HERE / "profiles.json"
    profiles = dict(DEFAULT_PROFILES)
    if not path.exists():
        path.write_text(json.dumps({"_exemple.exe": {"name": "Mon app", "knob": "scroll",
                                                     "click": "key:ctrl+s", "long": None}},
                                   indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        try:
            profiles.update(json.loads(path.read_text(encoding="utf-8")))
        except Exception as e:
            log.info("profiles.json invalide (%s), profils par défaut", e)
    return {k.lower(): v for k, v in profiles.items()}


# ---------------------------------------------------------------- Audio

def master_endpoint():
    return AudioUtilities.GetSpeakers().EndpointVolume


def app_sessions(exe_name):
    out = []
    for s in AudioUtilities.GetAllSessions():
        try:
            if s.Process and s.Process.name().lower() == exe_name.lower():
                out.append(s.SimpleAudioVolume)
        except Exception:
            pass
    return out


# ---------------------------------------------------------------- Widgets

TILE_APP, TILE_VOL, TILE_DASH, TILE_NET, TILE_SYS, TILE_HUE = range(6)  # ordre des tuiles du firmware
AUDIO_ASK_BASE = 100000  # ids des questions « sortie audio » (distincts des permissions Claude)


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


def idle_seconds():
    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    user32.GetLastInputInfo(ctypes.byref(info))
    return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000


def is_locked():
    """Session verrouillée : le bureau de saisie n'est plus accessible."""
    desk = user32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_SWITCHDESKTOP
    if not desk:
        return True
    ok = user32.SwitchDesktop(desk)
    user32.CloseDesktop(desk)
    return not ok


CLAUDE_STATUS = Path.home() / ".claude" / "knob_status.json"
COL_OK, COL_WARN, COL_ERR, COL_IDLE, COL_CLAUDE = "3DDC84", "FFB020", "FF4D5E", "7C8494", "D97757"


def claude_sessions():
    try:
        data = json.loads(CLAUDE_STATUS.read_text(encoding="utf-8"))
    except Exception:
        return []
    now = time.time()
    rank = {"waiting": 0, "working": 1, "done": 2}
    out = [v for v in data.values() if now - v.get("t", 0) < 6 * 3600]
    return sorted(out, key=lambda v: (rank.get(v.get("state"), 3), -v.get("t", 0)))


# ---------------------------------------------------------------- Compagnon

class Companion:
    def __init__(self):
        self.ser = None
        self.ev = None
        self.ev_time = 0
        self.profiles = load_profiles()
        self.profiles_mtime = 0
        self.icon_cache = {}
        self.cover_cache = {}
        self.app_key = None        # (exe_path, exe_name) ou "desktop"
        self.app = None            # dict décrivant l'app affichée
        self.mode_override = None  # bascule temporaire du mode molette (appui long)
        self.view = {}             # dernier état envoyé pour le widget
        self.last_master = None
        self.last_master_sent = 0
        self.last_appvol = None
        self.last_appvol_check = 0
        self.last_fg_check = 0
        self.last_widget = 0
        self.last_skip = 0
        self.bambu_sel = 0
        self.rx = b""
        self.media = media.MediaWatcher()
        self.bambu = bambu.BambuWatcher()
        self.dash = dashboard.Dashboard()
        self.hue = hue.Hue()
        self.camera = camera.Camera()
        self.cam_on = False
        self.cam_seq = 0
        self.tile = 0              # tuile affichée sur le module (message Q)
        self.sent = {}             # derniers messages envoyés par clé (anti-doublons)
        self.claude_prev = {}      # état précédent des sessions Claude (alertes)
        self.bambu_prev = {}       # état précédent des imprimantes (alertes)
        self.last_slow = 0
        self.last_clock = 0
        self.last_hue = 0
        self.last_perm = 0
        self.last_fg = None        # dernière fenêtre au premier plan (même ignorée)
        self.fg_exe = ""
        self.net = netspeed.NetSpeed()
        self.last_net = 0
        self.sysmon = sysmon.SysMon()
        self.alert_times = {}
        self.audio_choices = None
        self.audio_ask_id = AUDIO_ASK_BASE
        self.launcher_items = None
        self.launcher_mtime = 0
        self.launcher_icons = {}
        self.settings = settings.load()
        self.meeting_state = 0
        self.updating = False
        self.locked = None         # mode dédié média verrouillé (dict) ou None
        self.spectrum = spectrum.Spectrum()
        self.spec_seq = 0
        self.last_spec = 0
        self.last_lock_info = 0
        self.lock_sent = {}
        self.pending_lock = None    # verrouillage demandé par l'API (traité dans la boucle)
        self.away_muted = False     # son coupé par nous pour absence (à rétablir au retour)
        self.write_lock = threading.Lock()
        self.link_kind = None       # "usb" ou "wifi"
        self.relink = False
        self.next_wifi_try = 0
        self.wifi_status = None     # dernier état Wi-Fi rapporté par le module
        self.wifi_scan = []
        self.wifi_scan_done = threading.Event()
        self.pc_net = (0, None)
        self.mirror = np.zeros((240, 240), np.uint16)  # écran du module (RGB565), tenu à jour par "s"
        self.mirror_version = 0
        self.mirror_png = (-1, b"")
        self.mirror_wanted = 0      # dernière demande de l'éditeur (monotonic)
        self.mirror_on = False     # (horodatage, SSID du PC) : netsh est lent, on le garde 30 s
        self.last_wifi_poll = 0
        self.recent = {}           # apps vues au premier plan (éditeur de profils)
        self.editor_icon_misses = set()
        self.png_cache = {}        # icônes en PNG base64 pour l'éditeur
        self.reload_requested = False
        self.ask_shown = None      # id de la demande de permission affichée
        self.permissions = permissions.Permissions(
            lambda: self.fg_exe == "windowsterminal.exe")
        server.start(self)
        self.tray = tray.Tray(self, f"http://127.0.0.1:{server.PORT}/", HERE / "knob_companion.log")

    # --- liaison série
    def connect(self):
        mode = self.settings.get("link", "auto")
        ser = (self.open_usb() if mode != "wifi" else None) or (self.open_wifi() if mode != "usb" else None)
        if not ser:
            return False
        self.link_kind = "wifi" if isinstance(ser, link.NetLink) else "usb"
        self.on_connected(ser)
        return True

    def open_usb(self):
        port = next((p.device for p in list_ports.comports()
                     if p.vid == VID_ESPRESSIF and p.pid == PID_KNOB), None)
        if not port:
            return None
        ser = serial.Serial()
        ser.port, ser.baudrate, ser.timeout, ser.write_timeout = port, 115200, 0, 2
        # DTR obligatoire : sans lui, le CDC TinyUSB du module refuse d'émettre
        # (molette/clic perdus). RTS reste bas : seule la séquence RTS/DTR
        # complète redémarre le module en mode flash.
        ser.dtr, ser.rts = True, False
        ser.open()
        return ser

    def open_wifi(self):
        """Module en Wi-Fi : dernière IP connue, sinon découverte sur le réseau local."""
        key = self.settings.get("wifi_key")
        now = time.monotonic()
        if not key or now < self.next_wifi_try:
            return None
        self.next_wifi_try = now + 5
        for ip in dict.fromkeys(filter(None, [self.settings.get("wifi_ip"), "?"])):
            if ip == "?":
                ip = link.discover()
                if not ip:
                    return None
            try:
                net = link.NetLink(ip, key)
            except (OSError, ConnectionError) as e:
                log.debug("Wi-Fi %s : %s", ip, e)
                continue
            if ip != self.settings.get("wifi_ip"):
                self.settings = settings.set_private("wifi_ip", ip)
            return net
        return None

    def on_connected(self, ser):
        self.ser = ser
        self.last_master = None
        self.app_key = None
        self.sent = {}
        self.last_clock = 0
        self.ask_shown = None
        self.launcher_mtime = 0  # renvoie le lanceur au module (re)connecté
        self.last_fg = None
        self.app = None
        self.lock_sent = {}
        if self.locked:  # le module a redémarré : on remet la vue dédiée
            self.ser = ser
            self.send("e1\n")
        self.rx = b""
        self.wifi_status = None
        self.last_wifi_poll = 0
        # Miroir coupé par défaut (il a pu rester actif d'une liaison précédente) ;
        # push_mirror_state le rallume si l'éditeur regarde.
        self.mirror_on = False
        self.send("s0\n")
        log.info("connecté (%s)", ser.port)

    def send(self, data):
        # Un seul écrivain à la fois : deux fils qui écrivent en même temps mélangeraient
        # les octets (ex. une trame de spectre au milieu d'une pochette).
        with self.write_lock:
            self.ser.write(data if isinstance(data, bytes) else data.encode("utf-8"))

    def send_icon(self, payload, animate):
        self.send(f"I{ICON_SIZE} {ICON_SIZE} {len(payload)}\n".encode() + payload)
        if not animate:
            self.send("U\n")

    # --- volume général
    def endpoint(self):
        now = time.monotonic()
        if self.ev is None or now - self.ev_time > 2:  # suit le changement de sortie audio
            self.ev, self.ev_time = master_endpoint(), now
        return self.ev

    def push_master(self):
        ev = self.endpoint()
        state = (round(ev.GetMasterVolumeLevelScalar() * 100), int(bool(ev.GetMute())))
        now = time.monotonic()
        if state != self.last_master or now - self.last_master_sent > 2:
            self.send(f"V{state[0]} M{state[1]}\n")
            self.last_master, self.last_master_sent = state, now

    # --- app au premier plan
    def profile_for(self, key, exe_name):
        if key == "desktop":
            return self.profiles["_desktop"]
        p = dict(self.profiles["_default"])
        p.update(self.profiles.get(exe_name.lower(), {}))
        return p

    def describe(self, key):
        if key == "desktop":
            exe_path, exe_name = None, "desktop"
        else:
            exe_path, exe_name = key
        prof = self.profile_for(key, exe_name)
        name = prof.get("name") or exe_description(exe_path) or Path(exe_name).stem.capitalize()
        name = ascii_text(name, 18)

        cache_key = exe_path or "desktop"
        if cache_key not in self.icon_cache:
            img = load_exe_icon(exe_path) if exe_path else None
            if prof.get("color"):
                color = tuple(int(prof["color"][i:i + 2], 16) for i in (0, 2, 4))
            elif img is not None:
                color = accent_from_icon(img)
            else:
                color = DEFAULT_COLOR
            if img is None:
                img = monogram(name, color)
            self.icon_cache[cache_key] = (icon_payload(img), color)
            buf = io.BytesIO()
            img.resize((48, 48), Image.LANCZOS).save(buf, "PNG")
            self.png_cache[exe_name.lower()] = (
                "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), "#" + hex_color(color))
        payload, color = self.icon_cache[cache_key]

        widget = prof.get("widget")
        knob = self.mode_override or prof.get("knob", "auto")
        if widget == "media" and not self.mode_override:
            knob = "media"
        if knob == "auto":
            knob = "appvol" if app_sessions(exe_name) else "master"
        display = "progress" if widget in ("bambu", "claude") else knob

        click_label = ACTION_LABELS.get(prof.get("click"), (prof.get("click") or "").replace("key:", ""))
        hint = f"clic : {click_label}" if click_label else KNOB_LABELS.get(knob, prof.get("knob_label", ""))
        return {"exe": exe_name, "name": name, "knob": knob, "display": display, "widget": widget,
                "color": color, "hint": ascii_text(hint, 26), "payload": payload, "profile": prof}

    def push_app(self, key):
        app = self.describe(key)
        self.app_key, self.app = key, app
        self.send_icon(app["payload"], animate=True)
        self.send(f"A{app['name']}\t{app['display']}\t{hex_color(app['color'])}\t{app['hint']}\n")
        self.last_appvol = None
        self.view = {"icon": "app"}
        self.update_widget()
        log.info("app : %s (%s)", app["name"], app["display"])

    def check_foreground(self):
        fg = foreground_app()
        if fg is None:
            return
        if fg == self.last_fg:
            return
        self.last_fg = fg
        exe = "_desktop" if fg == "desktop" else fg[1].lower()
        self.fg_exe = exe
        if self.locked:
            return  # mode dédié verrouillé : l'écran ne suit plus les fenêtres
        if self.profile_for(fg, exe).get("ignore") and self.app is not None:
            self.recent.setdefault(exe, self.profiles.get(exe, {}).get("name") or Path(exe).stem.capitalize())
            return  # fenêtre ignorée : l'écran garde l'app précédente
        self.mode_override = None
        self.set_camera(False)
        self.push_app(fg)  # même si c'est l'app déjà connue : on la réaffiche
        self.recent[exe] = self.app["name"]

    def push_appvol(self):
        if not self.app or self.app["knob"] != "appvol":
            return
        sess = app_sessions(self.app["exe"])
        if not sess:
            return
        state = (round(sess[0].GetMasterVolume() * 100), int(bool(sess[0].GetMute())))
        if state != self.last_appvol:
            self.send(f"a{state[0]} M{state[1]}\n")
            self.last_appvol = state

    # --- widgets
    def media_session(self):
        prof = self.app["profile"]
        return self.media.find(prof.get("media_source") or Path(self.app["exe"]).stem)

    def media_view(self):
        sid, snap = self.media_session()
        if not snap or not snap["title"]:
            return {"texts": (self.app["name"], "rien en lecture"), "prog": (0, SYM_PLAY),
                    "color": hex_color(self.app["color"]), "icon": "app"}
        view = {"texts": (ascii_text(snap["title"], 60), ascii_text(snap["artist"], 40))}
        dur = snap["duration"]
        permille = int(1000 * self.media.live_position(snap) / dur) if dur else 0
        view["prog"] = (permille, SYM_PLAY if snap["playing"] else SYM_PAUSE)
        view["color"] = hex_color(self.app["color"])
        view["icon"] = "app"
        if snap["thumb"]:
            h = hashlib.md5(snap["thumb"]).hexdigest()
            if h not in self.cover_cache:
                img = media.thumb_image(snap["thumb"])
                self.cover_cache[h] = ((icon_payload(round_cover(img)), hex_color(accent_from_icon(img)))
                                       if img else None)
            if self.cover_cache[h]:
                view["icon"] = h
                view["color"] = self.cover_cache[h][1]
        return view

    def bambu_view(self):
        printers = self.bambu.summaries()
        if not printers:
            return {"texts": (self.app["name"], "aucune imprimante"), "prog": (0, ""), "color": COL_IDLE}
        idx = self.bambu_sel % len(printers)
        p = printers[idx]
        name = ascii_text(p["name"], 14) + (f"  {idx + 1}/{len(printers)}" if len(printers) > 1 else "")
        st, pct = p["state"], p["percent"]
        if st == "RUNNING":
            layer = f" - {p['layer']}/{p['layers']}" if p["layers"] else ""
            return {"texts": (name, f"{fmt_minutes(p['remaining'])}{layer}"), "prog": (pct * 10, f"{pct}%"),
                    "color": COL_OK}
        if st == "PAUSE":
            return {"texts": (name, f"en pause - {pct}%"), "prog": (pct * 10, SYM_PAUSE), "color": COL_WARN}
        if st in ("PREPARE", "SLICING"):
            return {"texts": (name, "preparation"), "prog": (0, SYM_REFRESH), "color": "22D3EE"}
        if st == "FINISH":
            return {"texts": (name, "impression terminee"), "prog": (1000, SYM_OK), "color": COL_OK}
        if st == "FAILED":
            return {"texts": (name, "echec"), "prog": (pct * 10, SYM_CLOSE), "color": COL_ERR}
        return {"texts": (name, "prete"), "prog": (0, ""), "color": COL_IDLE}

    def claude_view(self):
        sessions = claude_sessions()
        if not sessions:
            return {"texts": ("Terminal", "fleches - entree - echap"), "prog": (0, ""),
                    "color": hex_color(self.app["color"])}
        s = sessions[0]
        project = ascii_text(Path(s.get("cwd") or "Claude").name or "Claude", 18)
        extra = f" (+{len(sessions) - 1})" if len(sessions) > 1 else ""
        state = s.get("state")
        if state == "waiting":
            return {"texts": (project, "attend ta reponse" + extra), "prog": (1000, SYM_WARN), "color": COL_WARN}
        if state == "working":
            # L'arc tourne en boucle pendant que Claude travaille.
            return {"texts": (project, "au travail" + extra), "prog": (int(time.time() * 450) % 1000, SYM_REFRESH),
                    "color": COL_CLAUDE}
        return {"texts": (project, "termine" + extra), "prog": (1000, SYM_OK), "color": COL_OK}

    def update_widget(self):
        app = self.app
        if not app or not app["widget"]:
            return
        if app["widget"] == "media":
            if app["knob"] != "media":
                return
            view = self.media_view()
        elif app["widget"] == "bambu":
            view = self.bambu_view()
        elif app["widget"] == "claude":
            view = self.claude_view()
        else:
            return
        old = self.view
        icon = view.get("icon", old.get("icon", "app"))
        if icon != old.get("icon"):
            payload = app["payload"] if icon == "app" else self.cover_cache[icon][0]
            self.send_icon(payload, animate=False)
        if view["color"] != old.get("color"):
            self.send(f"C{view['color']}\n")
        if view["texts"] != old.get("texts"):
            self.send(f"T{view['texts'][0]}\t{view['texts'][1]}\n")
        if view["prog"] != old.get("prog"):
            self.send(f"P{view['prog'][0]}\t{view['prog'][1]}\n")
        view["icon"] = icon
        self.view = view

    def send_once(self, key, msg):
        """N'envoie que si le message a changé depuis le dernier envoi sous cette clé."""
        if self.sent.get(key) != msg:
            self.send(msg)
            self.sent[key] = msg

    # --- caméra Bambu
    def set_camera(self, on):
        if not on:
            if self.cam_on:
                self.camera.stop()
                if self.ser:
                    self.send("j\n")
            self.cam_on = False
            return
        printers = self.bambu.summaries()
        if not printers:
            return
        p = printers[self.bambu_sel % len(printers)]
        if self.camera.start(p["ip"], self.bambu.access_code(p["serial"])):
            self.cam_on, self.cam_seq = True, 0
            self.send(f"F{SYM_REFRESH}\n")

    def push_camera(self):
        if not self.cam_on:
            return
        if not self.camera.running:
            self.set_camera(False)
            return
        if self.camera.frame and self.camera.seq != self.cam_seq:
            self.cam_seq = self.camera.seq
            frame = self.camera.frame
            self.send(f"J{camera.SIZE} {camera.SIZE} {len(frame)}\n".encode() + frame)

    # --- tableau de bord
    def push_dashboard(self):
        now = datetime.now()
        if time.monotonic() - self.last_clock > 30:
            self.last_clock = time.monotonic()
            secs = now.hour * 3600 + now.minute * 60 + now.second
            self.send(f"K{secs}\t{dashboard.date_text(now)}\n")
        temp, desc = self.dash.weather
        self.send_once("W", f"W{temp}\t{desc}\n")
        self.send_once("E", f"E{self.dash.event}\n")
        self.send_once("S", f"S{self.status_line()}\n")

    def status_line(self):
        for p in self.bambu.summaries():
            if p["state"] == "RUNNING":
                return f"{ascii_text(p['name'], 10)} {p['percent']}% - {fmt_minutes(p['remaining'])}\t{COL_OK}"
        sessions = claude_sessions()
        if sessions and sessions[0].get("state") == "waiting":
            return f"Claude attend ta reponse\t{COL_WARN}"
        if sessions and sessions[0].get("state") == "working":
            return f"Claude au travail\t{COL_CLAUDE}"
        return f"\t{COL_IDLE}"

    # --- veille
    def is_night(self):
        h, s = datetime.now().hour, self.settings
        start, end = s["night_start"], s["night_end"]
        return (start <= h or h < end) if start > end else (start <= h < end)

    def push_sleep(self):
        locked, idle = is_locked(), idle_seconds()
        s = self.settings
        night = self.is_night()
        night_leds = max(0, min(255, int(s["night_leds"] * 255 / 100)))
        if night and (locked or idle > 120):
            z = "Z8 0 1 0"          # nuit, absent : quasi éteint, LEDs coupées, horloge
        elif locked or idle > 600:
            z = "Z70 0 1 255"       # absent : tamisé, horloge
        elif night:
            z = f"Z{int(s['night_backlight'])} 1 0 {night_leds}"  # nuit, présent : écran et LEDs adoucis
        else:
            z = "Z220 1 0 255"
        self.send_once("Z", z + "\n")

    # --- réunion (une app utilise le micro)
    def check_away_mute(self):
        """Coupe tout le son après N min d'absence ; le rétablit au retour si c'est nous qui l'avions coupé."""
        minutes = self.settings["away_mute_min"]
        locked, idle = is_locked(), idle_seconds()
        if self.away_muted:
            if not locked and idle < 5:  # retour devant le PC
                self.away_muted = False
                if audio_out.master_muted():
                    audio_out.set_master_mute(False)
                    self.notify("", "Son retabli", "bon retour !", "22D3EE")
                log.info("retour : son rétabli")
        elif minutes and idle >= minutes * 60:  # l'inactivité continue de compter session verrouillée
            if not audio_out.master_muted():  # déjà coupé à la main : on n'y touche pas
                audio_out.set_master_mute(True)
                self.away_muted = True
                self.send(f"n\tSon coupe\tabsent depuis {minutes} min\t7C8494\n")
                log.info("absent depuis %d min : son coupé", minutes)

    def push_meeting(self):
        st, label = meeting.state()
        self.meeting_state = st
        self.send_once("m", f"m{st}\t{ascii_text(label, 26)}\n")

    # --- réglages (éditeur) et écran d'accueil
    # --- mode dédié média (verrouillage sur Spotify & co.)
    def media_skip(self, steps, source):
        now = time.monotonic()
        if now - self.last_skip < 0.3:  # un cran = une piste, même en tournant vite
            return
        self.last_skip = now
        sid, _ = self.media.find(source)
        ok = sid and (self.media.next(sid) if steps > 0 else self.media.prev(sid))
        if not ok:
            press_combo("next" if steps > 0 else "prev")
        self.send(f"F{SYM_NEXT if steps > 0 else SYM_PREV}\n")

    def lock_media(self):
        if not self.app:
            return
        # Depuis une app média : son lecteur ; sinon (éditeur, API) : Spotify par défaut.
        is_media = self.app.get("widget") == "media"
        source = (self.app["profile"].get("media_source") or Path(self.app["exe"]).stem) if is_media else "spotify"
        self.locked = {"source": source, "name": self.app["name"] if is_media else "Spotify",
                       "color": hex_color(self.app["color"]), "payload": self.app["payload"]}
        self.lock_sent = {}
        self.send("e1\n")
        self.spectrum.start(audio_out.current()[1])
        self.push_locked()
        log.info("mode dédié verrouillé sur %s", self.locked["name"])

    def unlock_media(self):
        self.locked = None
        self.spectrum.stop()
        self.send("e0\n")
        log.info("mode dédié déverrouillé")
        self.last_fg = None  # réaffiche l'app au premier plan au prochain passage
        if self.app_key:
            self.push_app(self.app_key)

    def push_locked(self):
        """Pochette, titre, artiste, avancement et état de lecture pour la vue dédiée."""
        lk = self.locked
        sid, snap = self.media.find(lk["source"])
        if not snap or not snap["title"]:
            info = (lk["name"], "rien en lecture", lk["color"], 0, 0)
            cover_key, payload = "app", lk["payload"]
        else:
            dur = snap["duration"]
            permille = int(1000 * self.media.live_position(snap) / dur) if dur else 0
            cover_key, payload, color = "app", lk["payload"], lk["color"]
            if snap["thumb"]:
                h = hashlib.md5(snap["thumb"]).hexdigest()
                if h not in self.cover_cache:
                    img = media.thumb_image(snap["thumb"])
                    self.cover_cache[h] = ((icon_payload(round_cover(img)), hex_color(accent_from_icon(img)))
                                           if img else None)
                if self.cover_cache[h]:
                    cover_key, (payload, color) = h, self.cover_cache[h]
            info = (ascii_text(snap["title"], 60), ascii_text(snap["artist"], 40), color, permille,
                    int(snap["playing"]))
        if cover_key != self.lock_sent.get("cover"):
            self.send(f"I{ICON_SIZE} {ICON_SIZE} {len(payload)}\n".encode() + payload)
            self.send("u\n")
            self.lock_sent["cover"] = cover_key
        msg = "k{}\t{}\t{}\t{}\t{}\n".format(*info)
        if msg != self.lock_sent.get("info"):
            self.send(msg)
            self.lock_sent["info"] = msg

    def push_spectrum(self):
        if self.spectrum.frame and self.spectrum.seq != self.spec_seq:
            self.spec_seq = self.spectrum.seq
            self.send(self.spectrum.frame)

    # --- molette / clic / appui long sur les tuiles (profils _tile_*)
    def tile_profile(self, tile):
        return self.profiles.get(TILE_PROFILES[tile], {})

    def push_tile_config(self):
        """Dit au module ce qu'il gère lui-même sur chaque tuile (le reste lui est renvoyé ici)."""
        for tile in TILE_PROFILES:
            p = self.tile_profile(tile)
            mask = (p.get("knob") == "local") * 1 | (p.get("click") == "local") * 2 | (p.get("long") == "local") * 4
            self.send_once(f"y{tile}", f"y{tile} {mask}\n")

    def tile_event(self, msg):
        p = self.tile_profile(self.tile)
        if msg[0] == "R":
            self.tile_rotate(p, int(msg[1:]))
        else:
            which = "click" if msg == "C" else "long"
            action = p.get(which)
            if action == "app":
                if self.app:
                    self.run_action(self.app["profile"].get(which))
            elif action == "audio":
                self.ask_audio()
            elif action not in (None, "local"):
                self.run_action(action)

    def tile_rotate(self, p, steps):
        knob = p.get("knob")
        if knob == "app":
            self.on_rotate(steps)  # exactement ce que ferait la molette sur la tuile de l'app
        elif knob == "scroll":
            scroll(steps)
        elif knob == "keys":
            combo = p.get("cw" if steps > 0 else "ccw")
            for _ in range(min(abs(steps), 5)):
                if combo:
                    press_combo(combo)
        elif knob == "media":
            press_combo("next" if steps > 0 else "prev")
            self.send(f"F{SYM_NEXT if steps > 0 else SYM_PREV}\n")
        elif knob == "appvol" and self.app:
            for sess in app_sessions(self.app["exe"]):
                sess.SetMasterVolume(min(1.0, max(0.0, sess.GetMasterVolume() + VOL_STEP * steps)), None)
        elif knob == "master":
            ev = self.endpoint()
            ev.SetMasterVolumeLevelScalar(min(1.0, max(0.0, ev.GetMasterVolumeLevelScalar() + VOL_STEP * steps)), None)
            self.push_master()

    def push_home(self):
        self.send_once("Q", settings.home_message(self.settings))

    def save_settings(self, values):
        old_link = self.settings.get("link")
        self.settings = settings.save(values)
        if self.settings["link"] != old_link:
            self.relink = True  # la boucle principale coupe la liaison et se reconnecte selon le mode
            self.next_wifi_try = 0
        log.info("réglages enregistrés : %s", settings.public(self.settings))

    # --- mise à jour du firmware en un clic (icône de notification)
    def update_firmware(self):
        if self.updating:
            return
        # Module en Wi-Fi seulement : envoi sans fil ; sinon flash par l'USB comme avant.
        self.update_over = "wifi" if self.link_kind == "wifi" else "usb"
        self.updating = True
        threading.Thread(target=self._update_firmware, daemon=True, name="firmware").start()

    def _update_firmware(self):
        try:
            for _ in range(50):  # la boucle principale libère le port série
                if self.ser is None:
                    break
                time.sleep(0.1)
            pio = Path.home() / ".platformio" / "penv" / "Scripts" / "pio.exe"
            fw = HERE.parent / "firmware"
            wifi = self.update_over == "wifi"
            log.info("mise à jour du firmware (%s)…", "Wi-Fi" if wifi else "USB")
            self.tray.notify("Mise a jour du firmware en cours...")
            cmd = [str(pio), "run", "-d", str(fw)] + ([] if wifi else ["-t", "upload"])
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            ok = res.returncode == 0
            if ok and wifi:
                for attempt in range(3):  # nouveaux essais si le Wi-Fi a flanché
                    try:
                        err = link.push_firmware(self.settings.get("wifi_ip"), self.settings.get("wifi_key"),
                                                 fw / ".pio" / "build" / "knob" / "firmware.bin")
                    except (OSError, ConnectionError, serial.SerialException) as e:
                        err = str(e)
                    if err is None:
                        break
                    log.info("firmware sans fil : échec (%s)%s", err, ", nouvel essai" if attempt < 2 else "")
                    time.sleep(5)
                ok = err is None
                res.stdout += f"\nenvoi Wi-Fi : {err}"
            log.info("mise à jour du firmware : %s", "réussie" if ok else "ÉCHEC\n" + res.stdout[-1500:])
            self.tray.notify("Firmware mis a jour" if ok else "Echec de la mise a jour (voir le journal)")
        except Exception:
            log.exception("mise à jour du firmware")
        finally:
            time.sleep(4)  # le temps que le module redémarre
            self.updating = False

    # --- miroir de l'écran du module (éditeur 3D)
    def on_mirror(self, x, y, w, h, data):
        out, i, n = np.empty(w * h, np.uint16), 0, len(data)
        k = 0
        while i < n and k < w * h:
            b = data[i]
            if b >= 128:  # plage : (b - 127) fois le pixel suivant
                run = b - 127
                out[k:k + run] = data[i + 1] | data[i + 2] << 8
                k += run
                i += 3
            else:         # b + 1 pixels bruts
                cnt = b + 1
                out[k:k + cnt] = np.frombuffer(data, "<u2", cnt, i + 1)
                k += cnt
                i += 1 + 2 * cnt
        if k == w * h and x + w <= 240 and y + h <= 240:
            self.mirror[y:y + h, x:x + w] = out.reshape(h, w)
            self.mirror_version += 1

    def mirror_frame(self, known):
        """(version, PNG) de l'écran du module ; PNG vide si rien de neuf depuis `known`."""
        self.mirror_wanted = time.monotonic()
        v = self.mirror_version
        if v == known or not self.mirror_on or v == 0:
            return v, b""
        if self.mirror_png[0] != v:
            px = self.mirror.astype(np.uint32)
            rgb = np.dstack([((px >> 11) & 31) * 255 // 31, ((px >> 5) & 63) * 255 // 63,
                             (px & 31) * 255 // 31]).astype(np.uint8)
            buf = io.BytesIO()
            Image.fromarray(rgb, "RGB").save(buf, "PNG", compress_level=1)
            self.mirror_png = (v, buf.getvalue())
        return self.mirror_png

    def push_mirror_state(self):
        want = time.monotonic() - self.mirror_wanted < 3
        if want != self.mirror_on:
            self.mirror_on = want
            if want:
                self.mirror_version = 0  # le module renvoie tout l'écran
            self.send("s1\n" if want else "s0\n")

    # --- Wi-Fi : configuration par l'USB, puis liaison sans fil
    def on_wifi_message(self, msg):
        if msg.startswith("wi"):
            f = (msg[2:].split("\t") + ["", "", "", ""])[:4]
            state = int(f[0] or 0)
            self.wifi_status = {"state": state, "ssid": f[1], "ip": f[2], "rssi": int(f[3] or 0)}
            if state == 2 and f[2] and f[2] != self.settings.get("wifi_ip"):
                self.settings = settings.set_private("wifi_ip", f[2])
        elif msg.startswith("ws"):
            rssi, _, name = msg[2:].partition("\t")
            self.wifi_scan.append({"ssid": name, "rssi": int(rssi or 0)})
        elif msg == "w.":
            self.wifi_scan_done.set()

    def wifi_state(self):
        if time.monotonic() - self.pc_net[0] > 30:
            self.pc_net = (time.monotonic(), link.pc_network()[0])
        return {"link": self.link_kind, "port": self.ser.port if self.ser else None, "pc_ssid": self.pc_net[1],
                "status": self.wifi_status, "configured": bool(self.settings.get("wifi_key")),
                "mode": self.settings.get("link", "auto")}

    def wifi_scan_networks(self):
        if self.link_kind is None:
            return {"error": "Module non connecté"}
        self.wifi_scan = []
        self.wifi_scan_done.clear()
        self.send("w?\n")
        if not self.wifi_scan_done.wait(15):
            return {"error": "Pas de réponse du module"}
        return {"networks": sorted(self.wifi_scan, key=lambda n: -n["rssi"])}

    def wifi_configure(self, ssid, password, use_pc=False):
        if self.link_kind != "usb":
            return {"error": "Branche le module en USB pour configurer le Wi-Fi"}
        if use_pc:
            ssid, profile = link.pc_network()
            password = link.pc_network_key(profile) if profile else None
            if not ssid or password is None:
                return {"error": "Réseau de ce PC introuvable : saisis-le à la main"}
        if not ssid or any(c in ssid + password for c in "\t\r\n") \
                or len(ssid.encode()) > 32 or len(password.encode()) > 63:
            return {"error": "Nom ou mot de passe invalide"}
        key = self.settings.get("wifi_key") or link.new_key()
        self.settings = settings.set_private("wifi_key", key)
        self.wifi_status = None
        self.send(f"w={ssid}\t{password}\t{key}\n")
        log.info("Wi-Fi configuré sur le module (%s)", ssid)
        return {"ok": True}

    def wifi_forget(self):
        if self.link_kind != "usb":
            return {"error": "Branche le module en USB pour oublier le Wi-Fi"}
        self.send("w-\n")
        self.settings = settings.set_private("wifi_key", "")
        log.info("Wi-Fi oublié")
        return {"ok": True}

    # --- alertes (affichées par-dessus n'importe quelle app)
    def notify(self, symbol, title, subtitle, color):
        # En réunion : rangée dans l'historique sans bulle ni LEDs qui clignotent.
        kind = "n" if self.meeting_state and self.settings["meeting_silent"] else "N"
        self.send(f"{kind}{symbol}\t{ascii_text(title, 22)}\t{ascii_text(subtitle, 26)}\t{color}\n")
        log.info("alerte : %s - %s", title, subtitle)

    def check_alerts(self):
        fg_exe = self.fg_exe
        # Claude : passage de "au travail" à "attend" ou "terminé".
        try:
            data = json.loads(CLAUDE_STATUS.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        for sid, s in data.items():
            prev, cur = self.claude_prev.get(sid), s.get("state")
            if prev == "working" and cur != "working" and fg_exe != "windowsterminal.exe":
                project = Path(s.get("cwd") or "Claude").name
                if cur == "waiting":
                    self.notify(SYM_WARN, "Claude attend", project, COL_WARN)
                elif cur == "done":
                    self.notify(SYM_OK, "Claude a termine", project, COL_OK)
        self.claude_prev = {sid: s.get("state") for sid, s in data.items()}
        # Bambu : fin, échec, pause.
        for p in self.bambu.summaries():
            prev, cur = self.bambu_prev.get(p["serial"]), p["state"]
            if prev and prev != cur:
                if cur == "FINISH":
                    self.notify(SYM_OK, "Impression terminee", p["name"], COL_OK)
                elif cur == "FAILED":
                    self.notify(SYM_CLOSE, "Impression en echec", p["name"], COL_ERR)
                elif cur == "PAUSE":
                    self.notify(SYM_PAUSE, "Impression en pause", p["name"], COL_WARN)
            self.bambu_prev[p["serial"]] = cur

    # --- permissions Claude Code (répondues à la molette)
    def push_permission(self):
        try:
            sessions = json.loads(CLAUDE_STATUS.read_text(encoding="utf-8"))
        except Exception:
            sessions = {}
        self.permissions.expire(sessions)
        req = self.permissions.current()
        if req and req.id != self.ask_shown:
            opts = "|".join(f"{label},{color}" for label, _, color in req.options)
            self.send(f"X{req.id}\t{ascii_text('Claude - ' + req.project, 24)}\t"
                      f"{ascii_text(req.detail, 70)}\t{opts}\n")
            self.ask_shown = req.id
        elif not req and self.ask_shown:
            self.send(f"x{self.ask_shown}\n")
            self.ask_shown = None

    # --- éditeur de profils (serveur local)
    def editor_icon(self, exe, running):
        """Icône et couleur d'une app pas encore vue au premier plan, si elle tourne (pour l'éditeur)."""
        path = running.get(exe)
        if not path or exe in self.editor_icon_misses:
            return
        img = load_exe_icon(path)
        if img is None:
            self.editor_icon_misses.add(exe)
            return
        buf = io.BytesIO()
        img.resize((48, 48), Image.LANCZOS).save(buf, "PNG")
        self.png_cache[exe] = ("data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
                               "#" + hex_color(accent_from_icon(img)))

    def editor_state(self):
        running = {}
        for proc in psutil.process_iter(["name", "exe"]):
            if proc.info["name"] and proc.info["exe"]:
                running.setdefault(proc.info["name"].lower(), proc.info["exe"])
        overrides = {}
        try:
            overrides = {k.lower(): v for k, v in
                         json.loads((HERE / "profiles.json").read_text(encoding="utf-8")).items()
                         if not k.startswith("_exemple")}
        except Exception:
            pass
        defaults = {k.lower(): v for k, v in DEFAULT_PROFILES.items()}
        special = {"_default": "Par defaut (autres apps)", "_desktop": "Bureau",
                   "_tile_volume": "Tuile Volume", "_tile_dashboard": "Tuile Tableau de bord",
                   "_tile_network": "Tuile Reseau", "_tile_system": "Tuile Systeme"}
        apps = []
        for exe in sorted(set(defaults) | set(overrides) | set(self.recent)):
            prof = overrides.get(exe) or defaults.get(exe) or {}
            if exe not in self.png_cache and not exe.startswith("_"):
                self.editor_icon(exe, running)
            icon, color = self.png_cache.get("desktop" if exe == "_desktop" else exe, (None, "#22D3EE"))
            name = special.get(exe) or prof.get("name") or self.recent.get(exe) or Path(exe).stem.capitalize()
            apps.append({"exe": exe, "name": name, "icon": icon, "color": color,
                         "hasProfile": exe in defaults or exe in overrides, "seen": exe in self.recent})
        actions = [[a, ACTION_LABELS.get(a, a).capitalize()] for a in
                   ("playpause", "next", "prev", "mute", "appmute", "toggle:appvol", "bambu:camera", "bambu:next",
                    "local", "app", "audio", "media:lock")]
        actions += [[k, v.capitalize()] for k, v in ACTION_LABELS.items() if k.startswith("key:")]
        current = None
        if self.app_key == "desktop":
            current = "_desktop"
        elif self.app_key:
            current = self.app_key[1].lower()
        return {"defaults": defaults, "overrides": overrides, "apps": apps, "options": {"actions": actions},
                "settings": settings.public(self.settings), "tiles": settings.TILES,
                "wifi": self.wifi_state(),
                "current": current, "connected": self.ser is not None,
                "port": self.ser.port if self.ser else None}

    def save_overrides(self, overrides):
        clean = {k.lower(): v for k, v in overrides.items() if isinstance(v, dict)}
        (HERE / "profiles.json").write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("profils enregistrés depuis l'éditeur (%d surcharges)", len(clean))

    def request_reload(self):
        self.reload_requested = True

    # --- moniteur système
    def push_system(self):
        self.send(self.sysmon.message())
        s = self.sysmon.snapshot()
        now = time.monotonic()
        if s["gpu_temp"] >= 85 and now - self.alert_times.get("gpu", -1e9) > 600:
            self.alert_times["gpu"] = now
            self.notify(SYM_WARN, "GPU tres chaud", f"{s['gpu_temp']} degres", COL_ERR)
        if s["ram"] >= 92 and now - self.alert_times.get("ram", -1e9) > 600:
            self.alert_times["ram"] = now
            self.notify(SYM_WARN, "Memoire presque pleine", f"RAM a {s['ram']}%", COL_WARN)

    # --- sortie audio (appui long sur la tuile volume)
    def push_audio_device(self):
        self.send_once("D", f"D{ascii_text(audio_out.current()[1], 20)}\n")

    def ask_audio(self):
        self.audio_choices = audio_out.outputs()
        if not self.audio_choices:
            return
        self.audio_ask_id += 1
        cur = audio_out.current()[1]
        opts = "|".join(f"{ascii_text(name, 15)},{audio_out.PALETTE[i % 8]}"
                        for i, (_, name) in enumerate(self.audio_choices))
        self.send(f"X{self.audio_ask_id}\tSortie audio\tactuelle : {ascii_text(cur, 30)}\t{opts}\n")

    def on_audio_choice(self, rid, idx):
        if rid != self.audio_ask_id or not self.audio_choices or not 0 <= idx < len(self.audio_choices):
            return
        dev_id, name = self.audio_choices[idx]
        audio_out.set_default(dev_id)
        self.ev = None  # le volume général suit la nouvelle sortie
        self.sent.pop("D", None)
        self.notify("", "Sortie audio", name, audio_out.PALETTE[idx % 8])
        log.info("sortie audio -> %s", name)

    # --- lanceur radial
    def push_launcher(self, force=False):
        try:
            mtime = launcher.CONFIG.stat().st_mtime
        except OSError:
            mtime = 0
        if not force and mtime == self.launcher_mtime:
            return
        self.launcher_items = launcher.load_items()
        self.launcher_mtime = launcher.CONFIG.stat().st_mtime
        items = self.launcher_items
        self.send(f"O#{len(items)}\n")
        for i, it in enumerate(items):
            sym = launcher.SYMBOLS.get(it.get("symbol", ""), launcher.SYMBOLS["ok"])
            self.send(f"O{i}\t{ascii_text(it.get('label', '?'), 12)}\t{it.get('color', '22D3EE')}\t{sym}\n")
            path = it.get("icon")
            if path:
                if path not in self.launcher_icons:
                    img = load_exe_icon(path)
                    self.launcher_icons[path] = icon_payload(img, 32) if img else None
                payload = self.launcher_icons[path]
                if payload:
                    self.send(f"o{i} 32 32 {len(payload)}\n".encode() + payload)

    def launch(self, idx):
        if self.launcher_items and 0 <= idx < len(self.launcher_items):
            launcher.run(self.launcher_items[idx], press_combo, lambda: user32.LockWorkStation())

    # --- Hue
    def push_hue(self):
        name, permille, value, color, hint = self.hue.view()
        self.send_once("Y", f"Y{ascii_text(name, 18)}\t{permille}\t{value}\t{color}\t{hint}\n")

    # --- événements du module
    def run_action(self, action):
        if not action:
            return
        app = self.app
        if action.startswith("key:"):
            press_combo(action[4:])
        elif action.startswith("toggle:"):
            self.mode_override = None if self.mode_override else action[7:]
            self.push_app(self.app_key)
        elif action == "playpause" and app["widget"] == "media":
            sid, _ = self.media_session()
            if not (sid and self.media.toggle(sid)):
                press_combo("playpause")
        elif action in ("playpause", "next", "prev"):
            press_combo(action)
        elif action == "mute":
            ev = self.endpoint()
            ev.SetMute(0 if ev.GetMute() else 1, None)
        elif action == "appmute":
            for s in app_sessions(app["exe"]):
                s.SetMute(0 if s.GetMute() else 1, None)
        elif action == "bambu:next":
            self.bambu_sel += 1
        elif action == "media:lock":
            self.lock_media() if not self.locked else self.unlock_media()
        elif action == "bambu:camera":
            self.set_camera(not self.cam_on)

    def on_rotate(self, steps):
        app = self.app
        if not app:
            return
        knob = app["knob"]
        if knob == "media":
            self.media_skip(steps, self.app["profile"].get("media_source") or Path(self.app["exe"]).stem)
        elif knob == "keys":
            combo = app["profile"].get("cw" if steps > 0 else "ccw")
            for _ in range(min(abs(steps), 5)):
                if combo:
                    press_combo(combo)
        elif knob == "scroll":
            scroll(steps)
        elif knob == "appvol":
            for s in app_sessions(app["exe"]):
                s.SetMasterVolume(min(1.0, max(0.0, s.GetMasterVolume() + VOL_STEP * steps)), None)
            self.push_appvol()
        else:
            ev = self.endpoint()
            ev.SetMasterVolumeLevelScalar(min(1.0, max(0.0, ev.GetMasterVolumeLevelScalar() + VOL_STEP * steps)), None)
            self.push_master()

    def handle_events(self):
        n = self.ser.in_waiting
        if not n:
            return
        self.rx += self.ser.read(n)
        while b"\n" in self.rx:
            head, rest = self.rx.split(b"\n", 1)
            m = MIRROR_RE.match(head)
            if m:  # zone de l'écran du module (miroir pour l'éditeur 3D), suivie de données binaires
                size = int(m.group(5))
                if len(rest) < size:
                    break  # la suite n'est pas encore arrivée
                self.on_mirror(*map(int, m.groups()[:4]), rest[:size])
                self.rx = rest[size:]
                continue
            raw, self.rx = head, rest
            msg = raw.decode(errors="ignore").strip()
            if not msg:
                continue
            log.debug("module : %s", msg)
            if msg == "p":  # battement de cœur en Wi-Fi
                continue
            if msg[0] == "k":  # touche multimédia (en Wi-Fi, pas d'USB HID vers ce PC)
                press_media(int(msg[1:] or "0", 16))
                continue
            if msg[0] == "w":
                self.on_wifi_message(msg)
                continue
            if msg[0] == "x":
                rid, idx = msg[1:].split()
                if int(rid) >= AUDIO_ASK_BASE:
                    self.on_audio_choice(int(rid), int(idx))
                    continue
                self.permissions.answer(int(rid), int(idx))
                if self.ask_shown == int(rid):
                    self.ask_shown = None
            elif msg == "T":  # triple clic sur la molette : éditeur de profils
                webbrowser.open(f"http://127.0.0.1:{server.PORT}/")
                log.info("éditeur ouvert (triple clic)")
            elif self.locked and msg[0] in "RCL":
                # Mode dédié : molette = pistes, clic = lecture/pause, appui long = déverrouiller.
                if msg[0] == "R":
                    self.media_skip(int(msg[1:]), self.locked["source"])
                elif msg == "C":
                    sid, _ = self.media.find(self.locked["source"])
                    if not (sid and self.media.toggle(sid)):
                        press_combo("playpause")
                else:
                    self.unlock_media()
            elif msg[0] == "Q":
                self.tile = int(msg[1:] or 0)
            elif msg[0] == "M":
                # Diagnostic du module : journalisé au démarrage, ou si le rendu devient lent.
                slow = re.search(r"rendu_max=(\d+)", msg)
                if not slow or int(slow.group(1)) > 150:
                    log.info("module : tas %s", msg[1:])
                self.last_perf = msg[1:]
            elif self.tile == TILE_HUE and msg[0] in "RCL":
                if msg[0] == "R":
                    self.hue.adjust(int(msg[1:]))
                elif msg == "C":
                    self.hue.toggle()
                else:
                    self.hue.next_group()
                self.push_hue()
            elif msg[0] == "o":
                self.launch(int(msg[1:]))
            elif self.tile in TILE_PROFILES and msg[0] in "RCL":
                self.tile_event(msg)
            elif msg[0] == "R":
                self.on_rotate(int(msg[1:]))
            elif msg == "C" and self.app:
                self.run_action(self.app["profile"].get("click"))
            elif msg == "L" and self.app:
                self.run_action(self.app["profile"].get("long"))
            elif msg == "H":
                self.last_master = None
                if self.app_key:
                    self.push_app(self.app_key)

    def reload_profiles_if_changed(self):
        path = HERE / "profiles.json"
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return
        if mtime != self.profiles_mtime or self.reload_requested:
            self.profiles_mtime = mtime
            self.reload_requested = False
            self.profiles = load_profiles()
            self.icon_cache.clear()
            if self.app_key:
                self.push_app(self.app_key)

    def step(self):
        now = time.monotonic()
        self.handle_events()
        self.push_master()
        if now - self.last_fg_check > 0.1:
            self.last_fg_check = now
            self.reload_profiles_if_changed()
            self.check_foreground()
        if now - self.last_appvol_check > 0.15:
            self.last_appvol_check = now
            self.push_appvol()
        if now - self.last_widget > 0.25:
            self.last_widget = now
            self.guarded(self.update_widget)
        if now - self.last_hue > (0.2 if self.tile == TILE_HUE else 2):
            self.last_hue = now
            self.guarded(self.push_hue)
        if now - self.last_slow > 1:
            self.last_slow = now
            self.guarded(self.push_dashboard)
            self.guarded(self.push_sleep)
            self.guarded(self.check_alerts)
            self.guarded(self.push_system)
            self.guarded(self.push_audio_device)
            self.guarded(self.push_launcher)
            self.guarded(self.push_home)
            self.guarded(self.push_tile_config)
            self.guarded(self.push_meeting)
            self.guarded(self.check_away_mute)
        if now - self.last_wifi_poll > 3:
            self.last_wifi_poll = now
            self.guarded(lambda: self.send("w!\n"))
        self.guarded(self.push_camera)
        self.guarded(self.push_mirror_state)
        if self.pending_lock is not None:  # demandé par l'API locale
            want, self.pending_lock = self.pending_lock, None
            if want and not self.locked:
                self.guarded(self.lock_media)
            elif not want and self.locked:
                self.guarded(self.unlock_media)
        if self.locked:
            if now - self.last_spec > 0.033:  # ~30 images/s
                self.last_spec = now
                self.guarded(self.push_spectrum)
            if now - self.last_lock_info > 0.5:
                self.last_lock_info = now
                self.guarded(self.push_locked)
        if now - self.last_net > 0.5:
            self.last_net = now
            self.guarded(lambda: self.send(self.net.message()))
        if now - self.last_perm > 0.2:
            self.last_perm = now
            self.guarded(self.push_permission)

    def guarded(self, fn):
        """Une erreur dans un widget ne doit jamais couper la liaison."""
        try:
            fn()
        except serial.SerialException:
            raise
        except Exception:
            log.exception(fn.__name__)

    def run(self):
        comtypes.CoInitialize()
        while True:
            try:
                self.tray.set_connected(self.ser is not None)
                if self.relink and self.ser:
                    log.info("changement de liaison : %s", self.settings["link"])
                    self.ser.close()
                    self.ser = self.link_kind = None
                self.relink = False
                if self.updating:  # mise à jour du firmware : on libère le port
                    if self.ser:
                        self.ser.close()
                        self.ser = self.link_kind = None
                    time.sleep(0.5)
                    continue
                if self.ser is None and not self.connect():
                    time.sleep(1)
                    continue
                self.step()
                time.sleep(0.02)
            except (serial.SerialException, OSError) as e:
                log.info("port perdu (%s), nouvelle tentative", e)
                try:
                    self.ser and self.ser.close()
                except Exception:
                    pass
                self.ser = self.link_kind = None
                time.sleep(1)
            except comtypes.COMError as e:
                log.info("erreur audio (%s)", e)
                self.ev = None
                time.sleep(0.5)
            except Exception:
                log.exception("erreur inattendue")
                time.sleep(1)


if __name__ == "__main__":
    Companion().run()
