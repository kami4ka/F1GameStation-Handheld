# F1GameStation: /mnt/autoexec.sh, sourced by MiyooCFW's /etc/main instead of
# starting gmenu2x. Starts the coverflow launcher; gmenu2x stays installed and
# opens with START or SELECT. Delete this file to boot straight into gmenu2x.
export FRONTEND="gmenu2x" # retroarch-setup looks for gmenu2x's core links
if test -x "${HOME}/coverflow/coverflow"; then
	cd "${HOME}/coverflow" && ./coverflow >> "${GMENU2X_LOGS:-/dev/null}" 2>&1
else
	cd "${HOME}/gmenu2x" && ./gmenu2x >> "${GMENU2X_LOGS:-/dev/null}" 2>&1
fi
