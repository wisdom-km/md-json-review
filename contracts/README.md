# 契约文件

这两份 JSON Schema 从 k12-qbank 的 `backend/catalog/contracts/` 复制。文件有 `$id` 和 `version`。草稿写出 `schema_version`。字段以那边的 ADR 0013、ADR 0014、ADR 0017、ADR 0018 为准。改字段时两份一起改。

本仓库不新增第三方包。`src/core/schema_check.py` 只检查字典。`src/app/contracts.py` 读取这里的文件，写入前校验。失败的错误码是 `CONTRACT`，这一次不写文件。
