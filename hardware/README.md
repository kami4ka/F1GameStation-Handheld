# Hardware

KiCad 10 project for the F1GameStation main board, Rev 1.

| Path | What |
| --- | --- |
| `kicad/F1GameStation.kicad_pro` | project; open this in KiCad |
| `kicad/*.kicad_sch` | schematic: top sheet plus `soc`, `power`, `storage`, `display`, `audio`, `buttons` |
| `kicad/F1GameStation.kicad_pcb` | 4-layer board, 176 × 70 mm |
| `kicad/libraries/` | project symbols, footprints and 3D models (most come from the LCSC/EasyEDA library) |
| `production/F1GameStation.zip` | Gerbers and drill files for JLCPCB |
| `production/bom.csv` | BOM grouped by part, with LCSC numbers |
| `production/positions.csv` | pick-and-place (both sides) |
| `production/netlist.ipc` | IPC-D-356 netlist for the electrical test |
| `production/F1GameStation-schematic.pdf` | schematic as PDF |
| `production/F1GameStation-ibom.html` | interactive BOM, open in a browser |
| `3d/F1GameStation_PCBA.step` | assembled board for mechanical CAD |

The board can also be browsed without KiCad on the
[project site](https://kami4ka.github.io/F1GameStation-Handheld/#hardware).

## Design notes

- **Stackup:** L1 signal, L2 GND, L3 power planes (3V3, 2V5, 1V2), L4 signal. Ground is
  carried by the L2 plane, outer pours and stitching vias, not by traces.
- **Sides:** buttons, LEDs and the speaker are on the front; every other part is on the back.
  Parts under the battery stay below 2.4 mm.
- **USB:** the D+/D− pair is coupled 0.16/0.1 mm with a 0.2 mm pour gap, about 90 Ω on JLC04161H-7628.
- **No vias in SMD pads**, except the thermal vias under exposed pads.
- **Power:** IP5306 charges the 1S cell from USB-C and boosts it to 5 V. An EA3059C makes 3V3, 2V5 and
  1V2; an XC6206 makes 3V0. The backlight driver is an MP3202 (PT4103 footprint and pinout).
- **Battery gauge:** +BATT through a 200k/100k divider to LRADC0 (KEYADC, SoC pin 79).
- **LCD:** 40-pin RGB565 panel on J2 (AFC24-S40FIA-00, contacts on both sides). Its pin numbering is
  reversed in the footprint because the panel's pin 1 lands on connector contact 40.
- **Debug:** UART0 on the TX/RX/GND pads on the back (2.54 mm row), FEL button SW2, Reset SW1.

## Rev 1 issues

- PA1–PA3 (MENU, L, R) need external pull-ups; firmware works around it for now.
- No pin-1 markers on the silkscreen.
- No locating holes for the L/R trigger switch pegs.

## License

[CERN-OHL-S-2.0](LICENSE).
