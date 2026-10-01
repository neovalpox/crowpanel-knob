"""Sorties audio Windows : liste lisible des sorties utiles et changement de sortie par défaut."""
import re
import warnings

from pycaw.constants import DEVICE_STATE, EDataFlow, ERole
from pycaw.pycaw import AudioUtilities

# Sorties virtuelles sans intérêt pour un choix rapide.
HIDDEN = ("steam streaming", "oculus", "display audio", "microphone")
GENERIC = ("casque", "haut-parleurs", "speakers", "headphones", "headset", "ecouteurs", "écouteurs")
PALETTE = ["22D3EE", "F472B6", "3DDC84", "FFB020", "A78BFA", "FF4436", "76B900", "FFCD42"]


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


def outputs():
    """[(id, nom court)] des sorties actives utiles, sans doublon de nom."""
    enum = AudioUtilities.GetDeviceEnumerator()
    coll = enum.EnumAudioEndpoints(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value)
    out, seen = [], set()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for i in range(coll.GetCount()):
            dev = AudioUtilities.CreateDevice(coll.Item(i))
            name = dev.FriendlyName or ""
            if any(h in name.lower() for h in HIDDEN):
                continue
            short = short_name(name)
            if short.lower() in seen:
                continue
            seen.add(short.lower())
            out.append((dev.id, short))
    return out[:8]


def current():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dev = AudioUtilities.GetSpeakers()
        return dev.id, short_name(dev.FriendlyName or "")


def set_default(dev_id):
    AudioUtilities.SetDefaultDevice(dev_id, [ERole.eConsole, ERole.eMultimedia, ERole.eCommunications])
