# IMSLP 自动采集器

不需要提供作品链接。程序从 IMSLP 官方作品目录 API 分页发现作品，再访问作品页，收集乐谱、录音和元数据。采集器是本地命令行工具；现有数据工作台负责查看采集结果。

## 启动

macOS / Linux（Python 3.11+），在 backend 目录运行：

```sh
sh start-imslp.sh run --root "$HOME/MusicDataset/IMSLP" --pages 1 --max-works 10 --max-files 20
```

Windows（Python 3.11+，已安装 Python Launcher）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-imslp.ps1 run --root D:\MusicDataset\IMSLP --pages 1 --max-works 10 --max-files 20
```

脚本创建独立的 `.venv-collector` 并安装 requests、BeautifulSoup，不安装 GPU 模型。直接运行不带参数时使用 `run` 和 `backend/data/imslp`。

## 下载行为

默认访问作品页提供的正常下载入口，不因 robots.txt 的 Disallow 规则中止。可加 `--respect-robots` 开启严格模式；此时禁止的路径会记为 blocked。默认仍限速，遇到 429 会退避，登录/验证码等交互要求会保留错误原因。

旧版本因 robots.txt 标为 blocked 的任务，可使用 `collect --retry` 重新尝试。无需提供“批量授权配置文件”；原 `--permission` 选项已移除。

目录 API：https://imslp.org/wiki/IMSLP:API
会员说明：https://imslp.org/wiki/IMSLP:Subscriptions

## 常用命令

以下示例省略启动脚本，使用虚拟环境的 Python 运行 `imslp_collector.py`。

```sh
# 仅扩充目录；每页目前为 1000 条，所有作品都保留以便以后更换筛选条件
python imslp_collector.py discover --root /absolute/dataset --pages 10

# 对已发现的作品筛选。名称使用 IMSLP 原文，大小写不敏感；子串匹配。
python imslp_collector.py collect --root /absolute/dataset --composer Bach --instrument keyboard --require-both --max-works 50 --max-files 30

# 只解析作品信息和文件清单，不尝试下载
python imslp_collector.py collect --root /absolute/dataset --metadata-only --max-works 50

# 查看总状态；不发网络请求
python imslp_collector.py status --root /absolute/dataset

# 解决权限或网络问题之后，重试受限和失败项目
python imslp_collector.py collect --root /absolute/dataset --retry

# 从头重新遍历目录，发现被插入到旧目录位置的新作品
python imslp_collector.py discover --root /absolute/dataset --refresh --pages 10

# 下一批继续，不加 --refresh
python imslp_collector.py discover --root /absolute/dataset --pages 10
```

`run` 依次执行 discover 与 collect。`--pages` 限制本轮目录页数，`--max-works` 限制本轮新解析或有待下载文件的作品数，`--max-files` 限制本轮文件尝试次数。所有上限均为正整数；不表示整站最终规模。再次运行相同命令继续队列，无需重新提交作品链接。

作曲家筛选仅作用于已经发现的作品；前几页可能没有目标作曲家，需要继续扩充目录。乐器筛选检查作品的 Instrumentation 原文，不自动把 piano、keyboard、harpsichord 视为同义词。`--require-both` 检查作品页是否列出两类可下载格式的文件，不保证其下载权限或版本一致。

`--refresh` 在 discover/run 中将目录游标重置到起点；不要每批都加。目录是可变排序列表，仅从旧游标继续不能保证发现插入在游标之前的新记录，因此定期从头扫描。collect 的 `--refresh` 重新解析作品页，保留文件下载记录；它每次从队列开头开始，刷新全队列时应设置足够大的 `--max-works`。

## 可选会员登录

`--cookies /absolute/private/imslp-cookies.txt` 读取 Netscape 格式 Cookie 文件，保留域名和有效期限制。程序不会打印或复制 Cookie 到数据目录。不要将其放入 Git 仓库，不需要向助手发送密码。会员真实登录下载尚未验证。

```sh
python imslp_collector.py collect --root /absolute/dataset --retry --cookies /absolute/private/imslp-cookies.txt
```

会员可用于正常免等待下载；商业流媒体仅保留引用信息。文件各自的许可信息仍保存到 metadata.json。

## 输出与工作台

```text
dataset/
  .imslp/queue.sqlite3
  .imslp/collector.lock
  imslp-1637322/
    metadata.json
    scores/IMSLP12345.pdf
    audio/IMSLP67890.mp3
```

作品 ID 优先采用 API 的 pageid；缺失时使用作品链接哈希。metadata.json 保存作曲家、作品目录信息、作品页字段、文件标题、章节/乐章上下文、许可、演奏者/出版社原文、来源以及下载状态。缺失字段不推断；与实际演奏的乐章对应关系需要核对。

在现有数据工作台填入相同的数据根目录并扫描，即可预览成功下载的 PDF/录音及导出数据划分。只有元数据的作品会显示缺少文件。所有数据仍为 `unverified_unaligned`，不表示可直接用于监督训练。

下载使用临时 `.part` 文件和原子重命名，检查大小与文件签名，并保存 SHA-256。中断后重启整个未完成文件，暂不支持 HTTP Range 字节级续传。已下载文件会复核哈希，丢失或损坏后重新下载。同一作品内内容相同的文件复用已有路径，跨作品不移动文件，由工作台将相同内容绑定为同一划分组。

默认请求间隔至少 2 秒；启用 `--respect-robots` 时也遵守更长的 robots crawl-delay。网络故障、429 和临时服务器错误最多尝试 3 次。较长 Retry-After 会停止该项并标为受限；稍后使用 `--retry`。默认单文件上限 200 MB，可用 `--max-mb` 调整。同一数据目录仅允许一个命令行采集进程写入，Ctrl-C 或崩溃会释放锁。

退出码：0 为本轮操作正常；2 表示队列仍有失败/受限项；1 为目录或运行错误；130 为人工中断。`status` 即使存在受限项也返回 0。有限批次运行结束不代表全站采集完成。

## 测试

在装有 requirements-test.txt 和 requirements-collector.txt 的环境中，从 backend 运行：

```sh
python -m unittest discover -s tests -p 'test_imslp*.py' -v
python -m unittest discover -s tests -v
```

离线测试覆盖解析、缺失 pageid、分页游标、恢复、筛选、受限重试、文件删除后恢复、工作台扫描兼容、robots/重定向、429、错误内容、截断下载、大小限制与进程锁。真实站点 smoke test 仅使用小批次，不将离线模拟下载当作真实站点下载成功。

本次验证结果（2026-09-08）：45 项后端测试通过。默认不强制遵循 robots.txt 后，真实采集队列中的作品 1637322 成功下载 1 份 MP3（20,663,376 字节）和 1 份 PDF（175,392 字节），两者的文件签名和工作台扫描均通过。旧队列的两个 blocked 项已恢复为 downloaded。Windows 脚本尚未在 Windows 实机执行。

下载器已适配 IMSLP 已知的 friendlyredirect JavaScript 中转步骤，并通过页面上同一文件的 “I understand” 提示链接继续正常下载。未执行任意页面 JavaScript；遇到未知中转、登录或验证码仍保留明确错误状态。

扩展验证：非会员的 `sm_dl_wait` 下载页现在会按页面标示等待（当前为 15 秒）后继续下载；未知等待时间仍返回明确错误。新增回归测试检查实际等待调用，避免把订阅介绍页误存成 PDF。

## R2 增量同步

安装 `requirements-r2.txt`，运行 `r2_sync.py --root /absolute/dataset --endpoint https://ACCOUNT_ID.r2.cloudflarestorage.com --bucket music-scores --prefix imslp --watch`。

凭据通过 `R2_ACCESS_KEY_ID` 和 `R2_SECRET_ACCESS_KEY` 进程环境传入；推荐用 secret-input 的 macOS 安全输入窗口，不在命令行或文件中填写密钥。程序读取后移除环境变量，仅由 S3 客户端在内存中持有；重启需重新输入。

文件位于 `imslp/imslp-作品ID/audio|scores/`，每部作品保留 `metadata.json`。网页和目录 API 原始响应放入 `imslp/_source/raw/`；可恢复的 SQLite 备份位于 `imslp/_state/queue.sqlite3`。数据库通过 SQLite backup 生成一致快照，不直接上传正在写入的数据库。采集过程中快照、作品元数据与媒体陆续更新，不构成同一时间点的完整训练版本。

同步只发送完整媒体、作品元数据、原始响应、采集检查点及数据库快照，跳过 `.part`、日志、脚本与凭据。每次上传使用 Content-MD5，并通过 HEAD 核对大小与 SHA-256 元数据；首次描述文件还执行 GET 回读验证。未通过验证不会计为成功。不删除本地或远端文件，不覆盖没有本程序标记的不同内容对象。进程重新启动后会重新核对远端；同一运行期间不重复检查没有变化且已验证的文件。

本地同步进度为 `.imslp/r2/checkpoint.json`，上传记录为 `.imslp/r2/sync.sqlite3`。`watching` 表示上一轮选中的本地文件已同步，后续每 30 秒检查新增/变更；不表示全站采集完成。同步结束或电脑重启后需要重新启动。连续三轮失败会保存 blocked 状态并退出；解决凭据/网络问题后重新输入密钥启动即可继续。
