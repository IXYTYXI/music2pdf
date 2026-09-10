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

## 受约束的碎片修复（后续实验）

`rhythm_cleanup.py` 替代按中央C分组、统一吞掉半拍空隙的做法：只有显式 `voice_id`、`continuous_to` 和未量化拍位置同时存在，才调整小间隙或重叠。原始间隙上限0.125拍、调整上限一个网格；不同长度的和弦、保持音、明确休止和断奏受到保护。这些阈值是实验参数，不是乐理标准。

当前录音没有上述声部及连接标注，因此**没有自动执行声部缝合**。另一路 `repair_fragments.py` 检查相邻同音高碎片：边界距离不超过30ms，madmom边界附近没有显著新起音，且独立钢琴模型的同音高事件跨越边界，才生成合并候选。缺少起音并不能证明没有重新弹奏；独立模型只支持跨越边界，不证明整个合并时值准确。

整段实测合并18.042秒C5、50.967秒C3两处边界，233事件变为231，其余事件逐项不变。同一 dynamic16 / phase1 设置下休止标记132→130，十六分休止45→45。没有校正音高、声部推断或首小节起点，仍未通过音乐准确性验收，未接入正式产品流程。

```sh
python3 -m unittest discover -s experiments/2026-09-10-madmom-quantization -p 'test_rhythm_cleanup.py' -v
.work/amt-comparison/venv/bin/python experiments/2026-09-10-madmom-quantization/repair_fragments.py
.work/amt-comparison/venv/bin/python experiments/2026-09-10-madmom-quantization/quantize.py --notes .work/rhythm-repair/notes.json --output-dir .work/rhythm-repair/quantized
node_modules/.bin/tsx experiments/2026-09-10-madmom-quantization/render.mts .work/rhythm-repair/quantized
```

额外输入为本地 `.work/phrase-model-comparison/notes.json`（独立钢琴模型），以及原实验起音激活数组。原始数据不覆盖，候选和逐项审计写入 `.work/rhythm-repair/`。12项保护测试通过；12份候选XML逐项读回，均保留231事件及预期量化位置。
# Partitura 声部候选对照（2026-09-10）

## 首乐句多模型筛选：未通过

`phrase_consensus.py` 对原录音 4.25–19.65 秒做独立候选，原谱只在保存候选
之后读入验收。BP 音符需另一模型同音高且起音差不超过 100ms 支持；每个
支持事件在单次匹配中只用一次。补音需钢琴模型与 Omnizart 支持，不把两个
Omnizart 版本算作两票。保留事件的原时值不修改。

在 100/180ms 验收容差下，71 个事件变为 60 个，参考匹配 51→50，未匹配
事件 20→10，未匹配参考音 1→2。原谱第4小节左手 C4、G4 被误删。
参考起音仍是拍点投影，不能将这些数量称为人工录音标注准确率。
相同排谱设置下休止符 49→43，声部与时值混乱没有解决；不进入正式导出。
PDF 对照归档到 `outputs/失败/首乐句多模型筛选-2026-09-10/`。
此结果证明“没有其他模型支持就删除”不安全，不能用更少音符当作验收通过。
新增 3 项匹配保护测试，实验测试总计 21 项；测试通过不代表转谱正确。

追加定位：该重叠对应原音频 27.323 秒的 A4 与 27.590 秒的 E4。
另外三份模型在附近输出 E3 起音（27.587、27.620、27.680 秒），没有 E4
新起音；当前模型直到 27.788 秒才输出 E3。这是八度/起音分歧，不能靠截短 A4
解决，也不能凭模型多数票删 E4。运行 `audit_overlap.py` 可复现事件对照。

`review_candidates` 已增加候选声部保护：撤回存在非和弦重叠的整个候选组，
保留全部音符字段；不改变正式导出。共 18 项实验保护测试通过。
可查看 `outputs/查看识谱结果/17-重叠音符定位/先看这里.html`，包含原录音
26.8–28.8 秒片段和时间表。本轮未生成修正谱，因为音高真值尚未确认。

使用 Partitura 1.9.0，冻结原 `dynamic16` 的 233 个音符；仅添加
`voice_candidate`，不修改音高、起止时间，也不生成 `continuous_to`。
这次试验没有使用原谱辅助声部推断。

| 方法 | 声部数 | 同声部非和弦重叠对数 | 同声部跨谱表重叠对数 |
|---|---:|---:|---:|
| 现有空闲声部优先规则的 Python 对照实现 | 5 | 0 | 0 |
| Partitura 全局和弦模式 | 4 | 0 | 40 |
| Partitura 按现有谱表分组 | 5 | 1 | 0 |

按谱表版本仍沿用中央 C 划分，并非识别左右手。出现的问题是第 36 拍的
A4（1 拍）与第 36.5 拍的 E4（半拍）得到同一候选声部，存在半拍重叠。
不能据此截短 A4：重叠也可能来自保持音或转写错误，需要独立证据。
全局版本跨谱表归组不一定违背音乐声部理论，但不能直接当作左右手排谱。

结论：暂不接入正式导出。没有证明音符准确率、休止符数量或谱面正确性改善。
本轮没有生成声称改善的新 PDF。数据在 `.work/partitura/comparison.json`，
失败候选归档在 `outputs/失败/Partitura-2026-09-10/`。

复现（在独立 Python 环境安装 `partitura==1.9.0`）：

```sh
python experiments/2026-09-10-madmom-quantization/compare_voices.py
python -m unittest discover -s experiments/2026-09-10-madmom-quantization -p 'test_*.py'
```

新增保护测试覆盖保持音、和弦、真实间隔、谱表隔离、空输入与非法输入。
原始事件逐字段不变由整段运行断言检查；候选标签不等于连奏证据。
