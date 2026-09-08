#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv-collector/bin/python ]; then
  python3 -m venv .venv-collector
fi
if ! cmp -s requirements-collector.txt .venv-collector/requirements-installed.txt; then
  .venv-collector/bin/python -m pip install -r requirements-collector.txt
  cp requirements-collector.txt .venv-collector/requirements-installed.txt
fi
if [ "$#" -eq 0 ]; then
  set -- --help
fi
exec .venv-collector/bin/python recording_collector.py "$@"
