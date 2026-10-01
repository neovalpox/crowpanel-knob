"""Philips Hue (API locale v1) : pièces, luminosité, couleur, association au pont.

La clé d'API est stockée dans hue.json (ignoré par git). Sans clé, un clic sur la
tuile Hue lance l'association : il suffit d'appuyer sur le bouton du pont.
"""
import json
import logging
import threading
import time
import urllib.request
from pathlib import Path

log = logging.getLogger("knob.hue")
CONFIG = Path(__file__).resolve().parent / "hue.json"


def _request(method, url, body=None, timeout=4):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def xy_to_rgb(x, y, bri=254):
    """CIE xy (gamut large) -> sRGB, ravivé pour l'écran."""
    z = 1.0 - x - y
    Y = 1.0
    X = (Y / y) * x if y else 0
    Z = (Y / y) * z if y else 0
    r = X * 1.656492 - Y * 0.354851 - Z * 0.255038
    g = -X * 0.707196 + Y * 1.655397 + Z * 0.036152
    b = X * 0.051713 - Y * 0.121364 + Z * 1.011530
    rgb = [max(0.0, c) for c in (r, g, b)]
    rgb = [12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055 for c in rgb]
    m = max(rgb) or 1
    return tuple(int(255 * c / m) for c in rgb)


def ct_to_rgb(ct):
    """Température de couleur (mired) -> teinte chaude/froide approximative."""
    kelvin = 1_000_000 / max(ct, 153)
    t = (kelvin - 2000) / 4500  # 0 = très chaud, 1 = froid
    t = min(1, max(0, t))
    return (255, int(170 + 70 * t), int(80 + 175 * t))


class Hue:
    def __init__(self):
        cfg = {}
        try:
            cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        except Exception:
            pass
        self.ip = cfg.get("ip")
        self.key = cfg.get("key")
        self.groups = []      # [(id, nom, état dict)]
        self.sel = cfg.get("group")
        self.pairing_until = 0
        self.pending_bri = None
        self.lock = threading.Lock()
        self.last_poll = 0
        threading.Thread(target=self._loop, daemon=True, name="hue").start()

    # --- persistance
    def _save(self):
        CONFIG.write_text(json.dumps({"ip": self.ip, "key": self.key, "group": self.sel}, indent=2), encoding="utf-8")

    @property
    def base(self):
        return f"http://{self.ip}/api/{self.key}"

    # --- boucle de fond : découverte, association, rafraîchissement, envoi luminosité
    def _loop(self):
        while True:
            try:
                if not self.ip:
                    found = _request("GET", "https://discovery.meethue.com/")
                    if found:
                        self.ip = found[0]["internalipaddress"]
                        self._save()
                elif not self.key:
                    if time.time() < self.pairing_until:
                        res = _request("POST", f"http://{self.ip}/api", {"devicetype": "crowpanel_knob#pc"})
                        if res and "success" in res[0]:
                            self.key = res[0]["success"]["username"]
                            self.pairing_until = 0
                            self._save()
                            log.info("hue : associé")
                else:
                    self._flush_bri()
                    if time.time() - self.last_poll > 2:
                        self._poll()
            except Exception as e:
                log.debug("hue : %s", e)
                time.sleep(2)
            time.sleep(0.1)

    def _poll(self):
        groups = _request("GET", f"{self.base}/groups")
        out = [(gid, g["name"], g) for gid, g in groups.items() if g.get("type") in ("Room", "Zone")]
        out.sort(key=lambda t: (t[2].get("type") != "Room", t[1]))
        with self.lock:
            self.groups = out
            if out and self.sel not in [g[0] for g in out]:
                self.sel = out[0][0]
        self.last_poll = time.time()

    def _flush_bri(self):
        with self.lock:
            bri, self.pending_bri = self.pending_bri, None
        if bri is None or not self.sel:
            return
        _request("PUT", f"{self.base}/groups/{self.sel}/action", {"on": bri > 0, "bri": max(1, bri)})
        self.last_poll = 0

    # --- actions
    def current(self):
        with self.lock:
            for g in self.groups:
                if g[0] == self.sel:
                    return g
        return None

    def adjust(self, steps):
        g = self.current()
        if not g:
            return
        with self.lock:
            base = self.pending_bri
            if base is None:
                act = g[2].get("action", {})
                base = act.get("bri", 0) if g[2].get("state", {}).get("any_on") else 0
            self.pending_bri = min(254, max(0, base + steps * 13))
            # Mise à jour optimiste pour un affichage immédiat.
            g[2].setdefault("action", {})["bri"] = max(1, self.pending_bri)
            g[2].setdefault("state", {})["any_on"] = self.pending_bri > 0

    def toggle(self):
        if not self.key:
            self.pairing_until = time.time() + 30
            return
        g = self.current()
        if g:
            on = not g[2].get("state", {}).get("any_on")
            threading.Thread(target=lambda: _request("PUT", f"{self.base}/groups/{g[0]}/action", {"on": on}),
                             daemon=True).start()
            g[2].setdefault("state", {})["any_on"] = on
            self.last_poll = time.time() - 1.5

    def next_group(self):
        with self.lock:
            ids = [g[0] for g in self.groups]
            if ids:
                self.sel = ids[(ids.index(self.sel) + 1) % len(ids)] if self.sel in ids else ids[0]
        self._save()

    def view(self):
        """(nom, pour mille, texte, couleur hex, indice) pour la tuile."""
        if not self.ip:
            return "Hue", 0, "--", "7C8494", "recherche du pont..."
        if not self.key:
            if time.time() < self.pairing_until:
                return "Hue", 0, "--", "FFB547", "appuie sur le pont !"
            return "Hue", 0, "--", "FFB547", "clic : associer"
        g = self.current()
        if not g:
            return "Hue", 0, "--", "7C8494", "aucune piece"
        _, name, data = g
        act, on = data.get("action", {}), data.get("state", {}).get("any_on")
        if not on:
            return name, 0, "OFF", "7C8494", "clic : allumer"
        bri = act.get("bri", 254)
        if act.get("colormode") == "xy" and "xy" in act:
            rgb = xy_to_rgb(*act["xy"])
        elif "ct" in act:
            rgb = ct_to_rgb(act["ct"])
        else:
            rgb = (255, 181, 71)
        pct = round(bri * 100 / 254)
        return name, pct * 10, f"{pct}%", "%02X%02X%02X" % rgb, "appui long : piece suivante"
