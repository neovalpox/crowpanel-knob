"""Bande-son du trailer, composée par code (donc libre de droits).

Synthwave à 120 BPM (un temps = 0,5 s, une mesure = 2 s), 46 s, calée sur trailer.html :
  0-4 s   intro : nappe + montée de bruit, impact à 4 s
  4-38 s  kick, clap, charleston (doubles croches à partir de 16 s), basse, arpège, nappe compressée
  38-42 s pause : nappe + arpège, montée vers la fin
  42-46 s impact final, la nappe s'éteint
Usage : python music.py  ->  music.wav
"""
import wave

import numpy as np

SR = 44100
BPM = 120
BEAT = 60 / BPM
DUR = 46.0
N = int(SR * DUR)
t_all = np.arange(N) / SR

# Am - F - C - G, une mesure chacun (fréquences des fondamentales graves)
CHORDS = [(110.00, [220.00, 261.63, 329.63]),   # La mineur
          (87.31, [174.61, 220.00, 261.63]),    # Fa
          (130.81, [261.63, 329.63, 392.00]),   # Do
          (98.00, [196.00, 246.94, 293.66])]    # Sol


def chord_at(t):
    return CHORDS[int(t // (4 * BEAT)) % 4]


def env_decay(n, rate):
    return np.exp(-np.arange(n) / SR * rate)


def add(buf, start, sig):
    i = int(start * SR)
    if i >= len(buf):
        return
    sig = sig[: len(buf) - i]
    buf[i:i + len(sig)] += sig


def saw(freq, n, detune=0.0):
    ph = np.cumsum(np.full(n, freq * (1 + detune)) / SR)
    return 2 * (ph % 1) - 1


def lowpass(x, cutoff):
    # filtre passe-bas d'ordre 1 (suffisant pour adoucir les dents de scie)
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


rng = np.random.default_rng(42)
drums = np.zeros(N)
bass = np.zeros(N)
arp = np.zeros(N)
pad = np.zeros((N, 2))
fx = np.zeros(N)
duck = np.ones(N)  # compression déclenchée par le kick (effet « pompe »)

beat_on = lambda t: 4 <= t < 38 or 42 <= t < 42.5

# ---- batterie
kick_len = int(0.45 * SR)
k_t = np.arange(kick_len) / SR
kick = np.sin(2 * np.pi * np.cumsum(40 + 110 * np.exp(-k_t * 28)) / SR) * np.exp(-k_t * 7)
kick += 0.4 * np.sin(2 * np.pi * 55 * k_t) * np.exp(-k_t * 11)
clap_len = int(0.25 * SR)
clap = rng.standard_normal(clap_len) * env_decay(clap_len, 20)
clap = clap - lowpass(clap, 900)  # bruit filtré passe-haut
hat_len = int(0.06 * SR)
hat = rng.standard_normal(hat_len) * env_decay(hat_len, 70)
hat = hat - lowpass(hat, 6000)

for b in range(int(DUR / BEAT)):
    t = b * BEAT
    if beat_on(t):
        add(drums, t, kick * 0.95)
        d = int(t * SR)
        duck[d:d + int(0.32 * SR)] = np.minimum(duck[d:d + int(0.32 * SR)],
                                                0.35 + 0.65 * (np.arange(min(int(0.32 * SR), N - d)) / (0.32 * SR)))
        if b % 2 == 1:
            add(drums, t, clap * 0.45)
    step = BEAT / 4 if t >= 16 else BEAT / 2
    s = t
    while s < t + BEAT:
        if beat_on(s):
            accent = 1.0 if abs((s / BEAT) % 1 - 0.5) < 1e-6 else 0.6
            add(drums, s, hat * 0.18 * accent)
        s += step

# ---- basse : croches sur la fondamentale, octave sur les contretemps
note_len = int(BEAT / 2 * SR)
for i in range(int(DUR / (BEAT / 2))):
    t = i * BEAT / 2
    if not beat_on(t):
        continue
    root = chord_at(t)[0]
    f = root * (2 if i % 2 else 1)
    sig = (saw(f, note_len) + saw(f, note_len, 0.004)) * 0.5 * env_decay(note_len, 6)
    add(bass, t, sig * 0.5)
bass = lowpass(bass, 420)

# ---- arpège en doubles croches (accords montants)
an = int(BEAT / 4 * SR)
for i in range(int(DUR / (BEAT / 4))):
    t = i * BEAT / 4
    if t < 2 or t >= 45:
        continue
    notes = chord_at(t)[1]
    f = notes[i % 3] * (2 if (i // 3) % 2 else 1)
    pluck = np.sign(np.sin(2 * np.pi * f * np.arange(an) / SR)) * env_decay(an, 14)
    gain = 0.10 if 4 <= t < 38 else 0.07
    add(arp, t, pluck * gain)
arp = lowpass(arp, 2600)

# ---- nappe : accord tenu par mesure, légèrement désaccordé en stéréo
bar = 4 * BEAT
for k in range(int(DUR / bar) + 1):
    t = k * bar
    n = int(bar * SR)
    _, notes = chord_at(t)
    left = sum(saw(f, n, -0.003) for f in notes) / 3
    right = sum(saw(f, n, 0.003) for f in notes) / 3
    att = np.minimum(1, np.arange(n) / (0.25 * SR))
    add(pad[:, 0], t, left * att * 0.16)
    add(pad[:, 1], t, right * att * 0.16)
pad[:, 0] = lowpass(pad[:, 0], 1500)
pad[:, 1] = lowpass(pad[:, 1], 1500)

# ---- effets : montées de bruit et impacts
def riser(start, end, gain):
    n = int((end - start) * SR)
    noise = rng.standard_normal(n)
    ramp = np.linspace(0, 1, n) ** 2
    add(fx, start, (noise - lowpass(noise, 300 + 6000 * 0.5)) * ramp * gain)


def impact(at, gain):
    n = int(2.5 * SR)
    tt = np.arange(n) / SR
    boom = np.sin(2 * np.pi * np.cumsum(30 + 60 * np.exp(-tt * 6)) / SR) * np.exp(-tt * 1.6)
    noise = rng.standard_normal(n) * np.exp(-tt * 3)
    add(fx, at, (boom + 0.25 * (noise - lowpass(noise, 2000))) * gain)


riser(0.5, 4.0, 0.22)
impact(4.0, 0.9)
riser(36.0, 38.0, 0.12)
riser(39.0, 42.0, 0.2)
impact(42.0, 0.9)

# ---- mixage
mono = drums + bass * duck + arp * (0.6 + 0.4 * duck) + fx
mix = np.stack([mono + pad[:, 0] * duck, mono + pad[:, 1] * duck], axis=1)
fade = np.ones(N)
fade[-int(2.0 * SR):] = np.linspace(1, 0, int(2.0 * SR))  # extinction finale
fade[: int(0.3 * SR)] = np.linspace(0, 1, int(0.3 * SR))
mix *= fade[:, None]
mix = np.tanh(mix * 1.2)          # saturation douce
mix /= np.abs(mix).max() / 0.92   # normalisation

with wave.open("music.wav", "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((mix * 32767).astype("<i2").tobytes())
print("music.wav :", DUR, "s")
