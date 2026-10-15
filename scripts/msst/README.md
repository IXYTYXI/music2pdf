# MSST-WebUI 音源分离接入

上游：https://github.com/SUC-DriverOld/MSST-WebUI
固定版本：332c024771d9c048d209b12663d4745a4cb676f2
源码许可证：AGPL-3.0；模型权重须分别核对许可证。

用途：交响乐等混音的分离前处理，通过上游 MSSeparator/CLI 调用模型。
此接入默认 CPU，保存无损 WAV，不把音频分离结果视为乐谱或准确的独奏声部。
现阶段接入命令行后端，不包含完整 Gradio WebUI 的启动配置。

本地源码与独立 Python 环境位于 `.work/msst-webui/{source,venv}`。
安装依赖见 requirements-cpu.txt。该清单覆盖基础接口和 Demucs；其他架构按模型需要补充依赖。

重建安装（Python 3.11）：`sh scripts/msst/setup.sh`。可用环境变量 `MSST_PYTHON` 指定 Python 3.11 路径。

检查：`python3 scripts/msst/run.py --check`
运行：`python3 scripts/msst/run.py --input /绝对路径/输入文件夹 --output /绝对路径/新输出文件夹 --model-type htdemucs --model /绝对路径/模型权重 --config /绝对路径/模型配置`

原录音保持原样；输出目录必须新建。分离日志随输出保存。
模型与 YAML 必须配套，先核对配置中的 instruments/sources。
普通人声/鼓/贝斯/other 模型不能据此宣称分出了交响乐的弦乐、木管、铜管；更不能保证独立提取每件乐器。

交响乐验收：同一真实录音比较原音与各分轨，检查串音、漏音、起音损失和同步，再送入转写；不能只以文件生成成功验收。
当前未执行交响乐分离质量测试，尚未选定交响乐专用权重。

## VR 木管模型首次实测修正

上游 `spec_utils.py` 的分频谱重建缓冲区使用未初始化的 `np.ndarray`，未写入频段可能混入无效值。提供 `vr-zero-initialize.patch` 改为零初始化，setup.sh 可重复安全应用。零频谱重建测试在模拟脏内存下复现错误，修正后输出为零。此补丁不调整模型权重或分离阈值。
