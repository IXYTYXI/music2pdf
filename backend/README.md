# RTX 4060 本地分轨后端

这部分代码在 NVIDIA 电脑上运行已有模型，输出 WAV 音轨。它是独立于现有网站的 Python 服务；当前网站尚未连接这个接口，也不会自动生成各乐器的谱。无需付费模型 API；首次运行需要联网下载权重，音频留在本机。

## Windows 快速开始

准备 Python **3.11 x64**（安装 Python Launcher）、较新的 NVIDIA 驱动、RTX 4060 8GB。建议 16GB 以上系统内存，预留 20GB 以上 SSD 空间。安装包和模型需要下载，实际空间取决于使用的预设。完整音频解码仍会占用系统内存。

把此 `backend` 文件夹复制到 4060 电脑。在该文件夹打开 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install-4060.ps1
```

这里的执行策略仅作用于当前脚本进程，不修改系统执行策略。脚本创建独立 `.venv`，安装 PyTorch 2.9.1 CUDA 12.8、pymss 2.1.4，然后执行 GPU 运算和模型目录检查。使用官方预编译 PyTorch 时通常无需单独安装 CUDA Toolkit。

先用一分钟音频跑四轨基准：

```powershell
.\.venv\Scripts\python.exe cli.py separate "D:\Music\test.wav" --preset four
```

运行时显示任务目录；在第二个 PowerShell 窗口用 `Get-Content "任务目录\worker.log" -Wait -Encoding UTF8` 查看日志。结束后，目录内会有：

- `stems/`：每个音轨的 WAV 文件。
- `result.json`：模型、GPU 名称、耗时、PyTorch 显存峰值和推理参数。
- `worker.log`：模型下载和分离日志。
- `input.*`：输入音频副本。

每次 CLI 调用创建独立目录，不覆盖已有结果。默认位于 `backend/data/cli/`；可用 `--output "D:\Music\separated"` 修改父目录。

## 三种预设

| 参数 | 模型目录名称 | 输出 |
|---|---|---|
| `four`（默认） | `HTDemucs4` | 人声、鼓、贝斯、其他 |
| `six` | `HTDemucs4_6stems` | 上述四轨加吉他、钢琴；钢琴分离属于实验能力 |
| `vocals` | `mel_band_roformer_vocals_becruily` | 人声、其余伴奏 |

```powershell
.\.venv\Scripts\python.exe cli.py separate "D:\Music\song.mp3" --preset vocals
.\.venv\Scripts\python.exe cli.py separate "D:\Music\song.mp3" --preset six
```

三种预设均固定 `device=cuda`、`batch_size=1`、关闭 TTA，不会悄悄回退 CPU。RoFormer 使用 132300 个采样点的分块（44.1kHz 下约 3 秒）、22050 点重叠；这是一组待实测的低显存起步参数，可能影响分离质量。Demucs 保留自己的分段配置，避免误套 RoFormer 参数。模型按需下载至 `backend/data/models/`，默认使用 pymss 的 ModelScope 下载源。

8GB 显存不保证任意模型/配置均可运行。若出现 CUDA OOM，查看日志，先关闭游戏及其他 GPU 程序，再测试 `four`。不要同时启动多个 CLI 分离进程或多个 API 服务。提升并行数量会增加显存占用。

## 启动本地 API

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-4060.ps1
```

启动后访问 <http://127.0.0.1:8765/docs> 查看可交互接口文档。服务只监听本机，单个服务内一次执行一个 GPU 任务，最多接纳四个未完成任务（含上传和排队），满时返回 HTTP 429。不要增加 uvicorn workers，也不要使用自动 reload 启动多个实例。

上传使用原始文件内容，**不是 multipart 表单**：

```powershell
curl.exe -X POST "http://127.0.0.1:8765/jobs?filename=song.wav&preset=four" -H "Content-Type: application/octet-stream" --data-binary "@D:\Music\song.wav"
```

返回 `id` 后，将下面的 `JOB_ID` 替换为实际值：

```powershell
curl.exe "http://127.0.0.1:8765/jobs/JOB_ID"
curl.exe "http://127.0.0.1:8765/jobs/JOB_ID/log"
```

任务状态为 `uploading` / `queued` / `running` / `completed` / `failed`。不展示虚构的百分比。完成后从 `result.files` 读取实际文件名下载：

```powershell
curl.exe "http://127.0.0.1:8765/jobs/JOB_ID/files/input_vocals.wav" -o vocals.wav
curl.exe -X DELETE "http://127.0.0.1:8765/jobs/JOB_ID"
```

删除仅允许已完成或失败任务。单文件限制 200 MiB，单任务超时 30 分钟（含首次模型下载）；超时会终止模型进程并将任务标记失败。首次下载慢时可以重试。扩展名检查不是完整格式校验，损坏的音频会在模型解码阶段失败。

任务状态保存在内存，重启不恢复队列；输入、输出和日志仍在 `backend/data/jobs/`，可以停服后手动清理。正常关闭服务会等待已接纳的任务结束。模型缓存需单独清理。

此接口面向本机开发，没有公网用户认证、配额或持久化任务系统。跨源浏览器写请求被拒绝；现有 HTTPS 网站尚不能直接使用它。网站接入需另做代理/部署与访问控制。

## 如何测你的 4060

1. 运行 `cli.py doctor`，确认 CUDA 运算成功且型号正确。
2. 用相同的一分钟录音分别运行三个预设；第一次包含权重下载和模型加载，第二次再比较。
3. 查看 `elapsed_seconds`（包括模型加载、解码、保存；第一次还含下载）。
4. 查看 `peak_allocated_vram_gb` 和 `peak_reserved_vram_gb`；这是 PyTorch 的统计，不含其他程序和所有驱动开销。
5. 听漏音、串音、持续音断裂，再检查分离结果是否有助于后续扒谱。

## 开发验证

不用安装 torch 或模型也能测试 API、队列和进程错误处理。在 `backend` 目录中：

```powershell
py -3.11 -m venv .venv-test
.\.venv-test\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv-test\Scripts\python.exe -m unittest discover -s tests -v
```

目前验证范围：API/队列/失败处理测试，pymss 2.1.4 发布包接口和模型目录核对。**尚未在 Windows / RTX 4060 上执行安装脚本或真实模型推理，未测得分离准确率和显存峰值。** 测试中的替代模型运行器只验证调度与文件交付，不代表模型质量。

参考：[pymss](https://github.com/pymss-project/pymss)、[PyTorch CUDA 安装指令](https://pytorch.org/get-started/previous-versions/#v291)、[Demucs 模型说明](https://github.com/facebookresearch/demucs)。运行器与模型权重许可分别以各自上游说明为准。
