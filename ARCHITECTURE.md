# 架构笔记

第一条路径：打开书目录和 PDF，改一页 Markdown，另存 reviewed 文件。

## 层

浏览器只负责显示和把文本交给本机服务。`src/app` 做 HTTP、读盘、写另存稿和日志。`src/core` 只做块对齐和 content 替换。

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

级别：ERROR 是这次操作失败。WARN 留给没失败但不正常的情况，这一期还没有。INFO 是打开、保存、请求进出。DEBUG 默认关。

入口生成 12 位 `request_id`。保存时 `app.http`、`core.convert`、`app.store` 都带它。故意失败的地址是 `/api/drill-error`，用来核对编号能串起网页层和规则层。

不记：Markdown 正文、PDF 路径、密钥、家目录绝对路径。写进日志的字符串会去掉换行。

日志写到 `logs/app.jsonl`，同时打到终端。保留到用户自己删这个文件。只有本机用户能看。

## 数据

[D] 是，因为另存稿在用户的书目录里。[P] 否。

原始 OCR 文件只读。另存稿可以再次保存，保存前整份拷到 `_review_backups/<时间>/`。程序没有删除接口。恢复方法：把备份文件拷回同名的 `.reviewed.md` 或 `.reviewed.json`。演练在 `tests/test_store.py` 的第二次保存用例里：备份内容等于上一份另存稿，原始文件字节不变。

没有数据库，所以没有迁移文件。开发和正式数据的差别是：测试用临时目录，真实书目录只在用户自己打开时读写。
