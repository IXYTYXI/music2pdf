#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
BASE="$ROOT/.work/msst-webui"
REV=332c024771d9c048d209b12663d4745a4cb676f2
mkdir -p "$BASE"
if [ ! -d "$BASE/source/.git" ]; then
 git clone https://github.com/SUC-DriverOld/MSST-WebUI.git "$BASE/source"
 git -C "$BASE/source" checkout --detach "$REV"
fi
if [ "$(git -C "$BASE/source" rev-parse HEAD)" != "$REV" ]; then
 echo 'Unexpected upstream revision; refusing to overwrite existing source.' >&2
 exit 1
fi
if git -C "$BASE/source" apply --check "$ROOT/scripts/msst/vr-zero-initialize.patch" 2>/dev/null; then
 git -C "$BASE/source" apply "$ROOT/scripts/msst/vr-zero-initialize.patch"
elif ! git -C "$BASE/source" apply --reverse --check "$ROOT/scripts/msst/vr-zero-initialize.patch" 2>/dev/null; then
 echo 'VR compatibility patch cannot be applied safely.' >&2
 exit 1
fi
if [ ! -f "$BASE/venv/bin/python" ]; then
 "${MSST_PYTHON:-python3.11}" -m venv "$BASE/venv"
fi
"$BASE/venv/bin/python" -m pip install -r "$ROOT/scripts/msst/requirements-cpu.txt"
"$BASE/venv/bin/python" "$ROOT/scripts/msst/run.py" --check
