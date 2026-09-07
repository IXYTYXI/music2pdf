# 谱间 · Music2PDF

把钢琴音频转换为可试听、校正和导出的五线谱与主旋律简谱。中文浏览器工作台，所有音频解码和模型推理在用户设备中完成，无需上传音频或配置付费 API。

## 运行

需要 Node.js 22.13+（推荐 24）。

```sh
npm ci
npm run dev
```

依赖安装后会自动将 Basic Pitch 模型与 WASM 引擎复制到 `public/`。访问开发服务器输出的地址。模型文件跟随网站部署，不依赖外部模型 CDN。

```sh
npm test
npm run typecheck
npm run build
node scripts/check-inference.mjs
```

最后一条执行真实模型的合成 C 大三和弦测试，不代表真实钢琴录音准确度。

## 使用

1. 选择音频文件或拖放至导入区。支持浏览器可解码的 WAV、MP3、FLAC、M4A、OGG 等；不超过 200 MB / 60 分钟。导入时仅读取时长供试听；可选择整首或输入起止秒数，超过 10 分钟的录音默认先试识别 1 分钟。
2. 点击「开始转谱」后解码音频，只为所选范围生成识别数据；浏览器仍需完整解码原文件，长录音依然占用较多内存。每 30 秒（前后各含最多 2 秒上下文）使用独立 Worker 运行 Basic Pitch，多音识别无需把钢琴先拆成高低频音轨。可选择自动、1、2 或 4 路并行。自动模式依据 CPU 核数与浏览器可用的设备内存信息选择 1–2 路；单段录音仅使用一路。可取消全部任务，任意分段失败会停止其他任务。并行会增加内存占用，不保证按线程数等比例加速。
3. 对照原音调整速度、拍号和调性，切换五线谱、主旋律简谱和音符校正。
4. 试听为合成音色。可增加、删除音符，修改音高和起止时间，或恢复本次识别结果。
5. 导出完整音符的 MIDI / MusicXML；在五线谱或简谱页面使用「打印 / PDF」，在浏览器打印窗口中选择另存为 PDF。

「先看看示例乐谱」使用已知音符展示排版，明确标记为示例，不运行识别。「试试练习曲」生成原创合成音频，需点击开始转谱才运行真实模型。

## 当前范围与限制

- 第一版使用 Spotify Basic Pitch 通用多音模型，尚未接入专门钢琴模型、踏板检测或音源分离。
- 速度基于起音间隔粗估；拍号和调性由用户确认。支持 2/4、3/4、4/4 与大调调号；目前不自动识别变速、复拍子、三连音、弱起和小调。
- 时值量化到十六分音符；跨小节音符使用延音线；重叠且时长不同的音符使用独立声部保留。
- 中央 C 为上下谱表的启发式分界，不等于真实左右手分配。长踏板、混响、快速装饰音和密集和弦可能误识别，排版也可能需要在专业打谱软件中整理。
- 简谱旋律用音高连续性、音长和音区评分提取，不等于可靠识别的主旋律，支持对照音频校正。
- 音符在当前页面内存中保存；刷新或关闭页面会丢失编辑，请先导出。
- 推荐桌面端 Chrome / Edge。未执行浏览器自动交互或视觉 QA；类型、构建、核心乐谱测试及真实模型合成和弦测试已用于验证。

## 代码结构

- `app/page.tsx`：导入、任务状态、工作台和导出交互。
- `lib/music/long-audio.ts`：最多 4 路并行分段、按原音时间顺序合并、边界音符去重与延音衔接、总进度及取消；完整音频仍在浏览器内解码，内存占用随音频长度增加。
- `lib/music/transcribe.worker.ts`：独立模型推理，WASM 后端不可用时回退 CPU；每段完成或取消销毁 Worker，释放模型内存。
- `lib/music/score.ts`：统一音符类型、时值量化、多声部 MusicXML、旋律候选和简谱音高。
- `lib/music/audio.ts`：解码、重采样、试听及原创示例。
- `lib/music/export.ts`：MIDI 与下载。
- `components/score-view.tsx`：OpenSheetMusicDisplay 五线谱与简谱排版。
- `components/note-editor.tsx`：音符校正。

未来可以增加返回同一 `Note[]` 类型的服务器模型适配器，按 `track` 扩展乐器轨道；当前不提供歌曲或交响乐分轨能力。GPU 推理服务应独立于 Cloudflare Workers 部署。

## 部署

当前使用 Sites / Cloudflare Workers 托管前端与静态模型文件。`npm run build` 输出 `dist/server` 和 `dist/client`。`.openai/hosting.json` 记录 Sites 项目绑定，不包含密钥。连接 GitHub 只保存代码，不会自动触发部署，除非后续配置发布流程。

## 第三方许可

Basic Pitch 模型和实现由 Spotify 提供，Apache-2.0；TensorFlow.js 为 Apache-2.0；OpenSheetMusicDisplay 为 BSD-3-Clause；Tone.js MIDI 为 MIT。详见 `THIRD_PARTY_NOTICES.md` 与对应依赖的许可文件。

## RTX 4060 本地分轨代码

新增独立的 [Python 分轨后端与 Windows 使用说明](backend/README.md)，提供 CUDA 推理、人声/四轨/六轨预设、单任务排队、结果下载以及显存/耗时记录。当前网站尚未接入此服务。代码已做无 GPU 的接口和调度测试，Windows 安装及 4060 真实推理仍需在目标电脑验证。

## 多版本训练数据准备

新增 [本地数据工作台](backend/DATASET.md)：按作品文件夹收集多份录音和乐谱，试听/预览、检查缺失及重复内容，以固定种子导出训练/验证/测试 JSONL 索引。运行 `backend/start-dataset.sh`（Mac/Linux）或 `backend/start-dataset.ps1`（Windows），访问本机 8766 端口。无需 GPU；尚未进行识谱、对齐或模型训练。
