# Builds a fake /mnt/gmenu2x + /roms tree with placeholder box art for host tests.
import os, random, sys
sys.path.insert(0, os.path.dirname(__file__))
from PIL import Image, ImageDraw, ImageFont
root = sys.argv[1]
F = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
links = {"NES": ".nes,.zip", "SNES": ".smc,.sfc,.zip", "GB": ".gb,.zip", "GBA": ".gba,.zip", "MD": ".md,.bin,.gen,.zip"}
games = {
 "SNES": ["Star Courier (USA)", "Robo Rally X (Europe)", "Turbo Kart 3 (USA) [!]", "Mega Puzzle (Japan)", "Zap Zone (USA)"],
 "NES": ["Pixel Knight (USA)", "Castle Rush (Europe)", "Legend of Ember, The (USA)", "Bomb Squad (USA)"],
 "GB": ["Ghost Lantern (World)", "Tiny Tanks (USA)", "Cave Diver (Japan)"],
 "GBA": ["Moss Temple (USA)", "Sky Fortress (Europe)", "Frost Runner (USA)"],
 "MD": ["Neon Drift (USA)", "Deep Blue (Europe)", "Alien Harbor (USA)", "Quartz Quest (Japan)"],
}
noart = {"Bomb Squad (USA)", "Zap Zone (USA)", "Quartz Quest (Japan)"}
ext = {"NES": ".nes", "SNES": ".sfc", "GB": ".gb", "GBA": ".gba", "MD": ".md"}
R = os.path.abspath(root)
def stub(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write("#!/bin/sh\necho \"$0 $*\"\n"); os.chmod(path, 0o755)
d = f"{root}/gmenu2x/sections/emulators"; os.makedirs(d, exist_ok=True)
for s, flt in links.items():
    if s in ("GB", "GBA", "SNES"):
        continue  # these are started through RetroArch core links below
    stub(f"{R}/emus/{s.lower()}/{s.lower()}")
    open(f"{d}/{s.lower()}", "w").write(f"title={s}\nexec={R}/emus/{s.lower()}/{s.lower()}\nselectordir={R}/roms/{s}\nselectorfilter={flt}\n")
# a link whose program is missing, like the card's emulators/gambatte: must be ignored
open(f"{d}/gambatte", "w").write(f"title=Gambatte\nexec={R}/emus/gambatte/gambatte\nselectordir={R}/roms/GB\n")
# RetroArch core links as retroarch-setup writes them (selectordir is the whole card)
stub(f"{R}/emus/retroarch/retroarch")
d = f"{root}/gmenu2x/sections/cores"; os.makedirs(d, exist_ok=True)
for core, flt in (("gambatte", ".gb,.gbc,.dmg,.zip"), ("gpsp", ".gba,.bin,.zip"), ("fceumm", ".nes,.fds,.zip")):
    open(f"{d}/{core}.{core}.ra", "w").write(f"title={core}\nexec={R}/emus/retroarch/retroarch\nparams=-vL {core} --appendconfig={R}/emus/retroarch/retroarch_menu.cfg\nselectordir={R}\nselectorfilter={flt}\n")
# MiyooCFW's own SNES links: <group>.<core>.ra, a per-core script, no params, no filter
stub(f"{R}/emus/retroarch/snes9x2005.sh")
open(f"{R}/gmenu2x/sections/cores/snes9x4d.snes9x2005.ra", "w").write(f"title=snes9x2005\ndescription=snes9x2005 libretro core\nexec={R}/emus/retroarch/snes9x2005.sh\nselectordir={R}\n")
d = f"{root}/gmenu2x/sections/applications"; os.makedirs(d, exist_ok=True)
open(f"{d}/commander", "w").write("title=Commander\nexec=/usr/bin/dingux-commander\n")
for s, lst in games.items():
    rd = f"{root}/roms/{s}"; os.makedirs(f"{rd}/.images", exist_ok=True)
    for g in lst:
        open(f"{rd}/{g}{ext[s]}", "wb").write(b"\0" * 16)
        if g in noart: continue
        r = random.Random(g)
        w, h = {"GB": (300, 300), "SNES": (256, 352) if "Europe" not in g else (360, 256)}.get(s, (256, 360))
        c1 = tuple(r.randint(10, 160) for _ in range(3)); c2 = tuple(r.randint(120, 255) for _ in range(3))
        im = Image.new("RGB", (w, h)); dr = ImageDraw.Draw(im)
        for y in range(h):
            t = y / h; dr.line([0, y, w, y], fill=tuple(int(c1[i] * (1 - t) + c2[i] * t * 0.5) for i in range(3)))
        for _ in range(6):
            x = r.randint(0, w); y = r.randint(h // 4, h); z = r.randint(w // 8, w // 2)
            dr.ellipse([x - z, y - z, x + z, y + z], fill=tuple(min(255, int(c * 0.8 + 40)) for c in c1))
        dr.polygon([(w * .2, h), (w * .5, h * .45), (w * .8, h)], fill=c2)
        name = g.split(" (")[0].upper()
        sz = 40
        while ImageFont.truetype(F, sz).getlength(name) > w - 16: sz -= 1
        dr.text((w // 2, int(h * .2)), name, font=ImageFont.truetype(F, sz), fill=c2, anchor="mm", stroke_width=3, stroke_fill=(0, 0, 0))
        im.save(f"{rd}/.images/{g}.png")
