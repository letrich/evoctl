#!/bin/sh
set -eu

module_name=evo_raw
module_version=0.2
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_dir=/usr/src/${module_name}-${module_version}

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer with sudo." >&2
    exit 1
fi

kernel_build=/lib/modules/$(uname -r)/build
if [ ! -f "$kernel_build/Makefile" ]; then
    echo "Missing headers for kernel $(uname -r)." >&2
    echo "Install linux-headers-$(uname -r), then run this script again." >&2
    exit 1
fi

install -d -m 0755 "$source_dir"
install -m 0644 "$script_dir/evo_raw.c" "$source_dir/evo_raw.c"
install -m 0644 "$script_dir/Makefile" "$source_dir/Makefile"
install -m 0644 "$script_dir/dkms.conf" "$source_dir/dkms.conf"

if command -v dkms >/dev/null 2>&1; then
    if dkms status "$module_name/$module_version" 2>/dev/null | grep -q .; then
        dkms remove "$module_name/$module_version" --all
    fi
    dkms add "$module_name/$module_version"
    dkms build "$module_name/$module_version"
    dkms install "$module_name/$module_version"
else
    echo "DKMS is not installed; installing for the current kernel only." >&2
    make -C "$source_dir" clean all
    make -C "$source_dir" install
fi

install -Dm0644 "$script_dir/../udev/60-evoctl.rules" \
    /etc/udev/rules.d/60-evoctl.rules
install -Dm0755 "$script_dir/../udev/evoctl-usbmon-access" \
    /usr/local/libexec/evoctl-usbmon-access
install -Dm0644 /dev/null /etc/modules-load.d/evo_raw.conf
printf '%s\n' "$module_name" > /etc/modules-load.d/evo_raw.conf
install -Dm0644 /dev/null /etc/modules-load.d/evoctl-usbmon.conf
printf '%s\n' usbmon > /etc/modules-load.d/evoctl-usbmon.conf

udevadm control --reload-rules
modprobe "$module_name"
modprobe usbmon
udevadm trigger --subsystem-match=misc --sysname-match=evo8

for device_path in /sys/bus/usb/devices/*; do
    if [ -f "$device_path/idVendor" ] && [ -f "$device_path/idProduct" ] && \
       [ "$(cat "$device_path/idVendor")" = 2708 ] && \
       [ "$(cat "$device_path/idProduct")" = 0007 ]; then
        /usr/local/libexec/evoctl-usbmon-access "$(cat "$device_path/busnum")"
    fi
done

echo "Installed $module_name. The EVO 8 remains available to ALSA and DAWs."
echo "Control device: /dev/evo8"
echo "Direct-ALSA meters: read-only access enabled for the EVO USB bus monitor."
