# PDF 识谱与校对

在工作台中选择作品、点击 PDF 文件名，在谱面下方选择起止页码并点击“开始识谱”。页码以原始 PDF 为准，请先预览并跳过封面或空白页。识谱在后台串行执行，页面可继续操作。单批1–30页，单任务超时30分钟；较长总谱可分段识别，分段结果不会自动合并。

当前接入 Audiveris 5.10.2。官方 macOS ARM64 安装包已下载到本机 `backend/data/tools`，包含 Java 运行时。其他设备请安装对应平台的 [Audiveris 官方发行版](https://github.com/Audiveris/audiveris/releases/tag/5.10.2)，并将 `AUDIVERIS_BIN` 配置为可执行文件的完整路径。启动后台服务时该环境变量需设置在服务配置中。首次文字识别需在 Audiveris 配置对应的 Tesseract 语言数据。本机已补充英文 `eng.traineddata`。

处理使用 [Audiveris 批处理接口](https://audiveris.github.io/audiveris/_pages/guides/advanced/cli/) 导出 MXL（压缩 MusicXML）和 OMR 工程。即使程序退出码为0，也必须存在可解析、含有有音高音符的 MusicXML 才显示“待人工校对”；程序错误、空白页或无有效结果显示失败。

## 校对与保存

- 下载 MXL 可用支持 MusicXML 的打谱软件检查和修改。
- 点击“打开 Audiveris 校对”会打开本机识谱工程；修改后从 Audiveris 导出 MusicXML/MXL。
- 在网页选择导出的校对稿，确认实际完成音符、节奏、声部核对后，勾选确认框并保存。
- 未勾选也可以保存草稿，状态继续保持待校对。每次导入生成新的文件，不覆盖原 PDF 或旧稿。
- 当前不是浏览器内的可视化打谱编辑器，校对在 Audiveris 或其他打谱软件完成。

原始 PDF 保留不动。衍生文件和状态保存在 `backend/data/omr/任务ID/`，记录原路径、来源SHA-256、原始PDF页码范围、识谱输出、校对状态。重新选择同一PDF可查看历史任务。服务重启时未完成任务会显示中断，需要重新提交。

识谱结果和人工校对稿均不自动标记为训练就绪，也不自动并入原始文件清单；音频版本核对、音符时间对齐、页段合并仍待下一阶段处理。界面显示的音符和小节数量是识别输出统计，不是准确率。

## 验证

120项后端测试通过，覆盖输入路径、页码范围、无音符输出拒绝、校对文件校验、历史任务和原始文件保护。本机真实样本 `imslp-929871/scores/IMSLP577618.pdf` 第3页成功导出MusicXML；第2页空白页显示识别失败，未产生伪成功。自动导出结果尚未经人工校对。

Audiveris 为 AGPL-3.0 软件，详情参阅 [官方仓库及许可证](https://github.com/Audiveris/audiveris)。安装程序、引擎文件及下载数据均未纳入Git。
