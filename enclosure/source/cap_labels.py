# Two-colour labelled button caps for Bambu Studio (X1C + AMS).
#
# Reads the cap STLs exported by enclosure.py (enclosure/print/Cap_*.stl), sinks a letter 0.4 mm
# (2 x 0.2 mm layers) into each cap top, flush with the surface, and writes one Bambu Studio 3MF
# where every cap is an object with two parts: the cap (filament 1) and its letter (filament 2).
# Caps are flipped top-down on the plate so the letters print in the first two layers.
# D-pad caps stay blank.
#
# Run with a Python that has manifold3d, trimesh, fonttools, shapely, numpy:
#   python enclosure/source/cap_labels.py
# Output: enclosure/print/Caps_labelled_bambu.3mf, plus Cap_<n>_body.stl / Cap_<n>_label.stl.

import os, zipfile, uuid
import numpy as np
import trimesh
import manifold3d as mf
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from shapely.geometry import Polygon

HERE = os.path.dirname(os.path.abspath(__file__))
PRINT = os.path.join(HERE, '..', 'print')
FONT = '/System/Library/Fonts/Supplemental/Arial Black.ttf'
LABELS = {'A': 'A', 'B': 'B', 'X': 'X', 'Y': 'Y', 'START': 'S', 'SELECT': 'S', 'MENU': 'M'}
BLANK = ['UP', 'DOWN', 'LEFT', 'RIGHT']
DEPTH = 0.4            # 2 layers at 0.2 mm
EDGE = 0.9             # clear band between the letters and the cap rim
MAX_H = {7.0: 3.6, 5.0: 2.6}   # letter cap-height limit per cap diameter
PITCH = 12.0           # plate grid spacing
PLATE_C = (128.0, 128.0)       # X1C plate centre


class FlatPen(BasePen):
    """Glyph outline -> list of closed polylines (curves flattened)."""
    def __init__(self, glyphset, steps=8):
        super().__init__(glyphset)
        self.contours, self.cur, self.steps = [], [], steps
    def _moveTo(self, p):
        self.cur = [p]
    def _lineTo(self, p):
        self.cur.append(p)
    def _qCurveToOne(self, p1, p2):
        p0 = self.cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            self.cur.append(((1-t)**2*p0[0] + 2*(1-t)*t*p1[0] + t*t*p2[0], (1-t)**2*p0[1] + 2*(1-t)*t*p1[1] + t*t*p2[1]))
    def _curveToOne(self, p1, p2, p3):
        p0 = self.cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps; u = 1 - t
            self.cur.append((u**3*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t**3*p3[0], u**3*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t**3*p3[1]))
    def _closePath(self):
        if len(self.cur) > 2:
            self.contours.append(self.cur)
        self.cur = []
    _endPath = _closePath


def text_contours(text, font):
    gs, cmap, hmtx = font.getGlyphSet(), font.getBestCmap(), font['hmtx']
    out, x = [], 0.0
    for ch in text:
        g = cmap[ord(ch)]
        pen = FlatPen(gs)
        gs[g].draw(pen)
        out += [[(px + x, py) for px, py in c] for c in pen.contours]
        x += hmtx[g][0]
    return out


def fit(contours, cap_d):
    """Scale + centre the text so it fits the cap top with an EDGE margin."""
    pts = np.array([p for c in contours for p in c])
    lo, hi = pts.min(0), pts.max(0)
    ctr, half = (lo + hi) / 2, (hi - lo) / 2
    r = cap_d / 2 - EDGE
    s = min(r / np.hypot(*half), MAX_H[cap_d] / (hi[1] - lo[1]))
    return [[((x - ctr[0]) * s, (y - ctr[1]) * s) for x, y in c] for c in contours]


def to_manifold(m):
    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32), tri_verts=np.asarray(m.faces, np.uint32)))


def to_trimesh(m):
    mesh = m.to_mesh()
    return trimesh.Trimesh(mesh.vert_properties[:, :3], mesh.tri_verts, process=True)


def min_stroke_ok(contours, w=0.4):
    """True if every stroke is at least w wide (an inward buffer of w/2 keeps all the pieces)."""
    poly = Polygon()
    for c in contours:
        poly = poly.symmetric_difference(Polygon(c).buffer(0))
    eroded = poly.buffer(-w / 2)
    n = lambda g: len(getattr(g, 'geoms', [g])) if not g.is_empty else 0
    return n(eroded) >= n(poly), poly.area, eroded.area


def build():
    font = TTFont(FONT)
    parts = []                                   # (name, body trimesh, label trimesh or None)
    for name in list(LABELS) + BLANK:
        cap = trimesh.load(os.path.join(PRINT, f'Cap_{name}.stl'))
        assert cap.is_watertight, name
        lo, hi = cap.bounds
        cx, cy, ztop = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, hi[2]
        d = round(hi[0] - lo[0] - 2 * 1.2, 1)    # top diameter (bbox includes the 1.2 mm flange)
        capm = to_manifold(cap)
        label = None
        if name in LABELS:
            cs = fit(text_contours(LABELS[name], font), d)
            ok, a0, a1 = min_stroke_ok(cs)
            print(f'{name:7s} {LABELS[name]:2s} cap {d} mm  strokes >= 0.4 mm: {ok}')
            sec = mf.CrossSection([np.array(c) for c in cs], mf.FillRule.EvenOdd)
            prism = sec.extrude(DEPTH + 0.5).translate((cx, cy, ztop - DEPTH))
            body = capm - prism
            lab = capm ^ prism
            label = to_trimesh(lab)
            capm = body
        parts.append((name, to_trimesh(capm), label, (cx, cy)))
    return parts


def place(parts):
    """Flip each cap top-down (180 deg about X) and lay them out in a grid on the plate."""
    out = []
    cols = 4
    for i, (name, body, label, (cx, cy)) in enumerate(parts):
        gx = PLATE_C[0] + (i % cols - (cols - 1) / 2) * PITCH
        gy = PLATE_C[1] - (i // cols - 1) * PITCH
        meshes = [m for m in (body, label) if m is not None]
        zmax = max(m.bounds[1][2] for m in meshes)
        T = np.eye(4)
        T[:3, :3] = [[1, 0, 0], [0, -1, 0], [0, 0, -1]]
        T[:3, 3] = [gx - cx, gy + cy, zmax]
        moved = []
        for m in meshes:
            m = m.copy(); m.apply_transform(T); moved.append(m)
        out.append((name, moved[0], moved[1] if label is not None else None))
    return out


def mesh_xml(oid, m):
    v = '\n'.join(f'     <vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in m.vertices)
    t = '\n'.join(f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in m.faces)
    return (f'  <object id="{oid}" p:UUID="{uuid.uuid4()}" type="model">\n   <mesh>\n    <vertices>\n{v}\n    </vertices>\n'
            f'    <triangles>\n{t}\n    </triangles>\n   </mesh>\n  </object>\n')


def write_3mf(placed, path):
    objs, comps, items, cfg = [], [], [], []
    oid = 1
    for name, body, label in placed:
        ids = []
        for m in (body, label):
            if m is None:
                continue
            objs.append(mesh_xml(oid, m)); ids.append(oid); oid += 1
        parent = oid; oid += 1
        cl = ''.join(f'    <component p:path="/3D/Objects/object_1.model" objectid="{i}" p:UUID="{uuid.uuid4()}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n' for i in ids)
        comps.append(f'  <object id="{parent}" p:UUID="{uuid.uuid4()}" type="model">\n   <components>\n{cl}   </components>\n  </object>\n')
        items.append(f'  <item objectid="{parent}" p:UUID="{uuid.uuid4()}" transform="1 0 0 0 1 0 0 0 1 0 0 0" printable="1"/>\n')
        pc = f'    <part id="{ids[0]}" subtype="normal_part">\n      <metadata key="name" value="Cap {name}"/>\n      <metadata key="extruder" value="1"/>\n    </part>\n'
        if len(ids) > 1:
            pc += f'    <part id="{ids[1]}" subtype="normal_part">\n      <metadata key="name" value="Label {LABELS[name]}"/>\n      <metadata key="extruder" value="2"/>\n    </part>\n'
        cfg.append(f'  <object id="{parent}">\n    <metadata key="name" value="Cap {name}"/>\n    <metadata key="extruder" value="1"/>\n{pc}  </object>\n')
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
             'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p">\n'
             ' <metadata name="Application">BambuStudio-02.07.01.57</metadata>\n'
             ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
             ' <metadata name="Title">F1GameStation labelled caps</metadata>\n'
             ' <resources>\n' + ''.join(comps) + ' </resources>\n <build>\n' + ''.join(items) + ' </build>\n</model>\n')
    objects = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
               'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p">\n'
               ' <resources>\n' + ''.join(objs) + ' </resources>\n <build/>\n</model>\n')
    plate = '  <plate>\n    <metadata key="plater_id" value="1"/>\n' + ''.join(
        f'    <model_instance>\n      <metadata key="object_id" value="{c.split(chr(34))[1]}"/>\n      <metadata key="instance_id" value="0"/>\n    </model_instance>\n' for c in cfg) + '  </plate>\n'
    config = '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n' + ''.join(cfg) + plate + '</config>\n'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
                   ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
                   ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n</Types>\n')
        z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
                   ' <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n</Relationships>\n')
        z.writestr('3D/3dmodel.model', model)
        z.writestr('3D/Objects/object_1.model', objects)
        z.writestr('3D/_rels/3dmodel.model.rels', '<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
                   ' <Relationship Target="/3D/Objects/object_1.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n</Relationships>\n')
        z.writestr('Metadata/model_settings.config', config)


if __name__ == '__main__':
    parts = build()
    for name, body, label, _ in parts:
        body.export(os.path.join(PRINT, f'Cap_{name}_body.stl'))
        if label is not None:
            label.export(os.path.join(PRINT, f'Cap_{name}_label.stl'))
    out = os.path.join(PRINT, 'Caps_labelled_bambu.3mf')
    write_3mf(place(parts), out)
    print('wrote', out)
