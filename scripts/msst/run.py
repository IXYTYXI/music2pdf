"""Run the pinned MSST-WebUI separation CLI in its isolated CPU environment."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / '.work/msst-webui'
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--check', action='store_true')
p.add_argument('--input', type=Path)
p.add_argument('--output', type=Path)
p.add_argument('--model-type')
p.add_argument('--model', type=Path)
p.add_argument('--config', type=Path)
a = p.parse_args()
python = BASE / 'venv/bin/python'
source = BASE / 'source'
if not python.is_file() or not source.is_dir():
    p.error('MSST environment missing; see scripts/msst/README.md')
if a.check:
    sys.exit(subprocess.call([str(python), 'scripts/msst_cli.py', '--help'], cwd=source))
if not all([a.input, a.output, a.model_type, a.model, a.config]):
    p.error('--input, --output, --model-type, --model, --config are required')
for path in [a.input, a.model, a.config]:
    if not path.exists():
        p.error(f'Path does not exist: {path}')
if not a.input.is_dir():
    p.error('--input must be a directory')
if a.output.exists():
    p.error('Use a new output directory to preserve earlier results')
if a.input.resolve() == a.output.resolve() or a.input.resolve() in a.output.resolve().parents:
    p.error('Output must be outside the input directory')
a.output.mkdir(parents=True)
cmd = [str(python), 'scripts/msst_cli.py', '--device', 'cpu', '--output_format', 'wav',
       '--input_folder', str(a.input.resolve()), '--output_folder', str(a.output.resolve()),
       '--model_type', a.model_type, '--model_path', str(a.model.resolve()), '--config_path', str(a.config.resolve())]
with (a.output/'run.log').open('w') as log:
    result = subprocess.run(cmd, cwd=source, stdout=log, stderr=subprocess.STDOUT)
# Upstream can report per-file failures without a nonzero exit; require outputs too.
outputs = list(a.output.rglob('*.wav'))
if result.returncode or not outputs:
    sys.exit(f'Separation failed or produced no WAV files; inspect {a.output / "run.log"}')
print(f'Created {len(outputs)} WAV files in {a.output}')
