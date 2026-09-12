#!/usr/bin/env bash
set -euo pipefail

package_file="${1:?package file is required}"
plugin_id="${2:?lowercase plugin id is required}"

if [[ "$(basename "$package_file")" != "package.v3.json" ]]; then
  echo "Unsupported package file: $package_file" >&2
  exit 2
fi

plugin_dir="plugins.v3/${plugin_id}"
