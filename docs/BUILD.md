# Building an F1GameStation

> [!WARNING]
> Rev 1 is a prototype. The LCD, audio, battery gauge, backlight and USB high speed have not been
> tested yet on this revision. Read the [known issues](../README.md#known-issues) first.

You will need a hot-air station and a fine-tip iron (the SoC is a 0.4 mm QFN-88), a USB-C cable,
a microSD card (4 GB or more), and a 3D printer for the case.

1. [Order the board](#1-order-the-board)
2. [Assemble the board](#2-assemble-the-board)
3. [Flash the microSD card](#3-flash-the-microsd-card)
4. [Print the case](#4-print-the-case)
5. [Final assembly](#5-final-assembly)
6. [First boot](#6-first-boot)

## 1. Order the board

Everything for JLCPCB is in [`hardware/production`](../hardware/production):

| File | Upload as |
| --- | --- |
| `F1GameStation.zip` | Gerber files |
| `bom.csv` | BOM (grouped by part, LCSC numbers in the last column) |
| `positions.csv` | Pick-and-place (CPL) |
| `netlist.ipc` | IPC-D-356 netlist, optional for the electrical test |

PCB settings:

- 4 layers, 176 × 70 mm, 1.6 mm, stackup **JLC04161H-7628** with impedance control (the USB pair is
  routed for ~90 Ω)
- 1 oz outer copper, any solder mask colour
- PCB assembly on **both sides**: buttons, LEDs and speaker sit on the front, everything else on the back

Parts that JLCPCB may not have in stock, so check the order page before paying:

| Ref | Part | Notes |
| --- | --- | --- |
| F1C1S | Allwinner F1C200s (C2879851) | Often out of stock at JLC. Leave it out and solder it yourself (see below) |
| U1 | EA3059C triple buck (C570858) | Same: consign it or solder it by hand |
| U3 | W25Q128 SPI flash | Optional. The handheld boots from the microSD card; skip it to save a part |

The rest of the BOM was in stock at LCSC and JLC when the board was ordered (September 2026).

Not on the BOM, buy separately:

| Part | Notes |
| --- | --- |
| LCD | 4.3" 480×272 RGB panel, 40-pin 0.5 mm FPC, FPC043CS4001 pinout (106 × 67 mm module) |
| Battery | 1S Li-ion **606090** (6 × 60 × 90 mm), with a protection board, and a JST PH 2.0 two-pin pigtail. **Check polarity: J1 pin 1 is +BATT.** |
| Screws | 4 × M2 × 12 mm, cap or pan head |
| Inserts | 4 × M2 × 3 mm heat-set inserts (OD ~3.2 mm) |
| Trigger pins | 2 × 14.5 mm pieces of 1.75 mm filament |
| Tape | double-sided tape for the LCD |

## 2. Assemble the board

The [interactive BOM](../hardware/production/F1GameStation-ibom.html) (open it in a browser, or
[online](https://kami4ka.github.io/F1GameStation-Handheld/ibom.html)) shows where every part goes.

1. **SoC (if you left it out).** Preheat the board from below; the exposed pad is the SoC's only
   digital ground and sits on an internal ground plane, so hot air alone from the top will not reflow it.
   Keep 30 mm around the SoC free of front-side parts while you do this. The F1C200s pin 1 must match
   the iBOM, **the silkscreen has no pin-1 mark on Rev 1**.
2. **EA3059C (if you left it out).** Same care with its exposed pad.
3. **Check the rails** before anything else is connected: plug in USB-C and measure 5 V, 3V3, 3V0,
   2V5 and 1V2 at the regulator outputs (find them in the iBOM).
4. **Check FEL.** Hold the FEL button, press Reset, and run `sunxi-fel ver` on the computer.
   It should report `soc=00001663`. If it doesn't, the SoC joint is the first suspect.
5. **LCD.** Fold the FPC through the slot behind the screen and into J2 on the back, contacts up.
6. **Battery.** Plug the cell into J1 last, after checking the polarity.

The L/R trigger switches (SW12, SW13) have pegs but the board has no holes for them: trim the pegs
and hold the switch flat while soldering.

## 3. Flash the microSD card

**Prebuilt image.** Download `f1gamestation-sd-*.img.xz` from the
[Releases page](https://github.com/kami4ka/F1GameStation-Handheld/releases) and write it with
[balenaEtcher](https://etcher.balena.io) or Raspberry Pi Imager (both read `.xz` directly), or:

```sh
xz -dc f1gamestation-sd-rev1.img.xz | sudo dd of=/dev/rdiskN bs=4m   # macOS, check N with `diskutil list`
```

The image is MiyooCFW 2.0.0 beta 2 (musl) with the F1GameStation kernel, device tree, boot script,
480×272 menu and cover-flow launcher. It contains no games.

**Build it yourself.** See [firmware/README.md](../firmware/README.md). You need Docker and about
10 GB of disk.

**Adding games.** After the card is written, the FAT partition called `BOOT` shows up on any computer.
Copy ROMs into `BOOT/add-games/<SYSTEM>/` (`NES`, `SNES`, `GB`, `GBC`, `GBA`, `MD`, ...). On the next
start the console moves them into its games partition. For box art and proper names, run
[`fetch-boxart.py`](../firmware/launcher/tools/fetch-boxart.py) on that folder first.
Only use games you own or that are free to share.

## 4. Print the case

All parts are in [`enclosure/print`](../enclosure/print), as STL and as 3MF. PETG is recommended
for everything (the triggers need it for their printed leaf springs). 0.4 mm nozzle, 0.2 mm layers.

| Part | Qty | Orientation |
| --- | --- | --- |
| `Front_shell` | 1 | face down |
| `Back_shell` | 1 | back down |
| `L_trigger_print`, `R_trigger_print` | 1 each | as exported (flat top face down) |
| `Power_button_print` | 1 | as exported |
| `Cap_A`, `B`, `X`, `Y`, `UP`, `DOWN`, `LEFT`, `RIGHT` | 1 each | top face down |
| `Cap_START`, `SELECT`, `MENU` | 1 each | top face down |

No supports are needed except where the USB-C, microSD and power openings bridge the side walls
(under 11 mm). Walls are 2 mm (5 perimeters), the front face 1.6 mm (8 layers).

**Labelled caps.** `Caps_labelled_bambu.3mf` is a ready plate for a two-colour printer: black caps
with white letters sunk 0.4 mm (A/B/X/Y, ST/SL/M; the D-pad is blank). It opens in Bambu Studio and
OrcaSlicer with both filaments assigned. In OrcaSlicer, start a new project, add the second filament,
then *File → Import* the 3MF. `Cap_*_body.stl` and `Cap_*_label.stl` are the separate halves if you
want to set it up yourself.

**Editing the case.** `enclosure/source/F1GameStation_enclosure.f3d` opens in Fusion with the full
history; `F1GameStation_blockout.f3d` holds the parameters that drive it (board size, panel position,
battery, button layout). The STEP files are for other CAD tools. `blockout.py` and `enclosure.py`
rebuild both documents from scratch inside Fusion, see [enclosure/README.md](../enclosure/README.md).

## 5. Final assembly

1. Press the four M2 heat-set inserts into the front-shell bosses with a soldering iron at about
   220 °C, keeping them square.
2. Stick the LCD into the front-shell window with thin double-sided tape, FPC towards the top edge.
3. Lay the front shell face down and drop in the button caps, then the power button plunger.
4. **Triggers.** Drop each trigger in so its tongue window goes over the stop rib and the spring tip
   lands on its pad. Push a 14.5 mm piece of 1.75 mm filament through the trigger into the socket.
5. Lower the board onto the bosses, buttons down, feeding the LCD FPC through the slot into J2.
6. Put the battery in the back shell's bay, plug it into J1, and close the back shell.
7. Drive the four M2 × 12 screws from the back into the inserts. Snug is enough.

## 6. First boot

Insert the card and press the power button. The first boot shows MiyooCFW's setup screens:

1. **License**: the default is NO with a 30-second timeout that powers off. Press **RIGHT**, then **START**.
2. Let the partition resize finish; the console restarts.
3. The cover-flow launcher starts. **START** opens the quick menu (brightness, volume, screen mode,
   the classic gmenu2x menu, power off). **MENU + SELECT** quits a running game.

If nothing shows on screen, connect a 3.3 V USB-UART to the TX/RX/GND pads on the back
(115200 8N1) and watch the boot log.
