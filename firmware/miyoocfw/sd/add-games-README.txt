F1GameStation: adding games
===========================

Put game files (ROMs) in the folder of their system here, e.g.

    add-games/NES/Super Mario Bros.nes
    add-games/SNES/Super Mario Kart.sfc

Other systems work too: make a folder with the name of the system's folder in
roms/ on the console (GB, GBC, GBA, MD, ...).

For box art and proper game names, run this on a computer with internet
before you eject the card (it is in the F1GameStation repository):

    python3 firmware/launcher/tools/fetch-boxart.py /Volumes/BOOT/add-games

On the next start the console moves everything from here into roms/ and the
games appear in the launcher. This folder is emptied when that is done.

To remove games, put a file remove-games.txt next to this folder (in the
top of the BOOT volume) with one line per game, as <SYSTEM>/<file name>;
wildcards work, e.g.

    SNES/Super Mario Kart*

They are deleted from roms/ (with their covers) on the next start.
