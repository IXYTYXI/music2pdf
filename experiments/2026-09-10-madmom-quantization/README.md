# madmom拍点驱动量化实验

状态：诊断实验，**未接入正式量化流程，未完成音乐准确性验收**。

固定同一录音的233个Basic Pitch事件及修复后的XML导出器，比较固定BPM与实际拍点量化。未向madmom输入原PDF。

| 方法（相同三拍分组与相位） | 休止标记 | 十六分休止 | 起音移动超过80ms | 同音高起点碰撞 |
|---|---:|---:|---:|---:|
| 固定93.75BPM、十六分网格 | 156 | 60 | 0 | 1对 |
| madmom拍点、十六分网格 | 132 | 45 | 1 | 0 |
| madmom拍点、八分网格 | 78 | 0 | 7 | 2对 |

改动误差是相对模型原始时间，不是相对真实弹奏的准确率。八分网格强制拉长所有短音，不能因更整齐就采用。三个相位均测试，完整结果见JSON。

madmom原生RNNDownBeatProcessor选择三拍候选，72个拍点，速度中位数93.75BPM；首个4.38秒拍点被标为第2拍，小节起点仍有问题。不能自动在开头添加一拍休止。三拍、四拍候选的拍点时间相同，区别主要在小节分组。

CNN起音检测在18.042秒C5碎片附近缺少新起音证据，支持进一步检查误切；14.765秒A4疑点附近存在全局起音，不能排除来自其他声部。未据此自动删音或合并。

## 复现

从仓库根目录执行。需要本地Python 3.11环境，madmom 0.17.dev0（本次安装提交27f032e8947204902c675e5e341a3faf5dc86dae）、numpy、scipy及soundfile；madmom自带模型需就绪。

```sh
mkdir -p .work/madmom-quantization
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .work/amt-comparison/venv/bin/python experiments/2026-09-10-madmom-quantization/run.py
.work/amt-comparison/venv/bin/python experiments/2026-09-10-madmom-quantization/quantize.py
node_modules/.bin/tsx experiments/2026-09-10-madmom-quantization/render.mts
```

脚本保留当时本地实验路径，不是开箱即用的公共基准：原音位于`outputs/feasibility-2026-09-10/samples/imslp-929871/audio/IMSLP579780.mp3`，原始事件位于`outputs/失败/Gae仅听录音转谱-2026-09-10/运行记录/notes.json`。二者不随仓库提交；原音SHA-256记录在beats.json。

JSON可直接查看。12份XML已逐项读回，均保留233事件及预期量化时间；validation.json为本地验证摘要。实验XML按每秒一拍序列化以复用导出器，里面的60BPM不是录音速度，不应用它直接判断回放速度。模型、音频、激活数组与临时输出未提交。

工具文档：https://github.com/CPJKU/madmom

详细核查：https://guanghe.feishu.cn/docx/ErD1dhteToU1eUxeFuUcO8GtnHc 第8节。
