单机工具。核对 OCR 题页用。拆分、校验和备份已经是这个工具的功能，不是骨架。只在本机使用，不是可以上线的产品。MIT 许可，见 [LICENSE](LICENSE)。仓库：https://github.com/wisdom-km/md-json-review

你在本机网页里打开一本书的 OCR 目录和原始 PDF，一页一页改 Markdown。保存时另存 `.reviewed.md` 和 `.reviewed.json`。原始 `.md` 和 `.json` 不改。

## 这份 JSON

OCR 给每一页一个 JSON。它是一组「块」，不是一道一道拆开的题。每一块有四个字段：

- `index`：块的序号
- `label`：块的类型，例如 `text`
- `content`：这一块的文字。Markdown 改的就是这里
- `bbox_2d`：这一块在页面上的位置。没有位置时是 `null`

你只改 Markdown。程序把改过的文字放进对应块的 `content`，另外三个字段保持 OCR 原来的值，写成 `.reviewed.json`。这一份是改过的页块，字段仍是上面四个。它不是题目行，也不是答案行。这一版不连接 PostgreSQL。

## 启动

在这个目录打开终端：

```powershell
py -3 serve.py
```

题库的集成检查会安装这个仓库：`pip install git+https://github.com/wisdom-km/md-json-review.git@main`。安装配置不声明第三方依赖。setuptools 只在打包时使用，程序不导入它。

浏览器打开终端里打印的地址。默认端口是 8765，只监听本机。k12-qbank 的本机合成站点也使用 8765。两个要同时开时，核对页改端口：`py -3 serve.py --port 8766`，或先设环境变量 `PORT`。`--port` 优先于 `PORT`。端口必须是 1 到 65535 的整数。

点「选择书目录」和「选择 PDF」。两个都是同一种打开窗口，地址栏和底部输入框可以粘贴路径。PDF 窗口只列出 `.pdf`。页码在顶栏，用上一页、下一页或下拉框切换。原页和 Markdown 中间的竖条可以左右拖，用来改原页宽度。松开后记在这台电脑的浏览器里，下次打开还是这个宽度。

Markdown 整页是预览。点哪一行，就只把那一行变成源码，其他行仍是预览。回车在光标处把这一行拆成两行，JSON 预览按新的行再拆。例如把 `1. C 2. C 3. A` 拆成三行后，就是三道选择题的答案。`$...$` 里的分式会画出来。写在美元符号外面的 `\frac{分子}{分母}` 也会画出来。每一行行尾有「删除」和「后面去掉」。删掉的行不会在 JSON 里留下空行。顶栏「撤回」或 Ctrl+Z 可以退回刚才的删除和改字。撤回只记在当前这次打开的页面里。原始 `.md` 和 `.json` 仍然不改，改动只写 `.reviewed.md` 和 `.reviewed.json`。

顶栏可以选择「题目页」或「参考答案页」。题目页按题型标题和题号把这一页拆开。知识导读不建题。选择题选项不够时，这一题标成待确认，其余题照常留下。规则在 `config/split_rules.json`。启动时先按 `contracts/split-rules.v1.schema.json` 检查，通过后才打开端口。失败的 `code` 是 `SPLIT_RULES`，说明里写出字段。只有把 `reject_on_missing_options` 设为 true，才整页不拆。老师可以改题型。确认结果写在同目录的 `.questions.json`。这份文件的契约名是 `k12-question-draft` 第 1 版。每题有 `type` 和 `structure`，并带空的裁图列表，`geometry` 先是空的。以后的新题型映射到已有结构。

参考答案页用同样的题型标题和题号。题型标题的序号可以是中文，也可以是阿拉伯数字，例如 `1. 选择题`、`2. 填空题`、`3. 解答题`，分隔符可以是 `.`、`．` 或 `、`。`1. A` 这种短行仍是一道题的答案，不是题型标题。同一行里递增的多个答案会拆开，例如 `1. A  2. B  3. C`。`3.5` 和 `$1.5 + 2.5$` 不会被拆开。选择题只写选项字母，例如 `1. A` 或 `2. A、C`。填空和解答可以写 `$...$`。`解：` 单独成行时记为步骤。`(1)`、`(2)` 至少出现两次时记为小问。每条答案是一个 `k12-answer-draft` 第 1 版文件，放在 `{文件名}.answers/` 里。文件名把键里的冒号换成连字符，例如 `1:1:ocr:1` 存成 `1-1-ocr-1.json`。勾选「采用这条扫描答案」后，这一条的 `status` 是 `confirmed`，`applicable` 是 true。同一题只采用一条。来源固定是 `ocr`。这个工具不写模型答案。每条答案属于哪一课，写在同级的 `{文件名}.answers-meta.json`，不写进答案草稿，也不放进 `.answers/`。页首没有课时标题时，可以填「本页起始课时」。

字段以 k12-qbank 的 ADR 0013 和 ADR 0014 为准。形状文件在 `contracts/`，从题库的 `backend/catalog/contracts/` 复制，见 ADR 0017 和 ADR 0018。契约文件有 `$id` 和 `version`。写出的草稿带整数 `schema_version`。`scripts/check_contracts_in_sync.py` 读取题库 main 上的两份文件并比较 sha256，不一致时退出码不是 0。CI 会跑这条检查。写入前必须通过这份校验。失败的 `code` 是 `CONTRACT`，`error_code` 与它相同，这一次不写文件。题库导入失败的 `code` 是 `not_draft` 或 `answer_conflict`。两边都有 `code`、`message`、`request_id`。题库用 `import_question_draft` 和 `import_answer_draft` 各解析一次，放进内存，不再转成另一套 JSON。没有 HTTP 导入。这个工具不调用题库，这一步也不写入题库数据库。页的种类记在 `{文件名}.page-role.txt`。换成另一种再保存时，另一种的旧文件先留着。题目导入只读 `.questions.json`。答案导入只读 `.answers/` 里的文件。

## 兼容矩阵

这一版 main 和 [k12-qbank](https://github.com/wisdom-km/k12-qbank) 的 main 使用下面两份契约。带注释的标记 `draft-contract-1` 打在包含这张表的 main 上。更早的提交没有这张表，也不代表这一版契约。

| 契约 | 文件 version | 草稿 schema_version | $id |
| --- | --- | --- | --- |
| k12-question-draft | 1 | 1 | https://github.com/wisdom-km/k12-qbank/contracts/k12-question-draft.v1.schema.json |
| k12-answer-draft | 1 | 1 | https://github.com/wisdom-km/k12-qbank/contracts/k12-answer-draft.v1.schema.json |

本工具是生产者，复制题库的两份 JSON Schema，并写出整数 `schema_version`。题库是消费者，按 `$id` 和 `schema_version` 分发。题库的 job `review-import` 安装本仓库 main，用合成页导入这两份草稿。夹具不是教材页。

## 保存和导出

- 改字后约一秒自动保存，只写书目录里的 `.reviewed.md` 和 `.reviewed.json`。不覆盖 `.questions.json`，也不覆盖 `.answers/` 里的文件，也不覆盖 `{文件名}.answers-meta.json`。原始文件不改。
- 「保存」是手动再存一次。手动保存会把上一份另存稿拷到 `_review_backups`，并覆盖这一页的 `.questions.json` 或 `.answers/`。参考答案页同时覆盖同级的 `{文件名}.answers-meta.json`，覆盖前先备份。自动保存不备份。导出也会写出这两份草稿。
- 「导出」让你另选一个文件夹，把当前页写成同名的 `.md` 和 `.json`。题目页同时写出 `.questions.json`。参考答案页同时写出 `.answers/` 里的答案文件，以及同级的 `{文件名}.answers-meta.json`。不会写回原始文件。导出文件夹里已有的同名文件会先拷进 `_export_backups`。
- 有多块时，块和块之间单独一行写 `---`。段数必须和块数相同。对不上就不保存。

## 测试

```powershell
py -3 scripts/check.py
```

## 日志

`logs/app-YYYY-MM-DD.jsonl`，按本机日期一天一个文件，同时打在终端。每条有 `request_id`。失败时网页上会给出这个编号。日志不记 Markdown 正文，也不记你家目录的绝对路径。

## 数据

这个程序会把你改过的稿写进书目录。原始 OCR 文件只读。备份在书目录的 `_review_backups`。不要把整个磁盘选成书目录。

题库以后按 ADR 0013 和 ADR 0014 建表。这一步不连接 PostgreSQL。`.reviewed.json` 是页块，不是题目行或答案行。
