# F1GameStation: login shell on the debug UART (UART0, PE0/PE1) so the
# card can be updated over the UART; started once from the boot hooks.
if ! pidof getty >/dev/null || ! ps | grep -q '[g]etty -L ttyS0'; then
	setsid /sbin/getty -L 115200 ttyS0 vt100 </dev/null >/dev/null 2>&1 &
fi
