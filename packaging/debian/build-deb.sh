#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/../.." && pwd)
stage_dir=$(mktemp -d)
trap 'rm -rf -- "$stage_dir"' EXIT HUP INT TERM
version=$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' \
    "$project_dir/src/evoctl/__init__.py")
[ -n "$version" ] || {
    echo "Could not determine evoctl version." >&2
    exit 1
}

output=${1-"$project_dir/dist/evoctl_${version}_all.deb"}
case "$output" in
    /*) ;;
    *) output="$project_dir/$output" ;;
esac

install -d -m 0755 "$stage_dir/DEBIAN"
sed "s/@VERSION@/$version/" "$script_dir/control.in" \
    > "$stage_dir/DEBIAN/control"
chmod 0644 "$stage_dir/DEBIAN/control"
install -m 0755 "$script_dir/postinst" "$stage_dir/DEBIAN/postinst"
install -m 0755 "$script_dir/prerm" "$stage_dir/DEBIAN/prerm"
install -m 0755 "$script_dir/postrm" "$stage_dir/DEBIAN/postrm"

"$project_dir/packaging/build-single-file.sh" "$stage_dir/usr/bin/evoctl"
install -Dm0644 "$script_dir/evoctl.desktop" \
    "$stage_dir/usr/share/applications/evoctl.desktop"
install -Dm0644 "$project_dir/README.md" \
    "$stage_dir/usr/share/doc/evoctl/README.md"
install -Dm0644 "$script_dir/copyright" \
    "$stage_dir/usr/share/doc/evoctl/copyright"

dkms_dir="$stage_dir/usr/src/evo_raw-0.2"
install -d -m 0755 "$dkms_dir"
install -m 0644 "$project_dir/packaging/evo_raw/evo_raw.c" "$dkms_dir/evo_raw.c"
install -m 0644 "$project_dir/packaging/evo_raw/Makefile" "$dkms_dir/Makefile"
install -m 0644 "$project_dir/packaging/evo_raw/dkms.conf" "$dkms_dir/dkms.conf"

install -Dm0644 "$project_dir/packaging/udev/60-evoctl.rules" \
    "$stage_dir/lib/udev/rules.d/60-evoctl.rules"
install -Dm0755 "$project_dir/packaging/udev/evoctl-usbmon-access" \
    "$stage_dir/usr/libexec/evoctl/evoctl-usbmon-access"
install -Dm0644 "$script_dir/evo_raw.modules-load" \
    "$stage_dir/usr/lib/modules-load.d/evo_raw.conf"
install -Dm0644 "$script_dir/evoctl-usbmon.modules-load" \
    "$stage_dir/usr/lib/modules-load.d/evoctl-usbmon.conf"

find "$stage_dir" -type d -exec chmod 0755 {} +
mkdir -p "$(dirname -- "$output")"
dpkg-deb --root-owner-group --build "$stage_dir" "$output"
echo "Built $output"
