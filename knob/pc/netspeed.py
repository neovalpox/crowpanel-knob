"""Débits réseau du PC (montant / descendant) pour la tuile réseau.

On additionne les cartes physiques actives : les interfaces virtuelles (loopback,
Hyper-V, VPN, machines virtuelles) dupliqueraient le trafic.
"""
import math
import time

import psutil

VIRTUAL = ("loopback", "vethernet", "hyper-v", "virtualbox", "vmware", "wsl", "tap-", "tailscale",
           "zerotier", "wireguard", "npcap", "bluetooth")
SCALE_MAX = 125_000_000  # 1 Gbit/s en octets/s : haut de l'échelle logarithmique
SMOOTH = 0.5             # lissage exponentiel (0 = brut, 1 = figé)


def physical_counters():
    stats = psutil.net_if_stats()
    total_recv = total_sent = 0
    for name, c in psutil.net_io_counters(pernic=True).items():
        st = stats.get(name)
        if not st or not st.isup or any(v in name.lower() for v in VIRTUAL):
            continue
        total_recv += c.bytes_recv
        total_sent += c.bytes_sent
    return total_recv, total_sent


def fmt_rate(bps):
    """Octets/s -> texte court à la française (police sans accents)."""
    for unit, div in (("Go/s", 1e9), ("Mo/s", 1e6), ("ko/s", 1e3)):
        if bps >= div:
            v = bps / div
            return (f"{v:.1f}" if v < 100 else f"{v:.0f}").replace(".", ",") + " " + unit
    return f"{bps:.0f} o/s"


def log_permille(bps):
    return int(1000 * math.log10(1 + bps) / math.log10(1 + SCALE_MAX)) if bps > 0 else 0


class NetSpeed:
    def __init__(self):
        self.last = physical_counters()
        self.last_t = time.monotonic()
        self.down = self.up = 0.0

    def sample(self):
        """Débits lissés (octets/s) depuis l'appel précédent."""
        now, cur = time.monotonic(), physical_counters()
        dt = max(now - self.last_t, 1e-3)
        down = max(0, cur[0] - self.last[0]) / dt
        up = max(0, cur[1] - self.last[1]) / dt
        self.last, self.last_t = cur, now
        self.down = SMOOTH * self.down + (1 - SMOOTH) * down
        self.up = SMOOTH * self.up + (1 - SMOOTH) * up
        return self.down, self.up

    def message(self):
        down, up = self.sample()
        return f"B{log_permille(down)}\t{fmt_rate(down)}\t{log_permille(up)}\t{fmt_rate(up)}\n"
