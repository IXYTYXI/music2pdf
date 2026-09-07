"""Local CLI entry point, also usable without starting the web API."""
import argparse
import json
import shutil
import sys
import uuid
from pathlib import Path
from service import DATA, PRESETS, run_job


def doctor():
    import torch
    from importlib.metadata import version
    print('Python:', sys.version.split()[0])
    print('PyTorch:', torch.__version__, 'CUDA runtime:', torch.version.cuda)
    print('pymss:', version('pymss'))
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA 不可用。请确认在 NVIDIA 电脑上运行、驱动已更新且安装的是 CUDA 版 PyTorch。')
    gpu = torch.cuda.get_device_properties(0)
    print('GPU:', gpu.name, 'VRAM GiB:', round(gpu.total_memory / 1024**3, 2))
    # Actually allocate and execute a small CUDA operation, not just enumerate a GPU.
    print('CUDA calculation:', (torch.ones(2, device='cuda') + 1).cpu().tolist())
    from pymss import get_model_entry
    for key, value in PRESETS.items():
        entry = get_model_entry(value['model'])
        print(key, entry.name)
    print('GPU 和模型目录检查通过；尚未下载权重或验证分离效果。')


def main():
    parser = argparse.ArgumentParser(description='Music2PDF RTX 4060 本地分轨')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor', help='检查 NVIDIA/CUDA 和模型目录')
    job = sub.add_parser('separate', help='分离一个本地音频文件')
    job.add_argument('input', type=Path)
    job.add_argument('--preset', choices=PRESETS, default='four')
    job.add_argument('--output', type=Path, default=DATA / 'cli')
    args = parser.parse_args()
    if args.command == 'doctor':
        doctor()
        return
    if not args.input.is_file() or args.input.suffix.lower() not in {'.wav', '.mp3', '.flac', '.m4a', '.ogg', '.aac'}:
        parser.error('请输入存在的 WAV、MP3、FLAC、M4A、OGG 或 AAC 文件。')
    if not 0 < args.input.stat().st_size <= 200 * 1024 * 1024:
        parser.error('输入必须非空且不超过 200 MiB。')
    folder = args.output.resolve() / uuid.uuid4().hex
    folder.mkdir(parents=True)
    shutil.copyfile(args.input, folder / ('input' + args.input.suffix.lower()))
    print('任务目录:', folder, flush=True)
    print('首次执行会下载所选模型。进度日志:', folder / 'worker.log', flush=True)
    result = run_job(folder, args.preset)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print('分轨音频:', folder / 'stems')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
