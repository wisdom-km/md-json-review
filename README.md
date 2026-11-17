曳光弹。核对 OCR 题页用，留下当骨架，不是可以上线的产品。MIT 许可，见 [LICENSE](LICENSE)。仓库：https://github.com/wisdom-km/md-json-review

你在本机网页里打开一本书的 OCR 目录和原始 PDF，一页一页改 Markdown。保存时另存 `.reviewed.md` 和 `.reviewed.json`。原始 `.md` 和 `.json` 不改。

## 这份 JSON

OCR 给每一页一个 JSON。它是一组「块」，不是一道一道拆开的题。每一块有四个字段：

- `index`：块的序号
- `label`：块的类型，例如 `text`
- `content`：这一块的文字。Markdown 改的就是这里
- `bbox_2d`：这一块在页面上的位置。没有位置时是 `null`

你只改 Markdown。程序把改过的文字放进对应块的 `content`，另外三个字段保持 OCR 原来的值，写成 `.reviewed.json`。这一份就是准备放进数据库的页 JSON。这一版先写成文件，还没有连接 PostgreSQL。

## 启动

在这个目录打开终端：

```powershell
py -3 serve.py
```

浏览器打开终端里打印的地址，默认是 http://127.0.0.1:8765 。只监听本机。

书目录填 OCR 输出文件夹，例如里面有 `page_0001` 的那一层。PDF 填原始文件的完整路径。

## 保存规则

- 这一页的原 JSON 只有一块：整页 Markdown 写入那一块的 `content`。`index`、`label`、`bbox_2d` 保持原样。
- 有多块：块和块之间单独一行写 `---`。段数必须和块数相同。对不上就停，不写文件。
- 再保存时，上一份另存稿先拷到该书目录下的 `_review_backups`。

## 测试

```powershell
py -3 scripts/check.py
```

## 日志

`logs/app.jsonl`，同时打在终端。每条有 `request_id`。失败时网页上会给出这个编号。日志不记 Markdown 正文，也不记你家目录的绝对路径。

## 数据

这个程序会把你改过的稿写进书目录。原始 OCR 文件只读。备份在书目录的 `_review_backups`。不要把整个磁盘选成书目录。

题库 PostgreSQL 里现有的题目记录是题干、答案这些字段。这一页的块 JSON 还没有写入那张表。
