#!/bin/sh
set -eu

module_name=evo_raw
module_version=0.2

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this uninstaller with sudo." >&2
    exit 1
fi

modprobe -r "$module_name" 2>/dev/null || true
if command -v dkms >/dev/null 2>&1; then
    dkms remove "$module_name/$module_version" --all 2>/dev/null || true
fi
rm -f /etc/modules-load.d/evo_raw.conf
rm -f /etc/modules-load.d/evoctl-usbmon.conf
rm -f /etc/udev/rules.d/60-evoctl.rules
rm -f /usr/local/libexec/evoctl-usbmon-access
udevadm control --reload-rules
echo "Removed $module_name."
