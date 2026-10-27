#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PYTHON=${QPYTHON:-python3}
JOBS=${QJOBS:-8}
TARGETS=${QEMU_TARGETS:-aarch64-softmmu}
PREFIX=${QEMU_PREFIX:-/opt/openubmc-qemu-hi1711}
BUILD=${QEMU_BUILD_DIR:-"$ROOT/build-hi1711"}
TOOLS="$ROOT/.tools"
export PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1
"$PYTHON" -c 'import sys,venv,zlib; assert sys.version_info >= (3,8), sys.version'
for tool in make pkg-config cc; do
  command -v "$tool" >/dev/null || { echo "Missing build tool: $tool" >&2; exit 1; }
done
pkg-config --atleast-version=2.56.0 glib-2.0 || { echo 'Install a suitable glib2-devel or source-built GLib, and set PKG_CONFIG_PATH.' >&2; exit 1; }
pkg-config --exists gmodule-no-export-2.0 zlib pixman-1 || { echo 'Missing GLib/GModule, zlib-devel, or pixman-devel.' >&2; exit 1; }
if [[ ! -x "$TOOLS/bin/python" ]]; then
  "$PYTHON" -m venv --system-site-packages "$TOOLS"
fi
"$TOOLS/bin/python" -m pip install --no-index --find-links="$ROOT/vendor/wheels" \
  pip==24.0 setuptools==69.5.1 wheel==0.43.0 meson==1.2.3 tomli==2.0.1 ninja==1.11.1.3
export PATH="$TOOLS/bin:$PATH"
mkdir -p "$BUILD"
if [[ -f "$BUILD/build.ninja" ]]; then
  echo "Existing configured build directory: $BUILD" >&2
  echo 'Choose a NEW QEMU_BUILD_DIR rather than overwriting cached configuration.' >&2
  exit 1
fi
cd "$BUILD"
"$ROOT/qemu/configure" \
  --prefix="$PREFIX" \
  --target-list="$TARGETS" \
  --python="$TOOLS/bin/python" \
  --cc="${CC:-cc}" --cxx="${CXX:-c++}" \
  --ninja="$TOOLS/bin/ninja" \
  --without-default-features \
  --enable-tcg --enable-tools --enable-pixman \
  --enable-fdt=internal --enable-slirp --enable-attr --enable-virtfs \
  --disable-virtfs-proxy-helper --disable-plugins --disable-docs \
  --disable-download --disable-containers \
  "${@}"
make -j"$JOBS"
"$BUILD/qemu-system-aarch64" --version
"$BUILD/qemu-system-aarch64" -machine help | grep -w hi1711
"$BUILD/qemu-system-aarch64" -openubmc-version
printf '\nBuild complete. Install explicitly with: make -C %q install\n' "$BUILD"
printf 'Run project tests with: %q test -C %q --suite openubmc --print-errorlogs\n' "$TOOLS/bin/meson" "$BUILD"
