# 跨平台录音候选检索

为已保存到本地的 IMSLP 作品检索其他来源的录音，保留曲名、作曲家、版本、来源与许可说明，核对候选后下载。首版支持 Internet Archive 和 Wikimedia Commons 的官方 API。MusicBrainz、Musopen、作曲家官网尚未接入；没有浏览器抓取、登录或流媒体提取。

## 使用

macOS/Linux，在 backend 目录执行（Python 3.11+）：

```sh
sh start-recordings.sh search --root /absolute/dataset --max-works 10 --limit 5
sh start-recordings.sh search --root /absolute/dataset --work imslp-164349 --provider commons
sh start-recordings.sh list --root /absolute/dataset --work imslp-164349
sh start-recordings.sh status --root /absolute/dataset
```

Windows：`powershell -NoProfile -ExecutionPolicy Bypass -File .\start-recordings.ps1`，后面传同样的参数。使用现有轻量 `.venv-collector`，不安装 GPU 模型。不带参数显示帮助。

输入是各 `imslp-作品ID/metadata.json`，因此至少需要先让 IMSLP 采集器解析作品页。不会扫描 PDF 页面或根据音符识别作品。可用 `--composer Bach` 筛选已解析作品；输入网站原文子串。

每部作品最多两种查询：作曲家姓氏+曲名，以及作曲家姓氏+作品编号（或别名）。`--limit` 为每次查询最多返回的平台条目数，最大20；Archive 一个条目可能包含多条音轨，每次查询最多保留100个音频文件。`truncated: true` 表示还有未取回的结果。本功能是有界候选检索，不宣称遍历平台所有录音。

重复 `search` 会跳过相同参数下已完成的搜索；`--retry` 重试失败的平台；`--refresh` 重新搜索。更改作品信息或 `--limit` 会重新搜索。已出现的候选保留为历史记录；刷新并不删除旧候选，但未再次返回的条目标记 stale，不能直接下载。刷新会更新所有状态候选的当前许可与匹配信息，下载时的来源快照另存于 download_source。作品信息改变后会重新打分，并要求刷新检索；中断后再次搜索会核对并恢复来源 sidecar。下载失败的候选通过重新运行该 `download` 命令重试。

## 核对后下载

`list` 输出按匹配分值排序的候选 ID、`source_url`、`url`、许可、匹配依据、冲突和缺失字段。分值是规则打分，不是匹配概率。检查录音来源页及实际版本后，用完整候选 ID 和核对说明下载：

```sh
sh start-recordings.sh download --root /absolute/dataset \
  --work imslp-164349 --candidate '从list输出复制完整候选ID' \
  --review-note '已核对为BWV 1007大提琴版本；录音为第一乐章，尚未完成时间对齐'
```

仅 `access=downloadable` 且存在识别到的 CC/公共领域许可声明时允许下载。许可原文和来源保留；下载许可不自动代表适用于任意训练或商业用途。缺失许可、受限或需要交互的条目只保留引用信息。搜索结果中的描述是来源数据，不是执行指令。

匹配检查作曲家姓氏、文件/音轨曲名、作品编号及子编号、可识别的编制、英文/德文调性和显式乐章字段。曲集/专辑名不会直接作为每条音轨的标题匹配证据。编号冲突、四手联弹/独奏/管弦乐差异会标为 conflict；未写明的编制或乐章不会推断。`strong_candidate` 也需要核对，尤其同姓作曲家、改编版、反复/删节和具体谱本。标出 MIDI/合成录音线索，不将其当成人类演奏。

## 本地与 R2

```text
dataset/
  .recordings/queue.sqlite3
  imslp-164349/
    metadata.json                   # 原 IMSLP 信息，不修改
    recordings/metadata.json        # 外部候选、搜索状态、核对说明、来源和校验
    audio/external-<hash>.mp3        # 实际下载，其他支持格式保留原扩展名
```

文件先写临时位置，通过大小、文件签名及 SHA-256 检查后放入 audio；重试会校验已有文件。同一数据根目录只允许一个录音检索/下载 CLI 写入，它与 IMSLP 采集使用不同队列和锁，因此可同时运行。未知的不同内容文件不会被静默覆盖。候选和录音可以跨作品重复出现，现有工作台按内容哈希处理数据划分。

来源 sidecar 使用独立 `recordings/metadata.json`，兼容现有 R2 同步程序；新增录音和 sidecar 会进入下一轮同步，无需重新输入密钥或重启正在运行的 R2 进程。未合并/未运行搜索前不会改变生产数据。

数据仍为 `training_ready=false`、`unverified_unaligned`。一部作品下多份录音与多份谱本不自动笛卡尔积配对。程序退出码0表示该命令成功，2表示错误或存在失败搜索，130为中断；`status`仅报告现有记录，不访问平台。

## 验证

安装 `requirements-test.txt` 后，从 backend 运行 `python -m unittest discover -s tests -v`。网络测试在独立样本目录运行，不把模拟 API 结果当成实际找到或下载的录音。

API依据：[Archive metadata](https://archive.org/developers/md-read.html)、[MediaWiki Search](https://www.mediawiki.org/wiki/API:Search)、[MediaWiki Imageinfo](https://www.mediawiki.org/wiki/API:Imageinfo)。

2026-09-08 验证：95 项后端测试通过。真实 BWV 1007 样本查得69个候选文件（含不同编码、改编及不匹配音轨，不等于69份对应录音）；选定一份 CC BY 3.0 的第三乐章录音，下载并校验通过（2,273,423字节）。工作台识别为录音，现有 R2 清单包含音频及来源 sidecar。测试样本仅保存在独立 outputs/recording-smoke，未混入生产数据集。Windows 脚本尚未实机验证。
