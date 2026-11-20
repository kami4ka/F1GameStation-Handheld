# Enclosure

PSP-style case, 186 × 80 mm, printed in PETG. Designed in Autodesk Fusion.

## print/

Ready-to-print parts, as STL and 3MF, in assembly orientation unless named `_print`.

| File | Qty | Notes |
| --- | --- | --- |
| `Front_shell` | 1 | screen window, button holes, speaker grille, M2 insert bosses |
| `Back_shell` | 1 | battery bay, USB-C / microSD openings, counterbored screw holes |
| `L_trigger_print`, `R_trigger_print` | 1 each | laid flat for printing; `L_trigger`, `R_trigger` are in place |
| `Power_button_print` | 1 | laid flat; `Power_button` is in place |
| `Cap_*` | 1 each | 11 button caps |
| `Cap_*_body`, `Cap_*_label` | | caps split into body and sunk letters for two-colour printing |
| `Caps_labelled_bambu.3mf` | | all 11 caps on one plate, labels on filament 2 (Bambu Studio / OrcaSlicer) |

Print settings and orientation are in the [build guide](../docs/BUILD.md#4-print-the-case).

## source/

| File | What |
| --- | --- |
| `F1GameStation_enclosure.f3d` | Fusion archive of the enclosure with full timeline |
| `F1GameStation_blockout.f3d` | the parametric block-out it references: board, panel, battery, buttons |
| `*.step` | the same, for other CAD tools |
| `blockout.py` | builds the block-out document in Fusion from a table of parameters |
| `enclosure.py` | builds the enclosure from the block-out and exports the STLs |
| `cap_labels.py` | sinks labels into the cap STLs and writes the two-colour 3MF (needs `trimesh`, `manifold3d`, `shapely`, `fonttools`) |

`blockout.py` and `enclosure.py` run inside Fusion (Scripts and Add-Ins, or any way of executing
Python in Fusion). `enclosure.py` expects the block-out's user parameters in a `BLOCKOUT_VALUES`
dict (millimetres) and writes STLs to `F1GS_PRINT_DIR` (default `~/F1GameStation/enclosure/print`).
To change a dimension, edit it in the block-out's parameters and rebuild the enclosure; the
moving-part clearances (triggers, caps) are derived from the values at the top of `enclosure.py`.

## License

[CERN-OHL-S-2.0](../hardware/LICENSE).
