# F1GameStation 3D-printable PSP-style enclosure for Autodesk Fusion.
#
# Run inside Fusion (Fusion360MCP execute_code or as a script). Creates a new
# document, inserts the saved "F1GameStation block-out" as a referenced
# component (so fit is checked against the real block-out), and builds:
#   Front shell   - screen window, button holes, grille, LED windows, 4 bosses
#                   with M2 heat-set inserts (the PCB screws into these)
#   Back shell    - battery bay, USB-C / TF openings, 4 counterbored M2 screw bosses
#   Button caps, L/R triggers, power button plunger
# then saves it in the F1GameStation Fusion project and exports STLs.
#
# Printing: 0.4 mm nozzle, PLA/PETG. Walls are 2.0 mm (5 perimeters), the front
# face 1.6 mm (8 x 0.2 mm layers). Print the front shell face-down and the back
# shell back-down: every opening is a vertical through-cut, so neither needs
# supports except the USB-C / TF / power openings in the side walls, which
# bridge (< 11 mm). Clearances are 0.3 mm per side for moving parts.
# Heat-set inserts: M2 x 3 mm (OD ~3.2 mm) -> 3.2 mm hole, 4 mm deep.
# Triggers: print on the front (flat top) face, PETG preferred for the leaf spring. Assembly: front shell
# face-down, drop each trigger in so its tongue window goes over the stop rib and the spring tip lands on
# its pad, push a 1.75 mm filament pin (cut to 14.5 mm; the socket runs z -9.8..5.4) through the trigger into the front socket, close
# with the back shell. Rest: trigger held on the rib by the spring. Rev 1.1 triggers (trig_nub False) have
# no striker nub (the board-1 switches sit off their modelled spot: no PCB holes for their pegs), and a
# rounded lip that stands trig_proud outside the case outline as the finger surface.

import adsk.core, adsk.fusion, math, os

# where the STL/3MF exports go; set F1GS_PRINT_DIR before exec() to override
OUT = globals().get('F1GS_PRINT_DIR', os.path.expanduser('~/F1GameStation/enclosure/print'))
V = dict(globals().get('BLOCKOUT_VALUES', {}))      # mm values read from the block-out document

# ---------------------------------------------------------------- enclosure settings (mm)
E = dict(
    wall=2.0, face=1.6, back=1.6, corner_r=12.0, edge_r=2.0,   # corner_r 12 keeps the 176x70 PCB corners 1.7 mm clear
    case_back_z=-12.4,                  # deeper than the block-out's -11 so the 6 mm cell fits (-10.1 + 0.7 air)
    win_margin=0.5,                     # screen window = visible area + margin each side (bezel still covers the black border)
    btn_clear=0.3, cap_proud=1.5, cap_flange=1.2, cap_flange_t=0.8,
    boss_d=6.5, insert_d=3.2, insert_depth=4.2, screw_d=2.4, head_d=4.4, head_depth=2.2,
    led_d=1.6, grille_slot=(10.0, 1.2), grille_n=3, grille_pitch=3.0,
    usb_open=(13.2, 7.2),               # stadium sized for the cable's overmold (USB-C spec max 12.35 x 6.5) + 0.4 per side
    usb_chamfer=0.8,                    # 45 degree lead-in around the USB-C opening
    tf_open=(15.0, 2.8), pwr_open=(5.0, 4.4),
    trig_clear=0.3,
    # PSP-style shoulder triggers: a curved piece that follows the case corner, flush with the outline,
    # pivoting on a pin at its inner end. A nub on its inner face presses the side-push L/R switch on the
    # PCB top edge. The pin sits 6 mm from the switch so the corner, ~20 mm out, travels ~3.4x the switch
    # stroke (a lever), and the band itself stays 1 mm off the PCB outline so only the nub reaches in.
    trig_len=23.2,        # along the top edge, measured from the case side (pivot at |x| 72)
    trig_wrap=14.0,       # down the side edge, measured from the case top
    trig_depth=4.0,       # radial depth: inner face 1.0 mm outside the PCB outline
    trig_z0=-4.0, trig_z1=3.6,   # band height; the front part (z > 0.3) runs over the PCB top face
    trig_gap=0.4,         # clearance to the case at the trigger ends / band faces
    pin_hole=2.3, pin_socket=1.8, pin_len_note='1.75 mm filament or a 2 mm dowel',   # 2.0 printed too tight in PETG
    trig_nub=False,       # striker nub on/off (off: board 1 switches are not where the model has them)
    trig_proud=1.2, trig_round=1.0,      # finger lip outside the case outline, its outer edges rounded
    nub_w=3.0, nub_z0=0.6, nub_z1=3.2,   # striker in front of the actuator (SKRTLAE010 tip at y 34.92, z 0.08..3.44)
    trig_pre=0.15,        # nub to actuator gap at rest
    # motion limits. SKRTLAE010: 0.25 mm travel, 1.6 N. The trigger rests against a stop rib (outward limit),
    # a printed leaf spring holds it there, and the same rib ends the inward stroke when the switch reaches
    # full travel. All stop/spring features are Z-prisms: support-free with the trigger printed on its
    # front (z1) face and the front shell printed face-down. Clearances are sized from the rotation
    # (trig_disp below), and the full stroke is swept against the PCBA in Fusion.
    trig_switch_x=78.0,   # L/R switch position (|x|), scripts/build_board.py SW12/SW13
    trig_stroke=0.4,      # nub travel before the rib stops it: trig_pre + 0.25 switch travel
    stop_z0=0.3,          # tongue / spring bottom: above the PCB front face
    spring_t=0.6, spring_len=6.5, spring_preload=0.15,   # leaf spring: PETG recommended (PLA creeps under constant load)
)
HOLES = [(-57, 30), (57, 30), (-57, -30), (57, -30)]

app = adsk.core.Application.get()
pt = adsk.core.Point3D.create
def cm(v):
    return v / 10.0
VI = lambda v: adsk.core.ValueInput.createByReal(cm(v))

# ---------------------------------------------------------------- document + referenced block-out
proj = [app.data.dataProjects.item(i) for i in range(app.data.dataProjects.count) if app.data.dataProjects.item(i).name == 'F1GameStation'][0]
bo_file = None
for i in range(proj.rootFolder.dataFiles.count):
    f = proj.rootFolder.dataFiles.item(i)
    if f.name == 'F1GameStation block-out':
        bo_file = f
existing = [app.documents.item(i) for i in range(app.documents.count) if app.documents.item(i).name.startswith('F1GameStation enclosure')]
if existing:                                           # rebuild in place: keep the document, new version
    doc = existing[0]; doc.activate()
    design = adsk.fusion.Design.cast(app.activeProduct); root = design.rootComponent
    for o in list(root.occurrences):
        if o.component.name in ('Enclosure', 'Printed parts'):
            o.deleteMe()
    bo_occ = [o for o in root.occurrences if o.component.name.startswith('F1GameStation block-out')][0]
    for i in range(doc.documentReferences.count):     # pull the latest saved block-out
        r = doc.documentReferences.item(i)
        if not r.isLatestVersion if hasattr(r, 'isLatestVersion') else True:
            r.getLatestVersion()
    bo_occ = [o for o in root.occurrences if o.component.name.startswith('F1GameStation block-out')][0]
else:
    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    design = adsk.fusion.Design.cast(app.activeProduct)
    design.designType = adsk.fusion.DesignTypes.ParametricDesignType
    root = design.rootComponent
    bo_occ = root.occurrences.addByInsert(bo_file, adsk.core.Matrix3D.create(), True)
    bo_occ.isGroundToParent = True

def new_comp(name):
    o = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    o.component.name = name
    return o.component

def zplane(comp, z):
    pi = comp.constructionPlanes.createInput()
    pi.setByOffset(comp.xYConstructionPlane, VI(z))
    return comp.constructionPlanes.add(pi)

def rrect(sk, cx, cy, w, h, r):
    """rounded rectangle in block-out mm (sketch on an XY-parallel plane)"""
    r = min(r, w / 2 - 0.01, h / 2 - 0.01)
    L = sk.sketchCurves.sketchLines; A = sk.sketchCurves.sketchArcs
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    P = lambda x, y: pt(cm(x), cm(y), 0)
    if r <= 0.01:
        L.addTwoPointRectangle(P(x0, y0), P(x1, y1)); return
    L.addByTwoPoints(P(x0 + r, y0), P(x1 - r, y0)); L.addByTwoPoints(P(x1, y0 + r), P(x1, y1 - r))
    L.addByTwoPoints(P(x1 - r, y1), P(x0 + r, y1)); L.addByTwoPoints(P(x0, y1 - r), P(x0, y0 + r))
    A.addByCenterStartSweep(P(x1 - r, y0 + r), P(x1 - r, y0), math.pi / 2)
    A.addByCenterStartSweep(P(x1 - r, y1 - r), P(x1, y1 - r), math.pi / 2)
    A.addByCenterStartSweep(P(x0 + r, y1 - r), P(x0 + r, y1), math.pi / 2)
    A.addByCenterStartSweep(P(x0 + r, y0 + r), P(x0, y0 + r), math.pi / 2)

def circ(sk, cx, cy, d):
    sk.sketchCurves.sketchCircles.addByCenterRadius(pt(cm(cx), cm(cy), 0), cm(d) / 2)

def solid(comp, name, z0, t, draw):
    """extrude everything drawn by draw(sketch) from z0 by t into one new body per closed profile set"""
    sk = comp.sketches.add(zplane(comp, z0)); sk.name = name
    draw(sk)
    profs = adsk.core.ObjectCollection.create()
    for i in range(sk.profiles.count):
        profs.add(sk.profiles.item(i))
    ext = comp.features.extrudeFeatures.addSimple(profs, VI(t), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    bodies = [ext.bodies.item(i) for i in range(ext.bodies.count)]
    for k, b in enumerate(bodies):
        b.name = name if len(bodies) == 1 else '%s %d' % (name, k + 1)
    return bodies

def combine(comp, target, tools, op):
    col = adsk.core.ObjectCollection.create()
    for t in tools:
        col.add(t)
    ci = comp.features.combineFeatures.createInput(target, col)
    ci.operation = op
    ci.isKeepToolBodies = False
    comp.features.combineFeatures.add(ci)
    return target

CUT = adsk.fusion.FeatureOperations.CutFeatureOperation
JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation

# ---------------------------------------------------------------- derived geometry (block-out coords)
cw, ch = V['case_w'], V['case_h']
zf, zb = V['case_front_z'], E['case_back_z']
split_z = -V['pcb_t']                                   # shells meet at the PCB back face
lcd_cy = ch / 2 - V['lcd_top_margin'] - V['panel_h'] / 2
aa_w = V['panel_w'] - 2 * V['aa_side']; aa_h = V['panel_h'] - V['aa_fpc'] - V['aa_opp']
aa_cy = lcd_cy + (V['aa_opp'] - V['aa_fpc']) / 2
face_in = zf - E['face']
pad_y, dpx, abx, pitch = V['pad_y'], V['dpad_x'], V['abxy_x'], V['btn_pitch']
FACE_BTNS = [(dpx, pad_y + pitch), (dpx, pad_y - pitch), (dpx - pitch, pad_y), (dpx + pitch, pad_y),
             (abx, pad_y + pitch), (abx, pad_y - pitch), (abx - pitch, pad_y), (abx + pitch, pad_y)]
SMALL_BTNS = [(V['ss_x'] - V['ss_dx'], V['ss_y']), (V['ss_x'] + V['ss_dx'], V['ss_y']), (V['menu_x'], V['menu_y'])]
LEDS = [(-82, -32), (-76, -32), (-72, -32), (-68, -32), (-64, -32)]      # LED1, D2..D5 (scripts/build_board.py)

enc = new_comp('Enclosure')

# ---------------------------------------------------------------- outer skin and cavity
outer = solid(enc, 'Case', zb, zf - zb, lambda s: rrect(s, 0, 0, cw, ch, E['corner_r']))[0]
# round the front and back perimeter edges
edges = adsk.core.ObjectCollection.create()
for e in outer.edges:
    z0 = e.startVertex.geometry.z * 10; z1 = e.endVertex.geometry.z * 10
    if abs(z0 - z1) < 1e-6 and (abs(z0 - zf) < 1e-6 or abs(z0 - zb) < 1e-6):
        edges.add(e)
fi = enc.features.filletFeatures.createInput()
fi.addConstantRadiusEdgeSet(edges, VI(E['edge_r']), True)
enc.features.filletFeatures.add(fi)
cav = solid(enc, 'cavity', zb + E['back'], face_in - (zb + E['back']),
            lambda s: rrect(s, 0, 0, cw - 2 * E['wall'], ch - 2 * E['wall'], E['corner_r'] - E['wall']))[0]
combine(enc, outer, [cav], CUT)

# ---------------------------------------------------------------- front-face cuts
tools = []
tools += solid(enc, 'screen window', face_in - 0.5, E['face'] + 1,
               lambda s: rrect(s, 0, aa_cy, aa_w + 2 * E['win_margin'], aa_h + 2 * E['win_margin'], 1.0))
def btn_holes(s):
    for x, y in FACE_BTNS:
        circ(s, x, y, V['face_d'] + 2 * E['btn_clear'])
    for x, y in SMALL_BTNS:
        circ(s, x, y, V['small_d'] + 2 * E['btn_clear'])
    for x, y in LEDS:
        circ(s, x, y, E['led_d'])
    gw, gh = E['grille_slot']
    for k in range(E['grille_n']):
        rrect(s, V['spk_x'], V['spk_y'] + (k - (E['grille_n'] - 1) / 2) * E['grille_pitch'], gw, gh, gh / 2)
tools += solid(enc, 'face holes', face_in - 0.5, E['face'] + 1, btn_holes)
# side-wall openings: USB-C and TF on the bottom edge (back side of the PCB), power button on the right edge
usb_z = -2.78                                           # receptacle axis: GCT USB4105 shell z -4.91..-0.64 in the PCBA STEP (1.51 mm board)
tf_z = -V['pcb_t'] - 1.85 / 2
bottom_in = -ch / 2 + E['wall']
def wall_cut(name, base_plane, offset, axis_pt, half_u, half_v, thick):
    """cut a rectangular opening through a side wall: plane parallel to base_plane at 'offset'
    (verified against axis_pt so the sign of the plane normal does not matter), symmetric extrude."""
    for sign in (1, -1):
        pi = enc.constructionPlanes.createInput()
        pi.setByOffset(base_plane, VI(sign * offset))
        pl = enc.constructionPlanes.add(pi)
        o = pl.geometry.origin
        if abs((o.x + o.y + o.z) * 10 - offset) < 1e-3 or abs(offset) < 1e-6:
            break
        pl.deleteMe()
    sk = enc.sketches.add(pl); sk.name = name
    c = sk.modelToSketchSpace(pt(*[cm(v) for v in axis_pt]))
    u = sk.modelToSketchSpace(pt(*[cm(v) for v in half_u]))
    v = sk.modelToSketchSpace(pt(*[cm(v) for v in half_v]))
    du = max(abs(u.x - c.x), abs(v.x - c.x)); dv = max(abs(u.y - c.y), abs(v.y - c.y))
    sk.sketchCurves.sketchLines.addTwoPointRectangle(pt(c.x - du, c.y - dv, 0), pt(c.x + du, c.y + dv, 0))
    ei = enc.features.extrudeFeatures.createInput(sk.profiles.item(0), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    ei.setSymmetricExtent(VI(thick), True)
    b = enc.features.extrudeFeatures.add(ei).bodies.item(0); b.name = name
    return b
y_wall = -ch / 2 + E['wall'] / 2
uw, uh = E['usb_open']; tw_, th_ = E['tf_open']
def xz_plane(y):
    """construction plane parallel to XZ through model y (the offset sign of the XZ plane is checked)"""
    for sign in (1, -1):
        pi = enc.constructionPlanes.createInput()
        pi.setByOffset(enc.xZConstructionPlane, VI(sign * y))
        pl = enc.constructionPlanes.add(pi)
        if abs(pl.geometry.origin.y * 10 - y) < 1e-3 or abs(y) < 1e-6:
            return pl
        pl.deleteMe()
def stadium(name, y, cx, cz, w, h):
    """one closed stadium loop (w along x, h along z, round ends) on the XZ-parallel plane at y"""
    sk = enc.sketches.add(xz_plane(y)); sk.name = name
    c = sk.modelToSketchSpace(pt(cm(cx), cm(y), cm(cz)))
    along_x = abs(sk.modelToSketchSpace(pt(cm(cx + 1), cm(y), cm(cz))).x - c.x) > 0.05
    a, r = cm(w) / 2, cm(h) / 2
    if not along_x:
        raise RuntimeError('XZ sketch axes not as expected')
    L = a - r
    P = lambda u, v: pt(c.x + u, c.y + v, 0)
    sl, sa = sk.sketchCurves.sketchLines, sk.sketchCurves.sketchArcs
    sl.addByTwoPoints(P(-L, -r), P(L, -r)); sl.addByTwoPoints(P(L, r), P(-L, r))
    sa.addByCenterStartSweep(P(L, 0), P(L, -r), math.pi); sa.addByCenterStartSweep(P(-L, 0), P(-L, r), math.pi)
    return sk.profiles.item(0)
# USB-C: a stadium through the wall big enough for the plug's overmold to reach the receptacle face
# (y -35.14, 2.9 mm inside the wall), with a 45 degree lead-in on the outside
y_out = -ch / 2
usb_prof = stadium('USB-C opening', y_out - 1.0, V['usb_x'], usb_z, uw, uh)
ei = enc.features.extrudeFeatures.createInput(usb_prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
ei.setDistanceExtent(False, VI(E['wall'] + 2.0))
usb_tool = enc.features.extrudeFeatures.add(ei).bodies.item(0)
if usb_tool.boundingBox.maxPoint.y * 10 < y_out:           # extruded the wrong way: flip
    usb_tool.deleteMe()
    ei = enc.features.extrudeFeatures.createInput(usb_prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    ei.setDistanceExtent(False, VI(-(E['wall'] + 2.0)))
    usb_tool = enc.features.extrudeFeatures.add(ei).bodies.item(0)
usb_tool.name = 'USB-C opening'
ch_ = E['usb_chamfer']
li = enc.features.loftFeatures.createInput(adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
li.loftSections.add(stadium('USB-C lead-in out', y_out - 0.3, V['usb_x'], usb_z, uw + 2 * (ch_ + 0.3), uh + 2 * (ch_ + 0.3)))
li.loftSections.add(stadium('USB-C lead-in in', y_out + ch_, V['usb_x'], usb_z, uw, uh))
lead = enc.features.loftFeatures.add(li).bodies.item(0); lead.name = 'USB-C lead-in'
tools += [usb_tool, lead]
tools.append(wall_cut('TF opening', enc.xZConstructionPlane, y_wall, (V['tf_x'], y_wall, tf_z),
                      (V['tf_x'] + tw_ / 2, y_wall, tf_z), (V['tf_x'], y_wall, tf_z + th_ / 2), E['wall'] + 2))
x_wall = cw / 2 - E['wall'] / 2
pw_, ph_ = E['pwr_open']
tools.append(wall_cut('power opening', enc.yZConstructionPlane, x_wall, (x_wall, V['pwr_y'], 1.65),
                      (x_wall, V['pwr_y'] + pw_ / 2, 1.65), (x_wall, V['pwr_y'], 1.65 + ph_ / 2), E['wall'] + 2))
# ---------------------------------------------------------------- trigger kinematics (right side, x mirrored)
# The trigger turns about the pin; pressing turns the right one clockwise (seen from the front) by
# TRIG_TH, the angle that moves the nub trig_stroke towards the switch. trig_disp(x, y) is the full-stroke
# displacement of a trigger point; every clearance below is sized from it.
PIV_X = cw / 2 - E['trig_len'] + 2.2; PIV_Y = ch / 2 - E['trig_depth'] / 2
TRIG_TH = E['trig_stroke'] / (E['trig_switch_x'] - PIV_X)
def trig_disp(x, y):
    return TRIG_TH * (y - PIV_Y), -TRIG_TH * (x - PIV_X)
x_side_in = cw / 2 - E['wall']                        # side wall inner face
y_end = ch / 2 - E['trig_wrap']                       # trigger wrap end
_far = max(math.hypot(x - PIV_X, y - PIV_Y) for x, y in ((cw / 2, y_end), (cw / 2 - 3.5, ch / 2 - 3.5), (cw / 2 - E['trig_depth'], y_end)))
POCKET_IN = TRIG_TH * _far + 0.3                     # inward travel room behind the band
END_GAP = -trig_disp(cw / 2 - E['trig_depth'] / 2, y_end)[1] + 0.5   # wrap end moves down this much
NUB = (E['trig_switch_x'] - E['nub_w'] / 2, E['trig_switch_x'] + E['nub_w'] / 2, 34.92 + E['trig_pre'], ch / 2 - E['trig_depth'] + 0.05)
# stop rib in a window of the tongue: the rib moves +x relative to the window as the trigger turns, so the
# window's +x side gets that travel as extra room
TONGUE_X1 = x_side_in - 0.3
_rib_dx = -trig_disp(TONGUE_X1 - 2.0, y_end - 3.4)[0]
RIB = (TONGUE_X1 - 0.8 - 0.4 - _rib_dx - 1.2, TONGUE_X1 - 0.8 - 0.4 - _rib_dx, y_end - 4.0, y_end - 2.8)   # x0, x1, y0, y1
g_in = -trig_disp(RIB[1], RIB[3])[1] + 0.03          # inward travel at the rib's outer corner (first to touch)
WINDOW = (RIB[0] - 0.4, RIB[1] + 0.4 + _rib_dx, RIB[2], RIB[3] + g_in)         # rib sits on the window's lower edge at rest
TONGUE = (WINDOW[0] - 0.8, TONGUE_X1, y_end - 6.4, y_end + 0.2)                # trigger tongue running down inside the side wall
SPRING = (TONGUE[0] - E['spring_len'], TONGUE[0] + 0.4, TONGUE[2], TONGUE[2] + E['spring_t'])
BUMP = (SPRING[0], SPRING[0] + 1.0, TONGUE[2] - 0.4, TONGUE[2])
_bump_dx = -trig_disp(BUMP[0] + 0.5, BUMP[2])[0]    # the bump slides -x along its pad during the stroke
PAD = (BUMP[0] - 0.3 - _bump_dx, BUMP[1] + 0.2, BUMP[2] - 2.0, BUMP[2] + E['spring_preload'])
def box_xy(s, b, sx):
    x0, x1, y0, y1 = b
    rrect(s, sx * (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0, 0)

# trigger pockets: the trigger band plus clearance at the ends and faces, and its travel on the inner side
def corner_band(comp, name, depth, z0, z1, len_extra, wrap_extra, sx):
    """curved band following the case outline at one top corner (sx = -1 left, +1 right)"""
    r = E['corner_r']
    ring = solid(comp, name, z0, z1 - z0, lambda s: rrect(s, 0, 0, cw + 0.02, ch + 0.02, r))[0]
    inner = solid(comp, name + ' in', z0 - 1, z1 - z0 + 2, lambda s: rrect(s, 0, 0, cw - 2 * depth, ch - 2 * depth, max(r - depth, 0.5)))[0]
    combine(comp, ring, [inner], CUT)
    x_in = sx * (cw / 2 - E['trig_len'] - len_extra)
    y_lo = ch / 2 - E['trig_wrap'] - wrap_extra
    keep = solid(comp, name + ' keep', z0 - 1, z1 - z0 + 2,
                 lambda s: rrect(s, (x_in + sx * (cw / 2 + 5)) / 2, (y_lo + ch / 2 + 5) / 2, abs(sx * (cw / 2 + 5) - x_in), ch / 2 + 5 - y_lo, 0))[0]
    col = adsk.core.ObjectCollection.create(); col.add(keep)
    ci = comp.features.combineFeatures.createInput(ring, col)
    ci.operation = adsk.fusion.FeatureOperations.IntersectFeatureOperation
    comp.features.combineFeatures.add(ci)
    ring.name = name
    return ring
g = E['trig_gap']
for sx in (-1, 1):
    tools.append(corner_band(enc, 'trigger pocket', E['trig_depth'] + POCKET_IN, E['trig_z0'] - g, E['trig_z1'] + g, g, END_GAP, sx))
combine(enc, outer, tools, CUT)

# ---------------------------------------------------------------- bosses
bosses = solid(enc, 'front bosses', 0, face_in, lambda s: [circ(s, x, y, E['boss_d']) for x, y in HOLES])
bosses += solid(enc, 'back bosses', zb + E['back'] - 0.2, split_z - (zb + E['back'] - 0.2), lambda s: [circ(s, x, y, E['boss_d']) for x, y in HOLES])
for sx in (-1, 1):                                  # trigger pivot pin sockets, above and below the trigger band
    px = sx * (cw / 2 - E['trig_len'] + 2.2); py = ch / 2 - E['trig_depth'] / 2
    bosses += solid(enc, 'pivot socket front', E['trig_z1'] + E['trig_gap'], face_in - E['trig_z1'] - E['trig_gap'] + 0.3, lambda s, px=px, py=py: circ(s, px, py, 4.4))
    bosses += solid(enc, 'pivot socket back', zb + E['back'] - 0.2, E['trig_z0'] - E['trig_gap'] - (zb + E['back'] - 0.2), lambda s, px=px, py=py: circ(s, px, py, 4.4))
    # trigger stop rib (outward + inward limit) and the spring's bearing pad, hanging from the front face
    bosses += solid(enc, 'trigger stop rib', 0.6, face_in - 0.6 + 0.3, lambda s, sx=sx: box_xy(s, RIB, sx))
    bosses += solid(enc, 'trigger spring pad', 0.6, face_in - 0.6 + 0.3, lambda s, sx=sx: box_xy(s, PAD, sx))
combine(enc, outer, bosses, JOIN)
holes = solid(enc, 'insert holes', -0.01, E['insert_depth'], lambda s: [circ(s, x, y, E['insert_d']) for x, y in HOLES])
holes += solid(enc, 'screw holes', zb - 1, split_z - zb + 1.01, lambda s: [circ(s, x, y, E['screw_d']) for x, y in HOLES])
holes += solid(enc, 'screw heads', zb - 1, E['head_depth'] + 1, lambda s: [circ(s, x, y, E['head_d']) for x, y in HOLES])
for sx in (-1, 1):
    px = sx * (cw / 2 - E['trig_len'] + 2.2); py = ch / 2 - E['trig_depth'] / 2
    holes += solid(enc, 'pivot pin hole', zb + E['back'] + 1.0, (face_in + 1.0) - (zb + E['back'] + 1.0), lambda s, px=px, py=py: circ(s, px, py, E['pin_socket']))   # blind both ends: the pin is trapped
combine(enc, outer, holes, CUT)

# ---------------------------------------------------------------- split into front and back shells
si = enc.features.splitBodyFeatures.createInput(outer, zplane(enc, split_z), True)
enc.features.splitBodyFeatures.add(si)
shells = sorted([b for b in enc.bRepBodies], key=lambda b: b.boundingBox.maxPoint.z)
shells[0].name = 'Back shell'; shells[-1].name = 'Front shell'

# ---------------------------------------------------------------- printed parts
parts = new_comp('Printed parts')
sw_top = {'face': 0.8, 'small': 2.6}                  # cap rests on the actuator: SKRRAAE010 0.78 mm, SH-1808SN 2.58 mm (3D models)
def caps(kind, pts_, d):
    out = []
    for i, (x, y) in enumerate(pts_):
        z0 = sw_top[kind]
        fl_top = face_in - 0.1
        stem = solid(parts, 'cap stem', z0, fl_top - E['cap_flange_t'] - z0, lambda s: circ(s, x, y, d * 0.6))[0]
        fl = solid(parts, 'cap flange', fl_top - E['cap_flange_t'], E['cap_flange_t'], lambda s: circ(s, x, y, d + 2 * E['cap_flange']))[0]
        top = solid(parts, 'cap', fl_top, zf + E['cap_proud'] - fl_top, lambda s: circ(s, x, y, d))[0]
        combine(parts, top, [stem, fl], JOIN)
        out.append(top)
    return out
names = ['UP', 'DOWN', 'LEFT', 'RIGHT', 'X', 'B', 'Y', 'A']
for b, n in zip(caps('face', FACE_BTNS, V['face_d']), names):
    b.name = 'Cap ' + n
for b, n in zip(caps('small', SMALL_BTNS, V['small_d']), ['SELECT', 'START', 'MENU']):
    b.name = 'Cap ' + n
# triggers: the curved band, with a pivot hole at the inner end (pin along Z, held by sockets in both shells)
PIVOTS = []
for sx, n in ((-1, 'L'), (1, 'R')):
    t = corner_band(parts, n + ' trigger', E['trig_depth'], E['trig_z0'], E['trig_z1'], 0, 0, sx)
    t.name = n + ' trigger'
    px = sx * (cw / 2 - E['trig_len'] + 2.2)
    py = ch / 2 - E['trig_depth'] / 2
    PIVOTS.append((px, py))
    hole = solid(parts, n + ' pivot hole', E['trig_z0'] - 1, E['trig_z1'] - E['trig_z0'] + 2, lambda s, px=px, py=py: circ(s, px, py, E['pin_hole']))[0]
    # at the PCB's own height keep the band 1.5 mm off the outline, so the stroke never reaches the board edge
    keep = solid(parts, n + ' pcb keep-out', -V['pcb_t'] - 0.5, V['pcb_t'] + 0.5 + E['stop_z0'],
                 lambda s: rrect(s, 0, 0, V['pcb_w'] + 3, V['pcb_h'] + 3, 8.0))[0]
    combine(parts, t, [hole, keep], CUT)
    # striker nub: the only part that reaches in over the PCB edge, in front of the switch actuator
    if E['trig_nub']:
        nub = solid(parts, n + ' nub', E['nub_z0'], E['nub_z1'] - E['nub_z0'], lambda s, sx=sx: box_xy(s, NUB, sx))[0]
        combine(parts, t, [nub], JOIN)
    # finger lip: the band continued trig_proud outside the case outline, its outer edges rounded
    if E['trig_proud'] > 0:
        p = E['trig_proud']
        r = E['corner_r']
        lip = solid(parts, n + ' lip', E['trig_z0'], E['trig_z1'] - E['trig_z0'], lambda s: rrect(s, 0, 0, cw + 2 * p, ch + 2 * p, r + p))[0]
        lip_in = solid(parts, n + ' lip in', E['trig_z0'] - 1, E['trig_z1'] - E['trig_z0'] + 2, lambda s: rrect(s, 0, 0, cw - 0.02, ch - 0.02, r))[0]
        combine(parts, lip, [lip_in], CUT)
        x_in = sx * (cw / 2 - E['trig_len']); y_lo = ch / 2 - E['trig_wrap']
        keep = solid(parts, n + ' lip keep', E['trig_z0'] - 1, E['trig_z1'] - E['trig_z0'] + 2,
                     lambda s, x_in=x_in, y_lo=y_lo: rrect(s, (x_in + sx * (cw / 2 + 5)) / 2, (y_lo + ch / 2 + 5) / 2, abs(sx * (cw / 2 + 5) - x_in), ch / 2 + 5 - y_lo, 0))[0]
        combine(parts, lip, [keep], adsk.fusion.FeatureOperations.IntersectFeatureOperation)
        def out_d(x, y):                              # distance outside the case outline
            ax, ay = abs(x) - (cw / 2 - E['corner_r']), abs(y) - (ch / 2 - E['corner_r'])
            return math.hypot(max(ax, 0), max(ay, 0)) + min(max(ax, ay), 0) - E['corner_r']
        edges = adsk.core.ObjectCollection.create()
        for e in lip.edges:
            ok, p0, p1 = e.evaluator.getParameterExtents()
            ok, m = e.evaluator.getPointAtParameter((p0 + p1) / 2)
            if out_d(m.x * 10, m.y * 10) > 0.75 * p:
                edges.add(e)
        fi = parts.features.filletFeatures.createInput()
        fi.addConstantRadiusEdgeSet(edges, VI(E['trig_round']), True)
        parts.features.filletFeatures.add(fi)
        combine(parts, t, [lip], JOIN)
    # tongue down the inside of the side wall with a window around the stop rib, and a leaf spring
    # whose tip bears on the pad; all Z-prisms from the trigger's front face
    zt = E['trig_z1'] - E['stop_z0']
    tongue = solid(parts, n + ' tongue', E['stop_z0'], zt, lambda s, sx=sx: box_xy(s, TONGUE, sx))[0]
    spring = solid(parts, n + ' spring', E['stop_z0'], zt, lambda s, sx=sx: (box_xy(s, SPRING, sx), box_xy(s, BUMP, sx)))
    combine(parts, t, [tongue] + spring, JOIN)
    win = solid(parts, n + ' window', E['stop_z0'] - 1, zt + 2, lambda s, sx=sx: box_xy(s, WINDOW, sx))[0]
    combine(parts, t, [win], CUT)
# power plunger: stem through the wall (1.2 mm proud) plus an inside flange that stops 0.2 mm short of the
# switch actuator and is larger than the wall opening in both directions, so it cannot fall out
fx0, fx1 = V['pcb_w'] / 2 + 0.6, cw / 2 - E['wall'] - 0.2
sx0, sx1 = fx1 - 0.3, cw / 2 + 1.2                    # stem overlaps the flange, 1.2 mm proud of the wall
pw = solid(parts, 'Power button', 0.2, 2.9, lambda s: rrect(s, (sx0 + sx1) / 2, V['pwr_y'], sx1 - sx0, E['pwr_open'][0] - 2 * E['btn_clear'], 0.3))[0]
pf = solid(parts, 'power flange', -1.2, 5.4, lambda s: rrect(s, (fx0 + fx1) / 2, V['pwr_y'], fx1 - fx0, E['pwr_open'][0] + 2.4, 0.2))[0]
combine(parts, pw, [pf], JOIN)
pw.name = 'Power button'

design.computeAll()

# ---------------------------------------------------------------- interference with the block-out
col = adsk.core.ObjectCollection.create()
for c_ in (enc, parts):
    oc = [o for o in root.occurrences if o.component == c_][0]
    for b in c_.bRepBodies:
        col.add(b.createForAssemblyContext(oc))
IGNORE = ('PCB', 'Case envelope', 'LCD visible area', 'Face buttons', 'Start Select Menu', 'L trigger', 'R trigger', 'Power switch', 'Speaker', 'FPC')
for occ in bo_occ.childOccurrences:
    for b in occ.bRepBodies:
        if not b.name.startswith(IGNORE):
            col.add(b)
res = design.analyzeInterference(design.createInterferenceInput(col))
SPRING_PRELOAD_MM3 = 2 * (PAD[1] - PAD[0]) * E['spring_preload'] * (E['trig_z1'] - 0.6)   # intended overlap, bump vs pad
clashes = sorted(set((r.entityOne.name, r.entityTwo.name, round(r.interferenceBody.volume * 1000, 2)) for r in res
                     if not ({r.entityOne.name, r.entityTwo.name} <= {'Front shell', 'Back shell'})))

# ---------------------------------------------------------------- save + STL export
if existing:
    doc.save('Rebuilt by mechanical/enclosure.py')
else:
    doc.saveAs('F1GameStation enclosure', proj.rootFolder, 'PSP-style 3D-printable enclosure (PLA/PETG, 0.4 mm nozzle, M2 heat-set inserts). References the block-out.', '')
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.endswith('.stl'):
        os.remove(os.path.join(OUT, f))
em = design.exportManager
occ_of = {o.component.name: o for o in root.occurrences}
for cname in ('Enclosure', 'Printed parts'):
    for b in occ_of[cname].component.bRepBodies:     # STL export needs the occurrence (assembly-context) body
        o = em.createSTLExportOptions(b.createForAssemblyContext(occ_of[cname]), os.path.join(OUT, b.name.replace(' ', '_') + '.stl'))
        o.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
        em.execute(o)
vol = {b.name: round(b.volume * 1000, 1) for b in list(enc.bRepBodies) + list(parts.bRepBodies)}   # mm^3
{'clashes': clashes, 'bodies': vol, 'doc': doc.name}
