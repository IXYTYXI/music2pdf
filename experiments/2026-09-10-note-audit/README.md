# 音符识别诊断记录（2026-09-10）

这些是实验脚本和证据，尚未接入正式应用，也不代表识谱准确率达标。

## 已确认的进展与限制

- 对完整52.062秒Gae录音运行钢琴专用模型，再与已有Basic Pitch输出比较首段4.25—19.65秒。
- 约11.28秒的E5，Basic Pitch先报F5，至11.605秒才报E5；钢琴模型在11.280秒报E5，与原录音频谱证据更一致。
- 钢琴模型未将两处持续音候选拆成两次，但左手低音与原谱分歧更多。
- 同音高、相对拍点投影±180毫秒的一对一配对：参考52音；Basic Pitch 71事件、51个参考位置对应；钢琴模型81事件、47个参考位置对应。这是参考配对，**不是准确率**，未配对也不自动等于错音。
- 三处C4的频谱证据比C3更有支持，钢琴模型却输出C3。180Hz高通诊断让两处恢复C4，第三处仍同时输出C3；G音分歧未解决。
- 高通后完整录音事件数234→269。真实低音C3对照仍被保留，但结束时间改变。否决将此滤波作为正式修复；不能把新增35事件直接当作新增35错音。
- 尚未完成独立人工逐音真值、完整音符验收及跨片段修正验证。拍号、排版不解决音高误判。

## 文件与运行条件

从仓库根目录运行脚本；它们保留当时实验路径，依赖本地资料，并非开箱即用的基准测试。

| 文件 | 用途 |
|---|---|
| `run_piano.py` | 完整录音钢琴模型推理，不输入原谱 |
| `audit_reference.py` | 事后原谱配对及局部频谱检查，依赖先前拍点和Basic Pitch输出 |
| `compare_models.py` | 同一乐句模型对比，导出统一力度的诊断MIDI |
| `run_highpass_diagnostic.py` | 同一模型180Hz四阶零相位高通反证实验 |
| `highpass_evidence.json` | 六处滤波前后事件与否决结论 |
| `spectral_evidence.json` | 六个原音窗口的频带峰值；零填充不提高真实频率分辨率 |

环境：Python 3.11、torch 2.14.0、numpy 1.26.4，以及librosa、soundfile、scipy、pretty_midi、piano_transcription_inference。
所需模型为qiuqiangkong/piano_transcription_inference官方钢琴模型；本地路径`.work/amt-comparison/piano-model.pth`。
模型SHA-256：`c3fa9730725bf4a762f1c14bc80cd5986eacda01b026f5a4a2525cd607876141`。

原音路径：`outputs/feasibility-2026-09-10/samples/imslp-929871/audio/IMSLP579780.mp3`。
原音SHA-256：`aa9e6ec36cea14583890d79eaae1f278ceff6206d17ea775741807df7815e3ae`。
先创建`.work/phrase-model-comparison`、`.work/phrase-audit`、`.work/low-octave-audit`。
完整重跑参考配对还需本地`.work/full-music-analysis/analysis.json`的拍点、`outputs/失败/Gae仅听录音转谱-2026-09-10/运行记录/notes.json`的原始识别结果。
录音、PDF、模型、环境和临时日志未提交；JSON证据可直接阅读。原谱仅用于事后核查，未反馈至两个模型输入。

详细核查文档：https://guanghe.feishu.cn/docx/ErD1dhteToU1eUxeFuUcO8GtnHc

## 项目当前状态

本次仓库另包含数据工作台的R2读取、PDF预览、OMR与音谱对齐改动。这些功能与本目录的音频识别诊断是不同工作内容，不能将工作台测试通过解释为自动扒谱准确性通过。
