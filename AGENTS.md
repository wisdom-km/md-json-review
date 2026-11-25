# AGENTS.md

档位：单机工具。见 [docs/adr/0001-utility-tier.md](docs/adr/0001-utility-tier.md)。[D] 是：另存稿写在用户的书目录里。[P] 否：只监听 127.0.0.1。

## 怎么跑、怎么测

- 跑：`py -3 serve.py`，然后打开终端打印的本机地址。默认端口 8765。和 k12-qbank 同时开时用 `py -3 serve.py --port 8766`，或设 `PORT`。`--port` 优先。
- 测：`py -3 scripts/check.py`
- 安装：`pip install git+https://github.com/wisdom-km/md-json-review.git@main`。没有运行时第三方依赖。setuptools 只负责打包。

## 日志

`logs/app-YYYY-MM-DD.jsonl` 和终端。按本机日期一天一个文件。每条有 `request_id`。不记正文、密钥、家目录绝对路径。

## 禁止

- 不覆盖原始 `.md` / `.json`
- 块数对不上不写文件，也不猜
- 不监听 127.0.0.1 以外的地址
- `src/core` 不读不写文件。拆分规则由 `config/split_rules.json` 读入后传入。启动时按 `contracts/split-rules.v1.schema.json` 检查，失败码是 `SPLIT_RULES`，不打开端口
- 不连接 k12-qbank，也不连接 PostgreSQL
- 参考答案只写 `origin` 为 `ocr` 的 `k12-answer-draft`。一份文件一条答案。不写模型答案
- 密钥不进仓库和日志

## 哪份文件能导入

- `.reviewed.json` 是 OCR 页块。它不是题目行，也不是答案行。
- `.questions.json` 是 `k12-question-draft`。`.answers/` 里一份文件是一条 `k12-answer-draft`。
- 字段以 k12-qbank 的 ADR 0013、ADR 0014 为准。契约是 `k12-question-draft` 第 1 版和 `k12-answer-draft` 第 1 版。形状以 `contracts/` 里复制的 JSON Schema 为准，和题库 `backend/catalog/contracts/` 是同一份。草稿写出 `schema_version`。未知版本由题库拒绝。`scripts/check_contracts_in_sync.py` 对题库 main 做 sha256，不一致则退出码不是 0。写入前校验。失败的 `code` 是 `CONTRACT`。题库导入失败的 `code` 是 `not_draft` 或 `answer_conflict`。两边都有 `code`、`message`、`request_id`。不写文件。本工具不调用题库。

## 强制项

单机工具的门禁编号暂时仍按曳光弹：M-01 到 M-09，外加 M-12。[D] 时 M-11。M-10 不适用。project-essentials 没有这一档的单独表格。要改成长期前先问人。
任一 MUST 不满足不得说完成。豁免只认用户原话，记在 `docs/WAIVERS.md`。现在没有豁免。
