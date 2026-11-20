#!/usr/bin/env python3
"""Build the web 3D models for the project site.

Combines the enclosure STLs (enclosure/print, Z-up, millimetres, assembly
coordinates) with a KiCad GLB export of the PCBA into glTF scenes:

  site/models/f1gs.glb   PCBA (one vertex-coloured mesh) + every enclosure part
                         as its own named node, in assembled position. The
                         site's viewer explodes it by moving the nodes along
                         the offsets in the explode.json (metres).

usage:
  kicad-cli pcb export glb --subst-models --include-silkscreen \
      --include-soldermask --include-pads -o /tmp/pcba.glb hardware/kicad/F1GameStation.kicad_pcb
  python3 site/tools/build_models.py /tmp/pcba.glb

Needs trimesh and numpy. The KiCad GLB is in metres, Y-up, with the board
front facing +Y and the board top at Y = 0, which is also where the
enclosure puts the PCB top (Z = 0).
"""
import os
import sys

import numpy as np
import trimesh

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PRINT = os.path.join(ROOT, 'enclosure', 'print')
OUT = os.path.join(ROOT, 'site', 'models')

SHELL = [40, 42, 46, 255]
CAP = [28, 29, 32, 255]
LABEL = [235, 235, 235, 255]
TRIGGER = [55, 58, 64, 255]

# STL Z-up mm -> glTF Y-up metres: (x, y, z) -> (x, z, -y) / 1000
TO_GLTF = np.array([[1, 0, 0, 0],
                    [0, 0, 1, 0],
                    [0, -1, 0, 0],
                    [0, 0, 0, 1]], float) @ np.diag([1e-3, 1e-3, 1e-3, 1])

CAPS = ['A', 'B', 'X', 'Y', 'UP', 'DOWN', 'LEFT', 'RIGHT', 'START', 'SELECT', 'MENU']


def stl(name, colour):
    m = trimesh.load(os.path.join(PRINT, name + '.stl'))
    m.visual = trimesh.visual.ColorVisuals(m, face_colors=colour)
    return m


def enclosure_parts():
    """(name, mesh, exploded Z offset in mm)"""
    parts = [('Front shell', stl('Front_shell', SHELL), 30),
             ('Back shell', stl('Back_shell', SHELL), -45),
             ('L trigger', stl('L_trigger', TRIGGER), 18),
             ('R trigger', stl('R_trigger', TRIGGER), 18),
             ('Power button', stl('Power_button', TRIGGER), 12)]
    for c in CAPS:
        body = os.path.join(PRINT, f'Cap_{c}_body.stl')
        label = os.path.join(PRINT, f'Cap_{c}_label.stl')
        if os.path.exists(body):
            parts.append((f'Cap {c}', stl(f'Cap_{c}_body', CAP), 55))
            if os.path.exists(label):
                parts.append((f'Cap {c} label', stl(f'Cap_{c}_label', LABEL), 55))
        else:
            parts.append((f'Cap {c}', stl(f'Cap_{c}', CAP), 55))
    return parts


def colour_of(mesh):
    mat = getattr(mesh.visual, 'material', None)
    c = getattr(mat, 'baseColorFactor', None)
    if c is None:
        c = getattr(mat, 'main_color', None)
    if c is None:
        return [120, 120, 120, 255]
    c = np.asarray(c, float)
    if c.max() <= 1.0:
        c = c * 255
    return c.astype(np.uint8).tolist()


def pcba(path):
    """KiCad GLB -> one vertex-coloured mesh, centred on the board in X/Z"""
    s = trimesh.load(path, force='scene')
    parts = []
    for m in s.dump():
        col = colour_of(m)
        m = trimesh.Trimesh(m.vertices, m.faces, process=False)
        m.visual = trimesh.visual.ColorVisuals(m, face_colors=col)
        parts.append(m)
    board = trimesh.util.concatenate(parts)
    lo, hi = board.bounds
    centre = (lo + hi) / 2
    board.apply_translation([-centre[0], 0, -centre[2]])
    return board


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    os.makedirs(OUT, exist_ok=True)
    scene = trimesh.Scene()
    scene.add_geometry(pcba(sys.argv[1]), node_name='PCBA', geom_name='PCBA')
    for name, mesh, dz in enclosure_parts():
        m = mesh.copy()
        m.apply_transform(TO_GLTF)
        scene.add_geometry(m, node_name=name, geom_name=name)
    out = os.path.join(OUT, 'f1gs.glb')
    scene.export(out)
    # explode offsets for the viewer, glTF Y is the stack axis
    import json
    offsets = {name: dz * 1e-3 for name, _, dz in enclosure_parts()}
    with open(os.path.join(OUT, 'explode.json'), 'w') as f:
        json.dump(offsets, f, indent=1)
    print(out, os.path.getsize(out) // 1024, 'KiB')


if __name__ == '__main__':
    main()
