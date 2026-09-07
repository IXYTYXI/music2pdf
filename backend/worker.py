"""CUDA-only separation worker. Invoked in its own process for each job."""
import argparse
import json
import time
from pathlib import Path

from service import PRESETS


def separate(input_path, output, preset, models):
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('未发现可用 CUDA GPU。请在 RTX 4060 电脑上安装 NVIDIA 驱动和 CUDA 版 PyTorch。')
    from pymss import MSSeparator

    output.mkdir(parents=True, exist_ok=True)
    stems = output / 'stems'
    stems.mkdir(exist_ok=True)
    torch.cuda.set_device(0)
    torch.cuda.reset_peak_memory_stats(0)
    torch.set_num_threads(4)
    # RoFormer uses sample counts. Demucs keeps its model-specific segment defaults.
    params = {'batch_size': 1, 'normalize': False}
    if preset == 'vocals':
        params.update(chunk_size=132300, overlap_size=22050)
    started = time.perf_counter()
    with MSSeparator.from_model_name(
        PRESETS[preset]['model'], download=True, model_dir=str(models),
        device='cuda', device_ids=[0], output_format='wav',
        store_dirs=str(stems), save_as_folder=False, use_tta=False,
        inference_params=params,
    ) as separator:
        successful = separator.process_folder(str(input_path))
        if not successful:
            raise RuntimeError('音频解码或模型分离失败，未生成有效结果；请查看前面的模型日志。')
    torch.cuda.synchronize()
    files = sorted(p.name for p in stems.glob('*.wav'))
    if len(files) != {'four': 4, 'six': 6, 'vocals': 2}[preset]:
        raise RuntimeError('模型没有输出预期的多个音轨，请检查模型配置和日志。')
    result = {
        'files': files, 'model': PRESETS[preset]['model'], 'preset': preset,
        'gpu': torch.cuda.get_device_name(0),
        'elapsed_seconds': round(time.perf_counter() - started, 2),
        'peak_allocated_vram_gb': round(torch.cuda.max_memory_allocated(0) / 1024**3, 3),
        'peak_reserved_vram_gb': round(torch.cuda.max_memory_reserved(0) / 1024**3, 3),
        'inference_params': params,
    }
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--preset', choices=PRESETS, default='four')
    args = parser.parse_args()
    separate(args.input, args.output, args.preset, args.models)


if __name__ == '__main__':
    main()
