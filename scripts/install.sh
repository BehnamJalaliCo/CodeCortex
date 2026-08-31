#!/usr/bin/env sh
set -eu

FULL=0
for arg in "$@"; do
  case "$arg" in
    --full) FULL=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

if command -v uv >/dev/null 2>&1; then
  uv tool install --force "git+https://github.com/BehnamJalaliCo/CodeCortex.git"
elif command -v pipx >/dev/null 2>&1; then
  pipx install --force "git+https://github.com/BehnamJalaliCo/CodeCortex.git"
else
  python3 -m pip install --user --upgrade "git+https://github.com/BehnamJalaliCo/CodeCortex.git"
fi

if [ "$FULL" -eq 1 ]; then
  cortex backend install all
fi

printf '%s\n' "CodeCortex installed. Run: cortex bootstrap"
