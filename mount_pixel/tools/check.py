"""Contrôles de collision du support Pixel Fold (repère bureau).

- pince / socle contre le clavier (CAO Keychron)
- volume balayé par le cadre en rotation (cylindre dans le plan du téléphone)
  contre clavier, pince, socle et bureau
- zone du port USB-C + interrupteurs du clavier (et la fiche du câble) laissée libre
Les paramètres sont relus dans le .scad.
"""
import re
import sys
import numpy as np
import trimesh

SCAD = open("pixel_fold_k10_mount.scad", encoding="utf-8").read()


def param(name):
    m = re.search(rf"^{name}\s*=\s*([^;]+);", SCAD, re.M)
    return eval(m.group(1).replace("[", "(").replace("]", ")"))


tilt = np.radians(param("tilt_deg"))
hub = np.array(param("hub"), float)
back_t, ph_t, t_gap, f_lip_t = param("back_t"), param("ph_t"), param("t_gap"), param("f_lip_t")
gap, f_wall, latch_h = param("gap"), param("f_wall"), param("latch_h")
ph_w, ph_h = param("ph_w"), param("ph_h")
ow = ph_w / 2 + gap + f_wall
hh = ph_h / 2 + gap
sweep_r = np.hypot(ow, hh + latch_h) + 3
front_w = ph_t + t_gap + f_lip_t
U = np.array([1, 0, 0.0]); V = np.array([0, np.cos(tilt), np.sin(tilt)]); N = np.array([0, -np.sin(tilt), np.cos(tilt)])


def in_sweep(p, margin=1.0):
    d = p - hub
    w = d @ N
    r = np.hypot(d @ U, d @ V)
    return (w > -back_t - margin) & (w < front_w + margin) & (r < sweep_r + margin)


def pts(mesh, n=60000):
    p, _ = trimesh.sample.sample_surface_even(mesh, n)
    return np.vstack([p, mesh.vertices])


kb = trimesh.load("ref/k10_left_full.stl")
clip = trimesh.load("out/clip.stl")
base = trimesh.load("out/base.stl")
frame = trimesh.load("out/frame.stl")
ok = True
print(f"rayon balayé {sweep_r:.1f} mm, cadre {2*ow:.1f} x {2*hh+2*f_wall:.1f} mm")

# 1) pince contre clavier : points de la surface du clavier à l'intérieur de la pince
kp = pts(kb, 200000)
near = kp[(kp[:, 0] < 45) & (kp[:, 1] > -90)]
for name, m in (("pince", clip), ("socle", base)):
    inside = m.contains(near)
    print(f"{name} ∩ clavier : {inside.sum()} points", "" if inside.sum() == 0 else np.round(near[inside][:5], 2))
    ok &= inside.sum() == 0

# 2) balayage
lowest = hub - V * sweep_r * 1.0
print(f"point le plus bas du cadre en rotation : z = {(hub - V*sweep_r - N*back_t)[2]:.1f} / {(hub - V*sweep_r + N*front_w)[2]:.1f} mm")
for name, m in (("clavier", kb), ("pince", clip), ("socle (hors tête)", base)):
    p = pts(m, 120000)
    if name.startswith("socle"):
        # la tête de colonne est derrière le disque : on exclut seulement ce qui est derrière w < -back_t
        pass
    hit = in_sweep(p, 1.2)
    if name.startswith("socle"):
        d = p - hub
        r = np.hypot(d @ U, d @ V)
        hit &= ~(r < param("disc_d") / 2 + 0.6)   # bossage frottant : contact voulu
    print(f"balayage ∩ {name} : {hit.sum()} points", "" if hit.sum() == 0 else np.round(p[hit][:4], 1))
    ok &= hit.sum() == 0
zmin = min((hub + V * np.cos(a) * sweep_r + U * np.sin(a) * sweep_r + N * w)[2]
           for a in np.linspace(0, 2 * np.pi, 720) for w in (-back_t, front_w))
print(f"balayage : z mini = {zmin:.1f} mm (bureau à 0)")
ok &= zmin > 3

# 3) zone des ports du clavier : panneau X 35..100, fiche + câble jusqu'à Y = +45, Z 0..22
for name, m in (("pince", clip), ("socle", base)):
    p = pts(m, 80000)
    sel = (p[:, 0] > 35) & (p[:, 0] < 100) & (p[:, 1] > -1) & (p[:, 1] < 45) & (p[:, 2] < 22)
    print(f"zone ports ∩ {name} : {sel.sum()} points")
    ok &= sel.sum() == 0

# 4) cadre : dimensions d'impression
ext = frame.bounds[1] - frame.bounds[0]
print("cadre (bureau) étendue", np.round(ext, 1))
for f in ("clip", "base", "frame"):
    m = trimesh.load(f"out/{f}.stl")
    print(f"{f:6s} volume {m.volume/1000:6.1f} cm3  étanche {m.is_watertight}")
print("OK" if ok else "PROBLEMES")
sys.exit(0 if ok else 1)
