"""Données du tableau de bord : date, météo (Open-Meteo) et prochain rendez-vous (Outlook).

Tout est rafraîchi dans un thread pour ne jamais bloquer la boucle principale.
"""
import json
import logging
import threading
import time
import unicodedata
import urllib.request
from datetime import datetime, timedelta

log = logging.getLogger("knob.dashboard")

DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTHS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout",
          "septembre", "octobre", "novembre", "decembre"]

# Codes météo WMO -> description courte (police sans accents).
WEATHER = {0: "Ciel clair", 1: "Peu nuageux", 2: "Nuageux", 3: "Couvert", 45: "Brouillard", 48: "Brouillard",
           51: "Bruine", 53: "Bruine", 55: "Bruine", 61: "Pluie", 63: "Pluie", 65: "Forte pluie",
           66: "Pluie verglac.", 67: "Pluie verglac.", 71: "Neige", 73: "Neige", 75: "Forte neige",
           77: "Neige", 80: "Averses", 81: "Averses", 82: "Fortes averses", 85: "Averses neige",
           86: "Averses neige", 95: "Orage", 96: "Orage grele", 99: "Orage grele"}


def ascii_text(s, maxlen):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().replace("\t", " ").strip()
    return s if len(s) <= maxlen else s[: maxlen - 1].rstrip() + "."


def date_text(now=None):
    now = now or datetime.now()
    return f"{DAYS[now.weekday()]} {now.day} {MONTHS[now.month - 1]}"


def outlook_date(dt):
    """Date au format court de Windows : Outlook.Restrict l'interprète selon la locale."""
    import ctypes
    buf = ctypes.create_unicode_buffer(80)
    ctypes.windll.kernel32.GetLocaleInfoEx(None, 0x1F, buf, 80)  # LOCALE_SSHORTDATE
    pattern = buf.value or "dd/MM/yyyy"
    for token, fmt in (("yyyy", "%Y"), ("yy", "%y"), ("MM", "%m"), ("dd", "%d")):
        pattern = pattern.replace(token, fmt)
    pattern = pattern.replace("M", "%#m").replace("d", "%#d") if "%m" not in pattern else pattern
    return dt.strftime(pattern) + dt.strftime(" %H:%M")


def _get_json(url):
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.loads(r.read())


class Dashboard:
    def __init__(self):
        self.weather = ("", "")   # (température, description)
        self.event = ""
        self._loc = None
        threading.Thread(target=self._weather_loop, daemon=True, name="weather").start()
        threading.Thread(target=self._calendar_loop, daemon=True, name="calendar").start()

    # --- météo
    def _weather_loop(self):
        while True:
            try:
                if self._loc is None:
                    geo = _get_json("http://ip-api.com/json/?fields=lat,lon,city")
                    self._loc = (geo["lat"], geo["lon"])
                lat, lon = self._loc
                data = _get_json("https://api.open-meteo.com/v1/forecast"
                                 f"?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code")
                cur = data["current"]
                self.weather = (str(round(cur["temperature_2m"])), WEATHER.get(cur["weather_code"], ""))
                time.sleep(15 * 60)
            except Exception as e:
                log.info("météo : %s", e)
                time.sleep(120)

    # --- agenda Outlook (seulement s'il tourne déjà : on ne le lance jamais)
    def _calendar_loop(self):
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        while True:
            try:
                self.event = self._next_event(win32com.client)
            except Exception as e:
                self.event = ""
                log.debug("agenda : %s", e)
            time.sleep(300)

    @staticmethod
    def _next_event(win32):
        outlook = win32.GetActiveObject("Outlook.Application")
        items = outlook.GetNamespace("MAPI").GetDefaultFolder(9).Items  # 9 = calendrier
        items.IncludeRecurrences = True
        items.Sort("[Start]")
        now = datetime.now()
        start = outlook_date(now)
        end = outlook_date(now + timedelta(days=2))
        for it in items.Restrict(f"[End] >= '{start}' AND [Start] <= '{end}'"):
            if it.AllDayEvent:
                continue
            when = datetime.fromtimestamp(it.Start.timestamp())
            day = "" if when.date() == now.date() else ("demain " if when.date() == now.date() + timedelta(1) else
                                                       f"{DAYS[when.weekday()][:3]}. ")
            return ascii_text(f"{day}{when:%H:%M} {it.Subject}", 40)
        return ""
