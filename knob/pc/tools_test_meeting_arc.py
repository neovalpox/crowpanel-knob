"""Test : affiche le texte de réunion courbé sur le module (en Wi-Fi) et enregistre l'écran.

Prend la place du compagnon quelques secondes (il se reconnecte tout seul ensuite).
Usage : .venv\\Scripts\\python tools_test_meeting_arc.py [état 1|2] [texte]
"""
import re
import sys
import time

import numpy as np
from PIL import Image

import link
import settings


def decode(data, n):
    out, i, k = np.empty(n, np.uint16), 0, 0
    while i < len(data) and k < n:
        b = data[i]
        if b >= 128:
            out[k:k + b - 127] = data[i + 1] | data[i + 2] << 8
            k, i = k + b - 127, i + 3
        else:
            out[k:k + b + 1] = np.frombuffer(data, "<u2", b + 1, i + 1)
            k, i = k + b + 1, i + 3 + 2 * b
    return out


def main():
    state = sys.argv[1] if len(sys.argv) > 1 else "1"
    text = sys.argv[2] if len(sys.argv) > 2 else "Discord - micro ouvert"
    s = settings.load()
    net = link.NetLink(s["wifi_ip"], s["wifi_key"])
    screen = np.zeros((240, 240), np.uint16)
    net.write(f"m{state}\t{text}\ns1\n".encode())
    end, buf = time.monotonic() + 6, b""
    while time.monotonic() < end:
        net.write(b"V50 M0\n")  # garde le module synchronisé
        time.sleep(0.2)
        n = net.in_waiting
        buf += net.read(n)
        while b"\n" in buf:
            head, rest = buf.split(b"\n", 1)
            m = re.match(rb"^s(\d+) (\d+) (\d+) (\d+) (\d+)$", head)
            if not m:
                if head.startswith(b"M"):
                    print("module :", head.decode(errors="ignore"))
                buf = rest
                continue
            x, y, w, h, size = map(int, m.groups())
            if len(rest) < size:
                break
            screen[y:y + h, x:x + w] = decode(rest[:size], w * h).reshape(h, w)
            buf = rest[size:]
    net.write(b"s0\n")
    net.close()
    px = screen.astype(np.uint32)
    rgb = np.dstack([((px >> 11) & 31) * 255 // 31, ((px >> 5) & 63) * 255 // 63, (px & 31) * 255 // 31])
    Image.fromarray(rgb.astype(np.uint8), "RGB").resize((480, 480), Image.LANCZOS).save("meeting_arc.png")
    print("écran enregistré dans meeting_arc.png")


if __name__ == "__main__":
    main()
