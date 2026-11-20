#!/usr/bin/env python3
"""Fetch box art for the F1GameStation coverflow launcher.

Run on a computer with internet, with the console's SD card (or a copy of its
ROM folders) mounted:

    python3 fetch-boxart.py /Volumes/BOOT/add-games  # games waiting on the card
    python3 fetch-boxart.py /Volumes/BOOT/add-games --system SNES --force

For every ROM in <roms>/<SYSTEM>/ it finds the game's official (No-Intro)
name, downloads that game's cover from the libretro-thumbnails collection and
saves it, already shrunk to the launcher's size, as
<roms>/<SYSTEM>/.images/<rom file name>.png. The official name of each game
it recognises goes to <roms>/<SYSTEM>/.images/names.txt, so the launcher
shows "Dr. Mario" for a file called "drmario_usa.nes". That folder is also the one the
MiyooCFW scraper and gmenu2x use, so existing art is picked up too.

How a ROM is matched, best first:
  1. its file name already is a No-Intro name ("Tetris (World) (Rev 1).gb");
  2. its CRC32 (inside .zip files too) is looked up in the No-Intro database,
     so renamed files still match;
  3. a fuzzy match of the cleaned-up name against the covers that exist,
     preferring USA, then World, then Europe, then Japan.

Needs Python 3.8+. Pillow (pip3 install pillow) is used for resizing if it is
installed; on a Mac the built-in `sips` tool is used otherwise.
"""
import argparse
import difflib
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
import zlib

THUMBS = "https://thumbnails.libretro.com"
DATS = "https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/no-intro"
COVER_W, COVER_H = 102, 136  # the launcher's centre cover box (coverflow.c)

# card folder name -> libretro system name
SYSTEMS = {
    "NES": "Nintendo - Nintendo Entertainment System",
    "FC": "Nintendo - Nintendo Entertainment System",
    "FDS": "Nintendo - Family Computer Disk System",
    "SNES": "Nintendo - Super Nintendo Entertainment System",
    "SFC": "Nintendo - Super Nintendo Entertainment System",
    "GB": "Nintendo - Game Boy",
    "GBC": "Nintendo - Game Boy Color",
    "GBA": "Nintendo - Game Boy Advance",
    "VB": "Nintendo - Virtual Boy",
    "POKEMINI": "Nintendo - Pokemon Mini",
    "MD": "Sega - Mega Drive - Genesis",
    "SMD": "Sega - Mega Drive - Genesis",
    "GENESIS": "Sega - Mega Drive - Genesis",
    "32X": "Sega - 32X",
    "SEGACD": "Sega - Mega-CD - Sega CD",
    "SMS": "Sega - Master System - Mark III",
    "GG": "Sega - Game Gear",
    "PCE": "NEC - PC Engine - TurboGrafx 16",
    "NGP": "SNK - Neo Geo Pocket",
    "NGPC": "SNK - Neo Geo Pocket Color",
    "WS": "Bandai - WonderSwan",
    "WSC": "Bandai - WonderSwan Color",
    "LYNX": "Atari - Lynx",
    "A2600": "Atari - 2600",
    "ATARI2600": "Atari - 2600",
    "A7800": "Atari - 7800",
    "COLECO": "Coleco - ColecoVision",
    "MSX": "Microsoft - MSX",
    "PS": "Sony - PlayStation",
    "PSX": "Sony - PlayStation",
    "ARCADE": "FBNeo - Arcade Games",
    "FBA": "FBNeo - Arcade Games",
    "MAME": "MAME",
}
SKIP_EXT = {".png", ".jpg", ".txt", ".xml", ".db", ".srm", ".sav", ".state", ".cfg",
            ".ini", ".dat", ".md5", ".log", ".bak", ".rtc"}
REGION_PREF = ["USA", "World", "Europe", "Japan"]

UA = {"User-Agent": "f1gs-fetch-boxart/1.0"}


def get(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def cache_path(cache, name):
    os.makedirs(cache, exist_ok=True)
    return os.path.join(cache, re.sub(r"[^A-Za-z0-9._-]+", "_", name))


def thumb_index(system, kind, cache):
    """Names (without .png) of the covers libretro has for a system."""
    p = cache_path(cache, f"index-{system}-{kind}.txt")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read().splitlines()
    url = f"{THUMBS}/{urllib.parse.quote(system)}/{kind}/"
    page = get(url, timeout=120).decode("utf-8", "replace")
    names = sorted({html.unescape(urllib.parse.unquote(m))[:-4]
                    for m in re.findall(r'href="([^"?/]+\.png)"', page)})
    open(p, "w", encoding="utf-8").write("\n".join(names))
    return names


def nointro_crcs(system, cache):
    """crc32 (lower-case hex) -> No-Intro game name."""
    p = cache_path(cache, f"dat-{system}.dat")
    if not os.path.exists(p):
        try:
            data = get(f"{DATS}/{urllib.parse.quote(system)}.dat", timeout=120)
        except Exception as e:  # not every system has a No-Intro dat
            print(f"  (no CRC database for {system}: {e})")
            data = b""
        open(p, "wb").write(data)
    text = open(p, encoding="utf-8", errors="replace").read()
    crcs = {}
    for game in re.finditer(r'game \(\s*name "((?:[^"\\]|\\.)*)"(.*?)\n\)', text, re.S):
        for crc in re.findall(r"\bcrc ([0-9A-Fa-f]{8})", game.group(2)):
            crcs.setdefault(crc.lower(), game.group(1))
    return crcs


def rom_crcs(path):
    """CRC32s worth trying: whole file, and without a copier/iNES header."""
    out = []
    if path.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(path) as z:
                for info in z.infolist():
                    if not info.is_dir():
                        out.append(f"{info.CRC:08x}")
        except zipfile.BadZipFile:
            pass
        return out
    if os.path.getsize(path) > 64 * 1024 * 1024:
        return out
    data = open(path, "rb").read()
    out.append(f"{zlib.crc32(data) & 0xffffffff:08x}")
    if data[:4] == b"NES\x1a":
        out.append(f"{zlib.crc32(data[16:]) & 0xffffffff:08x}")
    if len(data) % 1024 == 512:
        out.append(f"{zlib.crc32(data[512:]) & 0xffffffff:08x}")
    return out


def libretro_file(name):
    """libretro-thumbnails replaces these characters with _ in file names."""
    return re.sub(r'[&*/:`<>?\\|"]', "_", name)


def clean(name):
    n = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", name).lower()
    n = re.sub(r"^(.*), the\b", r"the \1", n.strip())
    n = re.sub(r"\bthe\b|[^a-z0-9]+", " ", n)
    return " ".join(n.split())


def region_rank(name):
    for i, r in enumerate(REGION_PREF):
        if re.search(r"\(([^)]*\b)?" + r + r"\b", name):
            return i
    return len(REGION_PREF)


def best_fuzzy(rom_name, index, by_clean):
    key = clean(rom_name)
    if not key:
        return None
    cands = by_clean.get(key)
    if not cands:
        nums = re.findall(r"\d+", key)
        # a sequel number has to match: "Kirby 2" is not "Kirby"
        close = [c for c in difflib.get_close_matches(key, list(by_clean), n=5, cutoff=0.86)
                 if re.findall(r"\d+", c) == nums]
        if not close:
            return None
        cands = by_clean[close[0]]
    return sorted(cands, key=lambda n: (region_rank(n), "Rev" in n, "Beta" in n or "Proto" in n, n))[0]


def resize(src_png, dst_png):
    try:
        from PIL import Image
        im = Image.open(src_png).convert("RGB")
        k = min(COVER_W / im.width, COVER_H / im.height, 1.0)
        im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
        im.save(dst_png, optimize=True)
        return True
    except ImportError:
        pass
    if shutil.which("sips"):
        out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", src_png],
                             capture_output=True, text=True).stdout
        w = int(re.search(r"pixelWidth: (\d+)", out).group(1))
        h = int(re.search(r"pixelHeight: (\d+)", out).group(1))
        k = min(COVER_W / w, COVER_H / h, 1.0)
        subprocess.run(["sips", "-s", "format", "png", "-z", str(max(1, round(h * k))),
                        str(max(1, round(w * k))), src_png, "--out", dst_png],
                       capture_output=True, check=True)
        return True
    shutil.copy(src_png, dst_png)  # the launcher shrinks it, just slower
    return False


NAMES = "names.txt"  # in .images: "<rom file>\t<official name>", read by the launcher


def read_names(outdir):
    names = {}
    try:
        for line in open(os.path.join(outdir, NAMES), encoding="utf-8"):
            if "\t" in line:
                rom, name = line.rstrip("\n").split("\t", 1)
                names[rom] = name
    except FileNotFoundError:
        pass
    return names


def write_names(outdir, names):
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, NAMES), "w", encoding="utf-8", newline="\n") as f:
        for rom in sorted(names):
            f.write(f"{rom}\t{names[rom]}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roms", help="folder that holds the system folders (NES, SNES, GBA, ...)")
    ap.add_argument("--system", action="append", help="only this folder (repeatable)")
    ap.add_argument("--kind", default="Named_Boxarts",
                    choices=["Named_Boxarts", "Named_Titles", "Named_Snaps"],
                    help="box art (default), title screens or in-game screenshots")
    ap.add_argument("--force", action="store_true", help="replace art that is already there")
    ap.add_argument("--dry-run", action="store_true", help="only print what would be fetched")
    ap.add_argument("--cache", default=os.path.join(tempfile.gettempdir(), "f1gs-boxart-cache"))
    a = ap.parse_args()

    total = found = missing = 0
    for folder in sorted(os.listdir(a.roms)):
        if a.system and folder.upper() not in {s.upper() for s in a.system}:
            continue
        sysdir = os.path.join(a.roms, folder)
        system = SYSTEMS.get(folder.upper())
        if not os.path.isdir(sysdir) or folder.startswith("."):
            continue
        if not system:
            print(f"{folder}: unknown system folder, skipped (add it to SYSTEMS)")
            continue
        roms = sorted(f for f in os.listdir(sysdir)
                      if not f.startswith(".") and os.path.isfile(os.path.join(sysdir, f))
                      and os.path.splitext(f)[1].lower() not in SKIP_EXT)
        if not roms:
            continue
        print(f"{folder}: {len(roms)} ROMs ({system})")
        try:
            index = thumb_index(system, a.kind, a.cache)
        except Exception as e:
            print(f"  could not list covers: {e}")
            total += len(roms)
            missing += len(roms)
            continue
        have = set(index)
        by_clean = {}
        for n in index:
            by_clean.setdefault(clean(n), []).append(n)
        crcs = None
        outdir = os.path.join(sysdir, ".images")
        names = read_names(outdir)
        for rom in roms:
            total += 1
            base = os.path.splitext(rom)[0]
            dst = os.path.join(outdir, base + ".png")
            have_art = os.path.exists(dst) and not a.force
            if have_art and rom in names:
                found += 1
                continue
            match, how, title = None, "", None
            if libretro_file(base) in have:
                match, how, title = libretro_file(base), "name", base
            if not match:
                if crcs is None:
                    crcs = nointro_crcs(system, a.cache)
                for c in rom_crcs(os.path.join(sysdir, rom)):
                    n = crcs.get(c)
                    if not n:
                        continue
                    title = title or n
                    if libretro_file(n) in have:
                        match, how = libretro_file(n), "crc"
                        break
                    if not match:
                        f = best_fuzzy(n, index, by_clean)
                        if f:
                            match, how = f, "crc+name"
            if not match:
                f = best_fuzzy(base, index, by_clean)
                if f:
                    match, how = f, "fuzzy"
            if title or match:
                names[rom] = title or match
            if have_art:
                found += 1
                continue
            if not match:
                missing += 1
                print(f"  -  {rom}: no cover found" + (f" (it is {title})" if title else ""))
                continue
            print(f"  +  {rom}  <-  {match}  [{how}]")
            if a.dry_run:
                found += 1
                continue
            url = f"{THUMBS}/{urllib.parse.quote(system)}/{a.kind}/{urllib.parse.quote(match)}.png"
            try:
                data = get(url)
            except Exception as e:
                missing += 1
                print(f"     download failed: {e}")
                continue
            os.makedirs(outdir, exist_ok=True)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as t:
                t.write(data)
            try:
                resize(t.name, dst)
                found += 1
            finally:
                os.unlink(t.name)
        if not a.dry_run and names:
            write_names(outdir, names)
    print(f"\n{found} of {total} ROMs have a cover, {missing} without.")


if __name__ == "__main__":
    sys.exit(main())
