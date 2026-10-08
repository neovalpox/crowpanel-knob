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
import logging
import os
import time
import unicodedata
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
import audio_out
import launcher
import media
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


def press_combo(combo):
    keys = [VK.get(k) or ord(k.upper()) for k in combo.lower().split("+")]
    for k in keys:
        user32.keybd_event(k, 0, 0, 0)
    for k in reversed(keys):
        user32.keybd_event(k, 0, 2, 0)


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
    # ignore : la fenêtre ne change pas l'écran (on garde l'app précédente).
    "explorer.exe": {"name": "Explorateur", "ignore": True, "knob": "scroll", "click": "key:alt+up", "long": None},
    "spotify.exe": {"name": "Spotify", "widget": "media", "media_source": "spotify",
                    "click": "playpause", "long": "toggle:appvol"},
    "vlc.exe": {"name": "VLC", "widget": "media", "media_source": "vlc", "click": "playpause", "long": "toggle:appvol"},
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
    "deskflow.exe": {"name": "Deskflow", "knob": "master", "click": "mute", "long": None},
    "lightburn.exe": {"name": "LightBurn", "knob": "scroll", "click": None, "long": None},
    "excel.exe": {"name": "Excel", "knob": "scroll", "click": "key:ctrl+s", "long": None},
}

ACTION_LABELS = {
    "playpause": "play/pause", "next": "suivant", "prev": "precedent", "mute": "mute",
    "appmute": "mute app", "key:ctrl+tab": "onglet suivant", "key:ctrl+s": "enregistrer",
    "key:ctrl+shift+m": "mute micro", "key:alt+up": "dossier parent", "key:enter": "entree",
    "key:ctrl+r": "trancher", "key:ctrl+shift+o": "nouveau chat", "key:esc": "echap",
    "key:ctrl+k": "recherche", "key:ctrl+q": "marquer lu", "toggle:appvol": "volume",
}
KNOB_LABELS = {"scroll": "defiler", "appvol": "volume app", "master": "volume", "media": "pistes"}


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
        self.recent = {}           # apps vues au premier plan (éditeur de profils)
        self.png_cache = {}        # icônes en PNG base64 pour l'éditeur
        self.reload_requested = False
        self.ask_shown = None      # id de la demande de permission affichée
        self.permissions = permissions.Permissions(
            lambda: self.fg_exe == "windowsterminal.exe")
        server.start(self)
        self.tray = tray.Tray(self, f"http://127.0.0.1:{server.PORT}/", HERE / "knob_companion.log")

    # --- liaison série
    def connect(self):
        port = next((p.device for p in list_ports.comports()
                     if p.vid == VID_ESPRESSIF and p.pid == PID_KNOB), None)
        if not port:
            return False
        ser = serial.Serial()
        ser.port, ser.baudrate, ser.timeout, ser.write_timeout = port, 115200, 0, 2
        # DTR obligatoire : sans lui, le CDC TinyUSB du module refuse d'émettre
        # (molette/clic perdus). RTS reste bas : seule la séquence RTS/DTR
        # complète redémarre le module en mode flash.
        ser.dtr, ser.rts = True, False
        ser.open()
        self.ser = ser
        self.last_master = None
        self.app_key = None
        self.sent = {}
        self.last_clock = 0
        self.ask_shown = None
        self.launcher_mtime = 0  # renvoie le lanceur au module (re)connecté
        self.last_fg = None
        self.app = None
        self.rx = b""
        log.info("connecté sur %s", port)
        return True

    def send(self, data):
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
    def push_sleep(self):
        locked, idle = is_locked(), idle_seconds()
        night = datetime.now().hour >= 23 or datetime.now().hour < 7
        if night and (locked or idle > 120):
            z = "Z8 0 1"            # nuit : quasi éteint, LEDs coupées, horloge
        elif locked or idle > 600:
            z = "Z70 0 1"           # absent : tamisé, horloge
        else:
            z = "Z220 1 0"
        self.send_once("Z", z + "\n")

    # --- alertes (affichées par-dessus n'importe quelle app)
    def notify(self, symbol, title, subtitle, color):
        self.send(f"N{symbol}\t{ascii_text(title, 22)}\t{ascii_text(subtitle, 26)}\t{color}\n")
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
    def editor_state(self):
        overrides = {}
        try:
            overrides = {k.lower(): v for k, v in
                         json.loads((HERE / "profiles.json").read_text(encoding="utf-8")).items()
                         if not k.startswith("_exemple")}
        except Exception:
            pass
        defaults = {k.lower(): v for k, v in DEFAULT_PROFILES.items()}
        special = {"_default": "Par defaut (autres apps)", "_desktop": "Bureau"}
        apps = []
        for exe in sorted(set(defaults) | set(overrides) | set(self.recent)):
            prof = overrides.get(exe) or defaults.get(exe) or {}
            icon, color = self.png_cache.get("desktop" if exe == "_desktop" else exe, (None, "#22D3EE"))
            name = special.get(exe) or prof.get("name") or self.recent.get(exe) or Path(exe).stem.capitalize()
            apps.append({"exe": exe, "name": name, "icon": icon, "color": color,
                         "hasProfile": exe in defaults or exe in overrides})
        actions = [[a, ACTION_LABELS.get(a, a).capitalize()] for a in
                   ("playpause", "next", "prev", "mute", "appmute", "toggle:appvol", "bambu:camera", "bambu:next")]
        actions += [[k, v.capitalize()] for k, v in ACTION_LABELS.items() if k.startswith("key:")]
        current = None
        if self.app_key == "desktop":
            current = "_desktop"
        elif self.app_key:
            current = self.app_key[1].lower()
        return {"defaults": defaults, "overrides": overrides, "apps": apps, "options": {"actions": actions},
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
        elif action == "bambu:camera":
            self.set_camera(not self.cam_on)

    def on_rotate(self, steps):
        app = self.app
        if not app:
            return
        knob = app["knob"]
        if knob == "media":
            now = time.monotonic()
            if now - self.last_skip < 0.3:  # un cran = une piste, même en tournant vite
                return
            self.last_skip = now
            sid, _ = self.media_session()
            ok = sid and (self.media.next(sid) if steps > 0 else self.media.prev(sid))
            if not ok:
                press_combo("next" if steps > 0 else "prev")
            self.send(f"F{SYM_NEXT if steps > 0 else SYM_PREV}\n")
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
            raw, self.rx = self.rx.split(b"\n", 1)
            msg = raw.decode(errors="ignore").strip()
            if not msg:
                continue
            log.debug("module : %s", msg)
            if msg[0] == "x":
                rid, idx = msg[1:].split()
                if int(rid) >= AUDIO_ASK_BASE:
                    self.on_audio_choice(int(rid), int(idx))
                    continue
                self.permissions.answer(int(rid), int(idx))
                if self.ask_shown == int(rid):
                    self.ask_shown = None
            elif msg[0] == "Q":
                self.tile = int(msg[1:] or 0)
            elif msg[0] == "M":
                log.info("module : %s octets de tas libres", msg[1:])
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
            elif self.tile == TILE_VOL and msg == "L":
                self.ask_audio()
            elif self.tile in (TILE_DASH, TILE_NET, TILE_SYS, TILE_VOL):
                pass  # tuiles d'affichage : rien à piloter
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
        self.guarded(self.push_camera)
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
                self.ser = None
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
