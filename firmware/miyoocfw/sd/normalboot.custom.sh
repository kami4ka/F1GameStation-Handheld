# expected to be run from this directory
# LOGS variable is set, but it should usually be /dev/null
# CONSOLE_VARIANT is also set
sh ./uart-getty.sh
# F1GameStation: this MiyooCFW release does not load the sound driver itself;
# miyoo_snd=4 keeps the NS4150B amp (PA0) on
modprobe miyoo miyoo_snd=4 >> "${LOGS}" 2>&1
modprobe -a snd_mixer_oss snd_pcm_oss >> "${LOGS}" 2>&1
# F1GameStation: gmenu2x built for the 480x272 panel (firmware/miyoocfw/gmenu2x)
# replaces the release's 320x240 menu, which is kept as gmenu2x.320x240
G="${HOME}/gmenu2x"
if [ -f gmenu2x-f1gs ] && [ -d "$G" ] && ! cmp -s gmenu2x-f1gs "$G/gmenu2x"; then
	[ -f "$G/gmenu2x.320x240" ] || cp "$G/gmenu2x" "$G/gmenu2x.320x240"
	cp gmenu2x-f1gs "$G/gmenu2x" && chmod 755 "$G/gmenu2x" && sync
fi
# F1GameStation: coverflow launcher (firmware/launcher). A new tarball is
# unpacked to /mnt/coverflow; autoexec.sh (run by /etc/main instead of gmenu2x)
# and a gmenu2x link are added once, so deleting /mnt/autoexec.sh brings
# gmenu2x back for good. BusyBox tar here has no -z, hence gzip.
if [ -f coverflow.tar.gz ] && ! cmp -s coverflow.tar.gz "${HOME}/coverflow/.installed.tar.gz"; then
	first=false
	[ -d "${HOME}/coverflow" ] || first=true
	gzip -dc coverflow.tar.gz | tar -xf - -C "${HOME}" &&
		cp coverflow.tar.gz "${HOME}/coverflow/.installed.tar.gz"
	if $first && [ -f "${HOME}/coverflow/autoexec.sh" ]; then
		cp "${HOME}/coverflow/autoexec.sh" "${HOME}/autoexec.sh"
		cp "${HOME}/coverflow/coverflow.gmenu2x-link" "${HOME}/gmenu2x/sections/applications/coverflow"
	fi
	sync
fi
# F1GameStation: remove the demo ROMs the MiyooCFW release ships (once).
# Only files with the stock name and size go, so a real game of the same
# name stays. Their art and saves in .images go with them.
if [ ! -f "${HOME}/.f1gs-demo-roms-removed" ]; then
	for entry in GB/THEBOUNCINGBALL.GB:65536 GB/punk.gb:524288 GB/dangan.gb:262144 \
		GBC/ucity.gbc:131072 GBC/vectroid.gbc:32768 GBA/gba-frame-test.gba:1392 \
		NES/Alter_Ego.nes:40976 NES/color_test.nes:40976 \
		NES/from_below_2020_09_16_v_1_0_0.nes:40976; do
		rom=${entry%:*}
		size=${entry##*:}
		for root in "${HOME}/roms" /roms; do
			f="${root}/${rom}"
			if [ -f "$f" ] && [ "$(wc -c < "$f")" -eq "$size" ]; then
				rm -f "$f" "${f%/*}/.images/$(basename "${f%.*}").png"
			fi
		done
	done
	touch "${HOME}/.f1gs-demo-roms-removed"
	sync
fi
# F1GameStation: games inbox. Games copied to add-games/<SYSTEM>/ on the
# BOOT partition (FAT32, so any computer can write it) are moved to
# roms/<SYSTEM>/, with the covers in .images/ and names.txt merged, as
# written by firmware/launcher/tools/fetch-boxart.py. Files macOS leaves
# behind (._*, .DS_Store) are skipped and deleted.
new_games=false
for f in add-games/*/* add-games/*/.images/*; do
	case $(basename "$f") in ._*|.DS_Store) ;; *) [ -f "$f" ] && new_games=true ;; esac
done
if $new_games; then
	echo "Adding new games..."
	mount -o remount,rw /boot
	for dir in add-games/*/; do
		has=false
		for f in "$dir"* "$dir".images/*; do
			case $(basename "$f") in ._*|.DS_Store) ;; *) [ -f "$f" ] && has=true ;; esac
		done
		$has || continue
		sys=$(basename "$dir")
		dst="${HOME}/roms/${sys}"
		mkdir -p "${dst}/.images"
		for f in "$dir"* "$dir".images/*.png; do
			[ -f "$f" ] || continue
			case $(basename "$f") in ._*|.DS_Store) continue ;; esac
			case $f in */.images/*) t="${dst}/.images/" ;; *) t="${dst}/" ;; esac
			cp "$f" "$t" && rm -f "$f"
		done
		new="${dir}.images/names.txt"
		if [ -f "$new" ]; then
			# keep one line per ROM file, the newest name winning
			cat "${dst}/.images/names.txt" "$new" 2>/dev/null |
				awk -F '\t' 'NF >= 2 { if (!($1 in n)) o[++k] = $1; n[$1] = $0 }
					END { for (i = 1; i <= k; i++) print n[o[i]] }' > "${dst}/.images/names.new" &&
				mv "${dst}/.images/names.new" "${dst}/.images/names.txt" && rm -f "$new"
		fi
		rm -rf "${dir}.images"
		rm -f "$dir"._* "$dir".DS_Store
		rmdir "${dst}/.images" 2>/dev/null
	done
	sync
	mount -o remount,ro /boot
fi
# F1GameStation: game screen size chosen in coverflow's menu (0 centred,
# 1 fit the height, 2 fill), for the rgb480x272fb panel driver
if [ -f "${HOME}/.f1gs-scale.conf" ]; then
	cat "${HOME}/.f1gs-scale.conf" > /sys/module/rgb480x272fb/parameters/scale 2>/dev/null
fi
# launch daemon
daemon >> "${LOGS}" 2>&1
