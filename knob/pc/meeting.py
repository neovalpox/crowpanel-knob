"""Détection d'une réunion : une app utilise le micro (registre de confidentialité Windows),
et état du micro (coupé ou non, via Sonar s'il route le micro, sinon Windows)."""
import json
import urllib.request
import warnings
import winreg
from pathlib import Path

import audio_out

BASE = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
# Logiciels qui tiennent le micro sans être une réunion.
IGNORED = ("steelseries", "sonar", "nvidia broadcast", "voicemeeter", "obs64", "knob")
NAMES = {"ms-teams": "Teams", "teams": "Teams", "discord": "Discord", "zoom": "Zoom",
         "mattermost": "Mattermost", "telegram": "Telegram", "whatsapp": "WhatsApp", "chrome": "Chrome",
         "msedge": "Edge", "firefox": "Firefox", "slack": "Slack"}


def _app_name(key_name):
    raw = key_name.split("#")[-1]
    stem = Path(raw).stem if "#" in key_name else raw.split("_")[0].split(".")[-1]
    low = stem.lower()
    for k, v in NAMES.items():
        if k in low:
            return v
    return stem[:14]


def apps_using_mic():
    found = []

    def walk(path, depth):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            return
        with key:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(key, i)
                except OSError:
                    break
                i += 1
                full = path + "\\" + sub
                if sub == "NonPackaged" and depth == 0:
                    walk(full, 1)
                    continue
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, full) as s:
                        start = winreg.QueryValueEx(s, "LastUsedTimeStart")[0]
                        stop = winreg.QueryValueEx(s, "LastUsedTimeStop")[0]
                except OSError:
                    continue
                if start and stop == 0 and not any(x in sub.lower() for x in IGNORED):
                    found.append(_app_name(sub))

    walk(BASE, 0)
    return found


def mic_muted():
    """True si le micro est coupé (canal micro de Sonar, sinon micro par défaut de Windows)."""
    base = audio_out.sonar_base()
    if base:
        try:
            with urllib.request.urlopen(f"{base}/volumeSettings/classic", timeout=2) as r:
                cap = json.loads(r.read())["devices"]["chatCapture"]["classic"]
            return bool(cap.get("muted"))
        except Exception:
            pass
    try:
        from pycaw.pycaw import AudioUtilities
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return bool(AudioUtilities.GetMicrophone().EndpointVolume.GetMute())
    except Exception:
        return False


def state():
    """(0|1|2, libellé) : 0 = pas de réunion, 1 = micro ouvert, 2 = micro coupé."""
    apps = apps_using_mic()
    if not apps:
        return 0, ""
    muted = mic_muted()
    return (2 if muted else 1), f"{apps[0]} - micro {'coupe' if muted else 'ouvert'}"
