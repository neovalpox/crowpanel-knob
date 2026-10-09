"""Réglages du compagnon (settings.json, modifiables depuis l'éditeur)."""
import json
from pathlib import Path

PATH = Path(__file__).resolve().parent / "settings.json"
TILES = ["app", "volume", "dashboard", "network", "system", "hue"]  # ordre du firmware

DEFAULTS = {
    "home_tile": "volume",      # tuile d'accueil
    "app_return_s": 5,          # retour à l'accueil depuis l'app (0 = jamais)
    "other_return_s": 8,        # depuis volume / Hue quand ce n'est pas l'accueil (0 = jamais)
    "night_start": 22,          # mode nuit : heure de début
    "night_end": 7,             #             heure de fin
    "night_backlight": 90,      # luminosité de l'écran la nuit (0-220)
    "night_leds": 25,           # LEDs la nuit, en % (0-100)
    "meeting_silent": True,     # alertes silencieuses (historique seulement) pendant une réunion
    "away_mute_min": 10,        # coupe le son après N minutes d'absence (0 = jamais), rétabli au retour
}


def load():
    data = dict(DEFAULTS)
    try:
        data.update(json.loads(PATH.read_text(encoding="utf-8")))
    except Exception:
        pass
    return data


def save(values):
    data = load()
    for key, default in DEFAULTS.items():
        if key in values:
            v = values[key]
            data[key] = type(default)(v) if not isinstance(default, bool) else bool(v)
    PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def home_message(s):
    tile = TILES.index(s["home_tile"]) if s["home_tile"] in TILES else 1
    return f"Q{tile} {int(s['app_return_s'] * 1000)} {int(s['other_return_s'] * 1000)}\n"
