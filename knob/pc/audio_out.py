"""Sorties audio : liste lisible des sorties utiles et changement de sortie.

Si SteelSeries Sonar tourne (mode classique), changer la sortie par défaut de Windows ne sert
à rien : Sonar attache les applications à ses périphériques virtuels et renvoie le son vers
UNE sortie physique par canal. On change donc la sortie des canaux Sonar via son API locale
(adresse lue dans C:\\ProgramData\\SteelSeries\\GG\\coreProps.json). Sans Sonar, on change la
sortie par défaut de Windows.
"""
import json
import logging
import re
import ssl
import urllib.parse
import urllib.request
import warnings
from pathlib import Path

from pycaw.constants import DEVICE_STATE, EDataFlow, ERole
from pycaw.pycaw import AudioUtilities

log = logging.getLogger("knob.audio")

# Sorties virtuelles sans intérêt pour un choix rapide.
HIDDEN = ("steam streaming", "oculus", "display audio", "microphone")
GENERIC = ("casque", "haut-parleurs", "speakers", "headphones", "headset", "ecouteurs", "écouteurs")
PALETTE = ["22D3EE", "F472B6", "3DDC84", "FFB020", "A78BFA", "FF4436", "76B900", "FFCD42"]
SONAR_PROPS = Path(r"C:\ProgramData\SteelSeries\GG\coreProps.json")
SONAR_OUT_CHANNELS = ("game", "chat", "media", "aux")  # « mic » reste tel quel


def short_name(friendly):
    """« Casque (Arctis Nova Pro Wireless) » -> « Arctis Nova Pro » ; « SteelSeries Sonar - Chat (...) » -> « Sonar Chat »."""
    m = re.match(r"(.*?)\s*\((.*)\)$", friendly)
    first, inner = (m.group(1), m.group(2)) if m else (friendly, "")
    if "sonar" in first.lower():
        name = "Sonar " + first.split("-")[-1].strip()
    elif first.lower() in GENERIC and inner:
        name = inner
    else:
        name = first
    name = re.sub(r"\b(Wireless|High Definition Audio|Virtual Audio Device)\b", "", name).strip(" -")
    return name[:15].strip()


def _useful(friendly, physical_only=False):
    low = friendly.lower()
    if any(h in low for h in HIDDEN):
        return False
    return not (physical_only and "sonar" in low)


def _dedupe(devices):
    out, seen = [], set()
    for dev_id, friendly in devices:
        short = short_name(friendly)
        if short.lower() not in seen:
            seen.add(short.lower())
            out.append((dev_id, short))
    return out[:8]


# ---------------------------------------------------------------- SteelSeries Sonar

def _http(method, url, ctx=None):
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=3, context=ctx) as r:
        return json.loads(r.read() or b"null")


def sonar_base():
    """URL de l'API Sonar si Sonar tourne en mode classique, sinon None."""
    try:
        gg = json.loads(SONAR_PROPS.read_text(encoding="utf-8"))["ggEncryptedAddress"]
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE  # certificat local auto-signé
        sonar = _http("GET", f"https://{gg}/subApps", ctx)["subApps"]["sonar"]
        if not (sonar.get("isEnabled") and sonar.get("isRunning")):
            return None
        base = sonar["metadata"]["webServerAddress"]
        return base if _http("GET", f"{base}/mode") == "classic" else None
    except Exception:
        return None


# ---------------------------------------------------------------- API

def outputs():
    """[(id, nom court)] des sorties utiles (physiques si Sonar route le son)."""
    base = sonar_base()
    if base:
        devs = _http("GET", f"{base}/audioDevices")
        return _dedupe((d["id"], d["friendlyName"]) for d in devs
                       if d.get("dataFlow") == "render" and _useful(d["friendlyName"], physical_only=True))
    enum = AudioUtilities.GetDeviceEnumerator()
    coll = enum.EnumAudioEndpoints(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value)
    devices = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for i in range(coll.GetCount()):
            dev = AudioUtilities.CreateDevice(coll.Item(i))
            if _useful(dev.FriendlyName or ""):
                devices.append((dev.id, dev.FriendlyName))
    return _dedupe(devices)


def current():
    """(id, nom court) de la sortie qui joue vraiment le son."""
    base = sonar_base()
    if base:
        game = next(c for c in _http("GET", f"{base}/classicRedirections") if c["id"] == "game")
        names = {d["id"]: d["friendlyName"] for d in _http("GET", f"{base}/audioDevices")}
        return game["deviceId"], short_name(names.get(game["deviceId"], "?"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dev = AudioUtilities.GetSpeakers()
        return dev.id, short_name(dev.FriendlyName or "")


def _sonar_virtual(base, channel_name):
    for d in _http("GET", f"{base}/audioDevices"):
        if d.get("dataFlow") == "render" and f"sonar - {channel_name}" in d["friendlyName"].lower():
            return d["id"]
    return None


def master_muted():
    """Son général coupé ? (master de Sonar s'il route le son, sinon sortie Windows)."""
    base = sonar_base()
    if base:
        return bool(_http("GET", f"{base}/volumeSettings/classic")["masters"]["classic"].get("muted"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return bool(AudioUtilities.GetSpeakers().EndpointVolume.GetMute())


def set_master_mute(on):
    """Coupe / rétablit tout le son : avec Sonar, la sortie Windows ne couperait que le canal Game."""
    base = sonar_base()
    if base:
        _http("PUT", f"{base}/volumeSettings/classic/master/Mute/{'true' if on else 'false'}")
        return
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        AudioUtilities.GetSpeakers().EndpointVolume.SetMute(1 if on else 0, None)


def set_default(dev_id):
    base = sonar_base()
    if base:
        quoted = urllib.parse.quote(dev_id)
        for channel in SONAR_OUT_CHANNELS:
            _http("PUT", f"{base}/classicRedirections/{channel}/deviceId/{quoted}")
        # Windows doit rester sur les entrées de Sonar, sinon les apps le contournent.
        gaming, chat = _sonar_virtual(base, "gaming"), _sonar_virtual(base, "chat")
        if gaming:
            AudioUtilities.SetDefaultDevice(gaming, [ERole.eConsole, ERole.eMultimedia])
        if chat:
            AudioUtilities.SetDefaultDevice(chat, [ERole.eCommunications])
        return
    AudioUtilities.SetDefaultDevice(dev_id, [ERole.eConsole, ERole.eMultimedia, ERole.eCommunications])
