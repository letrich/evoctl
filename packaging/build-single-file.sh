#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
output=${1-"$project_dir/dist/evoctl.pyz"}

case "$output" in
    /*) ;;
    *) output="$project_dir/$output" ;;
esac

mkdir -p "$(dirname -- "$output")"
python3 -m zipapp "$project_dir/src" \
    --main evoctl.__main__:main \
    --python '/usr/bin/env python3' \
    --output "$output"
chmod 0755 "$output"

echo "Built $output"
echo "Runtime dependency: Python 3.11+ with PySide6 QtWidgets installed."
