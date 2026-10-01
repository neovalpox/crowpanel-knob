"""Fantôme du K10 Max, coin arrière GAUCHE, dans le repère bureau du support Pixel.

Repère bureau : X vers la droite (X=0 face gauche du clavier, clavier en X>0),
Y vers l'arrière (Y=0 face arrière, clavier en Y<0), Z vers le haut (Z=0 bureau).
Même calage que mount/tools/make_ghost.py (faces = point le plus saillant, patins inclus).
"""
import numpy as np
import trimesh

TYPING_DEG = 3.5
REAR_H = 29.8
m = trimesh.load("../mount/ref/k10_right_merged.stl")
v = m.vertices
P = np.column_stack([v[:, 0] + 161.36, -v[:, 2] - 70.5 - 0.44, v[:, 1] - 1.2 + 0.6])
a = np.radians(TYPING_DEG)
R = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])
m.vertices = P @ R.T + [0, 0, REAR_H]
m = m.slice_plane([140, 0, 0], [-1, 0, 0])
m = m.slice_plane([0, -90, 0], [0, 1, 0])
print("faces", len(m.faces), "bounds", np.round(m.bounds, 2))
m.export("ref/k10_left_full.stl")
import fast_simplification
vs, fs = fast_simplification.simplify(m.vertices.astype(np.float32), m.faces.astype(np.int32), target_reduction=0.85)
trimesh.Trimesh(vs, fs).export("ref/k10_left_ghost.stl")
print("ghost", len(fs))
