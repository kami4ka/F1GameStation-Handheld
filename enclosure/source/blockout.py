# F1GameStation mechanical block-out for Autodesk Fusion.
#
# Run inside Fusion (via the Fusion360MCP add-in's execute_code, or as a Fusion
# script). Builds a parametric block-out in the active design: a layout sketch
# plus simple bodies for the LCD panel, its FPC, the battery, the board envelope,
# buttons, USB-C, TF slot, speaker and a case envelope. Every dimension is a
# user parameter (Modify > Change Parameters), in mm.
#
# Coordinates, front view: X right, Y up, origin at the case centre.
# Z: 0 = PCB front face; +Z towards the user (LCD, buttons), -Z towards the back.

import adsk.core, adsk.fusion

app = adsk.core.Application.get()
doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)   # new, unsaved document
design = adsk.fusion.Design.cast(app.activeProduct)
design.designType = adsk.fusion.DesignTypes.ParametricDesignType
root = design.rootComponent
P = design.userParameters

PARAMS = [
    # case envelope
    ('case_w', 186, 'Case width (PSP-style landscape)'), ('case_h', 80, 'Case height'),
    ('case_front_z', 6, 'Case front face Z'), ('case_back_z', -11, 'Case back face Z'),
    # board envelope
    ('pcb_w', 176, 'PCB width'), ('pcb_h', 70, 'PCB height (clears the triggers)'), ('pcb_t', 1.6, 'PCB thickness'),
    # LCD panel, FPC043CS4001 (common 4.3in 40-pin module; verify with calipers)
    ('panel_w', 106, 'LCD module outline width (measured)'), ('panel_h', 67, 'LCD module outline height (measured)'),
    ('panel_t', 3.0, 'LCD module thickness'), ('panel_gap', 1.0, 'Gap PCB front to LCD back'),
    ('aa_side', 3.5, 'LCD border left/right (measured)'), ('aa_fpc', 7.5, 'LCD border on the FPC edge (measured)'), ('aa_opp', 3, 'LCD border opposite the FPC (measured)'),
    ('lcd_cx', 0, 'LCD centre X'), ('lcd_top_margin', 6, 'Case top edge to LCD module top'),
    # LCD FPC: exits the top long edge, folds behind the panel (estimated from photo)
    ('fpc_w', 46, 'FPC width at the panel edge (measured)'), ('fpc_x', 8, 'FPC centre X offset from LCD centre (right edge 22 mm from panel right, measured)'),
    ('fpc_len', 35, 'FPC length from panel edge'), ('fpc_t', 0.3, 'FPC thickness'),
    # PCB slot behind the screen: the FPC folds behind the panel, passes through it and plugs into J2 on the PCB back
    ('slot_y', 2, 'PCB FPC slot centre Y (behind the screen)'), ('slot_h', 2.5, 'PCB FPC slot height'), ('slot_clear', 1, 'Slot clearance each side of the FPC'),
    ('fpc_back_len', 8, 'FPC length on the PCB back, slot to connector'), ('fpc_conn_w', 21, 'FPC width at the connector end'),
    ('fpc_conn_x', 20.5, 'FPC connector-end centre X from LCD centre (tail runs +10..+31, user)'),
    ('j2_w', 25.4, 'J2 AFC01-S40FCA-00 body width'), ('j2_d', 4.6, 'J2 body depth'), ('j2_t', 2, 'J2 body height'),
    # battery, 606090 LiPo pouch behind the PCB, lying along X
    ('bat_w', 90, 'Battery length (along X)'), ('bat_h', 60, 'Battery width (along Y)'), ('bat_t', 6, 'Battery thickness'),
    ('bat_cy', 2.5, 'Battery centre Y (clears USB-C on the back)'), ('bat_gap', 2.5, 'Gap PCB back to battery (clears J2 and the FPC)'),
    # buttons (button centres), PSP-style: D-pad left of the LCD, ABXY right
    ('pad_y', 12, 'D-pad / ABXY centre Y'), ('dpad_x', -73, 'D-pad centre X'), ('abxy_x', 73, 'ABXY centre X'),
    ('btn_pitch', 9, 'D-pad / ABXY button offset from centre'), ('face_d', 7, 'Face button cap diameter'),
    ('btn_h', 4.5, 'Button cap top above PCB'),
    ('ss_y', -18, 'Start/Select Y (below ABXY)'), ('ss_x', 73, 'Start/Select centre X'), ('ss_dx', 7.5, 'Start/Select X offset'), ('menu_x', 73, 'Menu X'), ('menu_y', -29, 'Menu Y'), ('small_d', 5, 'Small button cap diameter'),
    ('lr_x', 80, 'L/R shoulder X offset'),
    ('trig_len', 32, 'Trigger length along the top edge'), ('trig_wrap', 12, 'Trigger wrap down the side edge'),
    ('trig_depth', 5, 'Trigger depth into the case'), ('trig_out', 1, 'Trigger stand-out beyond the case outline'),
    ('trig_z0', -4, 'Trigger bottom Z'), ('trig_t', 9, 'Trigger height'), ('pwr_y', -12, 'Power button Y (right side edge, side-push)'),
    # connectors and speaker
    ('usb_x', 0, 'USB-C centre X (bottom edge, PCB back)'), ('tf_x', -38, 'TF slot centre X (bottom edge, PCB back; under the SoC SD pins, clear of the M2 hole)'),
    ('spk_x', -73, 'Speaker centre X (below D-pad)'), ('spk_y', -22, 'Speaker centre Y'), ('spk_s', 13, 'Speaker size'), ('spk_t', 4, 'Speaker height'),
]

for name, val, comment in PARAMS:
    ex = P.itemByName(name)
    if ex is None:
        P.add(name, adsk.core.ValueInput.createByString('%g mm' % val), 'mm', comment)

P.itemByName('fpc_len').expression = '(case_h / 2 - lcd_top_margin) - slot_y + 3 mm'

V = adsk.core.ValueInput.createByString
pt = adsk.core.Point3D.create

def new_comp(name):
    occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    occ.component.name = name
    return occ.component

def plane_at(comp, z_expr):
    pi = comp.constructionPlanes.createInput()
    pi.setByOffset(comp.xYConstructionPlane, V(z_expr))
    pl = comp.constructionPlanes.add(pi)
    return pl

def setpos(D, a, b, orient, expr):
    # sketch distance dimensions are magnitudes: skip zero offsets, use abs() otherwise
    if abs(ev(expr)) < 1e-9:
        return None
    try:
        dd = D.addDistanceDimension(a, b, orient, pt(0, 0, 0))
        dd.parameter.expression = 'abs(%s)' % expr
        return dd
    except RuntimeError:        # already fixed by other geometry (e.g. coincident with origin axes)
        return None

def dim_rect(sk, lines, cx, cy, w, h):
    """lines from addTwoPointRectangle; constrain to expressions (centre, size)"""
    d = sk.sketchDimensions
    o = sk.originPoint
    horiz = [l for l in lines if abs(l.startSketchPoint.geometry.y - l.endSketchPoint.geometry.y) < 1e-9]
    vert = [l for l in lines if l not in horiz]
    bl = min((l.startSketchPoint for l in lines), key=lambda p: (p.geometry.x + p.geometry.y))
    gc = sk.geometricConstraints
    for l in horiz:
        try:
            gc.addHorizontal(l)
        except RuntimeError:
            pass
    for l in vert:
        try:
            gc.addVertical(l)
        except RuntimeError:
            pass
    dw = d.addDistanceDimension(horiz[0].startSketchPoint, horiz[0].endSketchPoint,
                                adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation, pt(0, 0, 0))
    dw.parameter.expression = w
    dh = d.addDistanceDimension(vert[0].startSketchPoint, vert[0].endSketchPoint,
                                adsk.fusion.DimensionOrientations.VerticalDimensionOrientation, pt(0, 0, 0))
    dh.parameter.expression = h
    setpos(d, o, bl, adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation, '(%s) - (%s) / 2' % (cx, w))
    setpos(d, o, bl, adsk.fusion.DimensionOrientations.VerticalDimensionOrientation, '(%s) - (%s) / 2' % (cy, h))

def ev(expr):
    return design.unitsManager.evaluateExpression(expr, 'mm')    # cm internally

def rect(sk, cx, cy, w, h):
    x, y, ww, hh = ev(cx), ev(cy), ev(w), ev(h)
    lines = sk.sketchCurves.sketchLines.addTwoPointRectangle(pt(x - ww / 2, y - hh / 2, 0), pt(x + ww / 2, y + hh / 2, 0))
    lines = [lines.item(i) for i in range(lines.count)]
    dim_rect(sk, lines, cx, cy, w, h)
    return lines

def circle(sk, cx, cy, d):
    c = sk.sketchCurves.sketchCircles.addByCenterRadius(pt(ev(cx), ev(cy), 0), ev(d) / 2)
    D = sk.sketchDimensions; o = sk.originPoint
    try:
        D.addDiameterDimension(c, pt(ev(cx) + ev(d), ev(cy) + ev(d), 0)).parameter.expression = d
    except RuntimeError:
        pass
    setpos(D, o, c.centerSketchPoint, adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation, cx)
    setpos(D, o, c.centerSketchPoint, adsk.fusion.DimensionOrientations.VerticalDimensionOrientation, cy)
    return c

def body(comp, name, z0, t, shapes, opacity=1.0):
    """shapes: list of ('rect', cx, cy, w, h) / ('circle', cx, cy, d), extruded from z0 by t.
    Each shape gets its own sketch so its dimensions never interact with its neighbours."""
    plane = plane_at(comp, z0)
    made = []
    for k, s in enumerate(shapes):
        sk = comp.sketches.add(plane)
        nm = name if len(shapes) == 1 else '%s %d' % (name, k + 1)
        sk.name = nm
        (rect if s[0] == 'rect' else circle)(sk, *s[1:])
        prof = sk.profiles.item(0)
        if sk.profiles.count > 1:          # pick the outer profile
            prof = max((sk.profiles.item(i) for i in range(sk.profiles.count)), key=lambda p: p.areaProperties().area)
        ext = comp.features.extrudeFeatures.addSimple(prof, V(t), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        b = ext.bodies.item(0)
        b.name = nm
        b.opacity = opacity
        made.append(b)
    return made

LCD_CY = '(case_h / 2 - lcd_top_margin - panel_h / 2)'
LCD_TOP = '(case_h / 2 - lcd_top_margin)'
AA_W = '(panel_w - 2 * aa_side)'
AA_H = '(panel_h - aa_fpc - aa_opp)'
AA_CY = '(' + LCD_CY + ' + (aa_opp - aa_fpc) / 2)'
LCD_Z0 = 'panel_gap'

# ---------------------------------------------------------------- layout sketch
lay = root.sketches.add(root.xYConstructionPlane)
lay.name = 'Layout (front view)'
rect(lay, '0 mm', '0 mm', 'case_w', 'case_h')
rect(lay, 'lcd_cx', LCD_CY, 'panel_w', 'panel_h')
rect(lay, 'lcd_cx', AA_CY, AA_W, AA_H)
for (x, y, d) in [('dpad_x', 'pad_y + btn_pitch', 'face_d'), ('dpad_x', 'pad_y - btn_pitch', 'face_d'),
                  ('dpad_x - btn_pitch', 'pad_y', 'face_d'), ('dpad_x + btn_pitch', 'pad_y', 'face_d'),
                  ('abxy_x', 'pad_y + btn_pitch', 'face_d'), ('abxy_x', 'pad_y - btn_pitch', 'face_d'),
                  ('abxy_x - btn_pitch', 'pad_y', 'face_d'), ('abxy_x + btn_pitch', 'pad_y', 'face_d'),
                  ('ss_x - ss_dx', 'ss_y', 'small_d'), ('ss_x + ss_dx', 'ss_y', 'small_d'), ('menu_x', 'menu_y', 'small_d')]:
    circle(lay, x, y, d)
# speaker grille: 3 slots over the speaker
for k in (-1, 0, 1):
    rect(lay, 'spk_x', 'spk_y + %d * 3 mm' % k, 'spk_s - 3 mm', '1.2 mm')

# ---------------------------------------------------------------- bodies
c = new_comp('Board envelope')
body(c, 'PCB', '-pcb_t', 'pcb_t', [('rect', '0 mm', '0 mm', 'pcb_w', 'pcb_h')])

c = new_comp('LCD FPC043CS4001')
body(c, 'LCD module', LCD_Z0, 'panel_t', [('rect', 'lcd_cx', LCD_CY, 'panel_w', 'panel_h')])
body(c, 'LCD visible area', LCD_Z0 + ' + panel_t', '0.1 mm', [('rect', 'lcd_cx', AA_CY, AA_W, AA_H)])
# FPC: short wrap at the top edge, then flat behind the panel
body(c, 'FPC wrap', '0.2 mm', 'panel_gap + panel_t - 0.2 mm', [('rect', 'lcd_cx + fpc_x', LCD_TOP + ' + fpc_t', 'fpc_w', '2 * fpc_t')])
body(c, 'FPC tail', '0.2 mm', 'fpc_t', [('rect', 'lcd_cx + fpc_x', LCD_TOP + ' - (fpc_len - 3 mm) / 2', 'fpc_w', 'fpc_len - 3 mm')])

# PCB slot for the FPC, then the FPC path through it and the connector on the back
brd = [o.component for o in root.occurrences if o.component.name == 'Board envelope'][0]
ssk = brd.sketches.add(plane_at(brd, '-pcb_t'))
ssk.name = 'FPC slot'
rect(ssk, 'lcd_cx + fpc_x', 'slot_y', 'fpc_w + 2 * slot_clear', 'slot_h')
cut = brd.features.extrudeFeatures.createInput(ssk.profiles.item(0), adsk.fusion.FeatureOperations.CutFeatureOperation)
cut.setDistanceExtent(False, V('pcb_t'))
cut.participantBodies = [brd.bRepBodies.itemByName('PCB')]
brd.features.extrudeFeatures.add(cut).name = 'FPC slot cut'
fc = [o.component for o in root.occurrences if o.component.name.startswith('LCD')][0]
body(fc, 'FPC through slot', '-pcb_t - fpc_t', 'pcb_t + fpc_t + 0.2 mm', [('rect', 'lcd_cx + fpc_x', 'slot_y', 'fpc_w', 'fpc_t')])
body(fc, 'FPC on PCB back', '-pcb_t - fpc_t', 'fpc_t', [('rect', 'lcd_cx + fpc_conn_x', 'slot_y - fpc_back_len / 2', 'fpc_conn_w', 'fpc_back_len')])
c = new_comp('J2 LCD connector')
body(c, 'J2 AFC01-S40FCA-00', '-pcb_t - j2_t', 'j2_t', [('rect', 'lcd_cx + fpc_conn_x', 'slot_y - fpc_back_len - j2_d / 2', 'j2_w', 'j2_d')])

c = new_comp('Battery 606090')
body(c, 'Battery', '-pcb_t - bat_gap - bat_t', 'bat_t', [('rect', '0 mm', 'bat_cy', 'bat_w', 'bat_h')])

c = new_comp('Buttons')
face = [('circle', 'dpad_x', 'pad_y + btn_pitch', 'face_d'), ('circle', 'dpad_x', 'pad_y - btn_pitch', 'face_d'),
        ('circle', 'dpad_x - btn_pitch', 'pad_y', 'face_d'), ('circle', 'dpad_x + btn_pitch', 'pad_y', 'face_d'),
        ('circle', 'abxy_x', 'pad_y + btn_pitch', 'face_d'), ('circle', 'abxy_x', 'pad_y - btn_pitch', 'face_d'),
        ('circle', 'abxy_x - btn_pitch', 'pad_y', 'face_d'), ('circle', 'abxy_x + btn_pitch', 'pad_y', 'face_d')]
body(c, 'Face buttons', '0 mm', 'btn_h', face)
body(c, 'Start Select Menu', '0 mm', 'btn_h', [('circle', 'ss_x - ss_dx', 'ss_y', 'small_d'), ('circle', 'ss_x + ss_dx', 'ss_y', 'small_d'), ('circle', 'menu_x', 'menu_y', 'small_d')])
body(c, 'Power switch', '0 mm', '3.3 mm', [('rect', 'pcb_w / 2 - 1.7 mm', 'pwr_y', '3.4 mm', '4.5 mm')])
body(c, 'L R switches', '0 mm', '3.3 mm', [('rect', '-lr_x', 'pcb_h / 2 - 1.7 mm', '4.5 mm', '3.4 mm'), ('rect', 'lr_x', 'pcb_h / 2 - 1.7 mm', '4.5 mm', '3.4 mm')])

TRIG = []
for side in (-1, 1):
    sx = '' if side > 0 else '-'
    top = ('rect', '%s(case_w / 2 - trig_len / 2 + trig_out)' % sx, 'case_h / 2 - trig_depth / 2 + trig_out', 'trig_len', 'trig_depth')
    wrap = ('rect', '%s(case_w / 2 - trig_depth / 2 + trig_out)' % sx, 'case_h / 2 - trig_wrap / 2 + trig_out', 'trig_depth', 'trig_wrap')
    bs = body(c, ('R' if side > 0 else 'L') + ' trigger', 'trig_z0', 'trig_t', [top, wrap])
    tools = adsk.core.ObjectCollection.create(); tools.add(bs[1])
    ci = c.features.combineFeatures.createInput(bs[0], tools)
    ci.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
    c.features.combineFeatures.add(ci)
    bs[0].name = ('R' if side > 0 else 'L') + ' trigger'
    TRIG.append(bs[0])

c = new_comp('Connectors')
body(c, 'USB-C', '-pcb_t - 3.26 mm', '3.26 mm', [('rect', 'usb_x', '-pcb_h / 2 + 7.35 mm / 2 - 1 mm', '8.94 mm', '7.35 mm')])
body(c, 'TF slot', '-pcb_t - 1.85 mm', '1.85 mm', [('rect', 'tf_x', '-pcb_h / 2 + 15 mm / 2 - 1 mm', '14 mm', '15 mm')])
body(c, 'Battery connector', '-pcb_t - 4.3 mm', '4.3 mm', [('rect', 'bat_w / 2 + 8 mm', 'bat_cy', '6 mm', '8 mm')])

c = new_comp('Speaker')
body(c, 'Speaker KLJ-01304T', '0 mm', 'spk_t', [('rect', 'spk_x', 'spk_y', 'spk_s', 'spk_s')])

c = new_comp('Case envelope')
body(c, 'Case envelope', 'case_back_z', 'case_front_z - case_back_z', [('rect', '0 mm', '0 mm', 'case_w', 'case_h')], opacity=0.15)

'block-out built: %d user parameters, %d occurrences' % (P.count, root.occurrences.count)
