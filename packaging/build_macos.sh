#!/usr/bin/env bash
#
# Build Media Downloader for macOS: .app bundle -> code signature -> .dmg
#
#   ./packaging/build_macos.sh                  # ad-hoc signed build
#   ./packaging/build_macos.sh --with-ffmpeg    # bundle ffmpeg/ffprobe too
#   SIGN_IDENTITY="Developer ID Application: …" ./packaging/build_macos.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

APP_NAME="Media Downloader"
VERSION="$(python3 -c "import re;print(re.search(r'APP_VERSION = \"([^\"]+)\"', open('core/appinfo.py').read()).group(1))")"
ARCH="$(uname -m)"
DIST="$ROOT/dist"
APP="$DIST/$APP_NAME.app"
DMG="$DIST/MediaDownloader-$VERSION-macos-$ARCH.dmg"
STAGE="$DIST/dmg-stage"
VENV="$ROOT/.venv"
SIGN_IDENTITY="${SIGN_IDENTITY:--}"     # "-" means ad-hoc

WITH_FFMPEG=0
[[ "${1:-}" == "--with-ffmpeg" ]] && WITH_FFMPEG=1

step() { printf "\n\033[1;34m▸ %s\033[0m\n" "$1"; }
ok()   { printf "\033[0;32m  ✓ %s\033[0m\n" "$1"; }
die()  { printf "\033[0;31m  ✗ %s\033[0m\n" "$1" >&2; exit 1; }

# ── toolchain ────────────────────────────────────────────────────────────────
step "Muhitni tekshirish"
[[ -x "$VENV/bin/python" ]] || die "venv topilmadi. Ishga tushiring: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
PY="$VENV/bin/python"
"$PY" -c "import PyInstaller" 2>/dev/null || die "PyInstaller o'rnatilmagan: .venv/bin/pip install -r requirements-dev.txt"
ok "python $("$PY" -c 'import sys;print(".".join(map(str,sys.version_info[:3])))') · $ARCH · v$VERSION"

# ── icon ─────────────────────────────────────────────────────────────────────
step "Ikona"
if [[ ! -f assets/icon.icns || packaging/make_icon.py -nt assets/icon.icns ]]; then
  "$PY" packaging/make_icon.py
fi
ok "assets/icon.icns"

# ── optional ffmpeg staging ──────────────────────────────────────────────────
export MDL_BUNDLE_FFMPEG=0
if [[ $WITH_FFMPEG -eq 1 ]]; then
  step "FFmpeg'ni bundle'ga tayyorlash"
  [[ -x packaging/bin/ffmpeg ]] || die "packaging/bin/ffmpeg yo'q. Avval: ./packaging/fetch_ffmpeg.sh"
  export MDL_BUNDLE_FFMPEG=1
  ok "packaging/bin/ffmpeg ($(du -h packaging/bin/ffmpeg | cut -f1))"
fi

# ── build ────────────────────────────────────────────────────────────────────
step "PyInstaller bilan .app yig'ish"
"$PY" -m PyInstaller packaging/MediaDownloader.spec --noconfirm --clean --log-level WARN
[[ -d "$APP" ]] || die ".app yaratilmadi"
ok "$(basename "$APP") ($(du -sh "$APP" | cut -f1))"

# ── sign ─────────────────────────────────────────────────────────────────────
step "Imzolash"
# Nested Mach-O objects must be signed before the bundle that contains them.
find "$APP" -type f \( -name "*.so" -o -name "*.dylib" \) -print0 |
  xargs -0 -I{} codesign --force --sign "$SIGN_IDENTITY" --timestamp=none {} 2>/dev/null || true

if [[ "$SIGN_IDENTITY" == "-" ]]; then
  codesign --force --deep --sign - "$APP"
  ok "ad-hoc imzolandi (notarize qilinmagan)"
else
  codesign --force --deep --options runtime --timestamp \
           --sign "$SIGN_IDENTITY" "$APP"
  ok "imzolandi: $SIGN_IDENTITY"
fi
codesign --verify --deep --strict "$APP" && ok "imzo tekshiruvi o'tdi"

# ── smoke test ───────────────────────────────────────────────────────────────
step "Smoke test"
"$APP/Contents/MacOS/$APP_NAME" --no-open >/tmp/mdl-smoke.log 2>&1 &
SMOKE_PID=$!
for _ in $(seq 1 40); do
  grep -q "http://127.0.0.1" /tmp/mdl-smoke.log && break
  sleep 0.25
done
kill "$SMOKE_PID" 2>/dev/null || true
grep -q "http://127.0.0.1" /tmp/mdl-smoke.log \
  && ok "bundle ishga tushdi: $(grep -o 'http://127.0.0.1:[0-9]*' /tmp/mdl-smoke.log | head -1)" \
  || die "bundle ishga tushmadi. Log: /tmp/mdl-smoke.log$(printf '\n'; tail -20 /tmp/mdl-smoke.log)"

# ── dmg ──────────────────────────────────────────────────────────────────────
step "DMG yasash"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
[[ -f "$DMG" ]] && rm -f "$DMG"

hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$STAGE" \
  -fs HFS+ \
  -format UDZO \
  -imagekey zlib-level=9 \
  -quiet \
  "$DMG"

rm -rf "$STAGE"
codesign --force --sign "$SIGN_IDENTITY" "$DMG" 2>/dev/null || true
ok "$(basename "$DMG") ($(du -h "$DMG" | cut -f1))"

# ── summary ──────────────────────────────────────────────────────────────────
printf "\n\033[1;32m✅ Tayyor\033[0m\n"
printf "   App:  %s\n" "$APP"
printf "   DMG:  %s\n" "$DMG"
printf "   SHA:  %s\n" "$(shasum -a 256 "$DMG" | cut -d' ' -f1)"

if [[ "$SIGN_IDENTITY" == "-" ]]; then
  printf "\n\033[0;33m⚠  Ad-hoc imzo — Gatekeeper foydalanuvchini ogohlantiradi.\033[0m\n"
  printf "   Foydalanuvchi uchun: System Settings ▸ Privacy & Security ▸ \"Open Anyway\"\n"
  printf "   Yoki bitta buyruq:   xattr -dr com.apple.quarantine \"/Applications/%s.app\"\n" "$APP_NAME"
fi
