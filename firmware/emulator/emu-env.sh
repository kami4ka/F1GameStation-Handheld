# Shared paths for the emulator scripts (sourced). Override any of them in
# the environment.
F1GS_EMU_DIR=${F1GS_EMU_DIR:-$HOME/Projects/Hardware/miyoocfw/qemu}
# build.sh / make-sd.sh output (the Docker work volume on the Mac)
F1GS_DEPLOY=${F1GS_DEPLOY:-/Volumes/f1gs-src/deploy}
F1GS_SRC_IMG=${F1GS_SRC_IMG:-$HOME/Projects/Hardware/miyoocfw/f1gs-src.sparseimage}
