#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv-dataset/bin/python ]; then
  python3 -m venv .venv-dataset
fi
.venv-dataset/bin/python -m pip install -r requirements-api.txt -r requirements-r2.txt -r requirements-alignment.txt
printf '%s\n' '数据工作台：http://127.0.0.1:8766 （保持终端打开，Ctrl+C 停止）'
exec .venv-dataset/bin/python -m uvicorn dataset_app:app --host 127.0.0.1 --port 8766 --workers 1
