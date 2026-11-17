# 架构笔记

第一条路径：打开书目录和 PDF，改一页 Markdown，另存 reviewed 文件。

## 层

浏览器只负责显示和把文本交给本机服务。`src/app` 做 HTTP、读盘、写另存稿和日志。`src/core` 做块对齐、题目拆分和答案拆分。它不读不写文件。

依赖允许：

| 从 | 到 | 允许 |
| --- | --- | --- |
| 浏览器 | app 的 HTTP | 允许 |
| app | core | 允许 |
| core | app、文件系统、网络 | 禁止 |
| app | 原始 .md / .json 的写入 | 禁止 |

装配只有 `serve.py`：它加载环境、创建日志、创建会话、启动服务。

## 两条方案里选了哪条

JSON 预览可以放在浏览器里再写一遍规则，也可以只放在 core。选了只放在 core。预览和保存走同一个函数，避免两套规则以后对不上。

## 日志

一条日志一个 JSON 对象。字段：`time`、`level`、`event`、`request_id`、`module`，加上 `result` 或 `error`，结束时有 `duration_ms`。

级别：ERROR 是这次操作失败。WARN 留给没失败但不正常的情况，这一期还没有。INFO 是打开、保存、导出、请求进出。选择窗口返回的路径只交给浏览器，不写入日志。DEBUG 默认关。

入口生成 12 位 `request_id`。保存时 `app.http`、`core.convert`、`app.store` 都带它。故意失败的地址是 `/api/drill-error`，用来核对编号能串起网页层和规则层。

不记：Markdown 正文、PDF 路径、密钥、家目录绝对路径。写进日志的字符串会去掉换行。

日志写到 `logs/app.jsonl`，同时打到终端。保留到用户自己删这个文件。只有本机用户能看。

## 数据

[D] 是，因为另存稿在用户的书目录里。[P] 否。

原始 OCR 文件只读。另存稿可以再次保存。手动保存前，把上一份另存稿整份拷到 `_review_backups/<时间>/`。停下来自动保存时不备份，避免每停一次就多一个备份目录。导出写到用户另选的文件夹，文件名是这一页的原名；若目标会盖住原始文件就拒绝。题目页的导出同时带上 `.questions.json`。参考答案页的导出同时带上 `.answers/` 里的答案文件。导出前，目标文件夹里的同名旧文件拷到该文件夹的 `_export_backups/<时间>/`。程序没有删除接口。恢复方法：把备份文件拷回同名的 `.reviewed.md` 或 `.reviewed.json`。答案文件拷回 `{文件名}.answers/`。演练在 `tests/test_store.py` 和 `tests/test_answers.py`：第二次手动保存的备份等于上一份另存稿；连续自动保存不产生备份；导出到原页目录会被拒绝。原始文件字节不变。

题目草稿是同目录的 `{文件名}.questions.json`，契约 `k12-question-draft` 第 1 版。OCR 答案是 `{文件名}.answers/` 里的一份一份 `k12-answer-draft` 第 1 版。页的种类写在 `{文件名}.page-role.txt`，内容只有 `questions` 或 `answers`。答案键的形状是 `题键:ocr:序号`。文件名把冒号换成连字符。来源只有 `ocr`。勾选采用后，`applicable` 为 true，且 `status` 为 `confirmed`。这仍不是题库发布。本工具不调用 k12-qbank，也不连接 PostgreSQL。

没有数据库，所以没有迁移文件。开发和正式数据的差别是：测试用临时目录，真实书目录只在用户自己打开时读写。
