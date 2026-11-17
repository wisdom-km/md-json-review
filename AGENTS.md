# AGENTS.md

档位：曳光弹。[D] 是：另存稿写在用户的书目录里。[P] 否：只监听 127.0.0.1。

## 怎么跑、怎么测

- 跑：`py -3 serve.py`，然后打开终端打印的本机地址。k12-qbank 的合成站点也占用 8765，不要同时开。
- 测：`py -3 scripts/check.py`

## 日志

`logs/app.jsonl` 和终端。每条有 `request_id`。不记正文、密钥、家目录绝对路径。

## 禁止

- 不覆盖原始 `.md` / `.json`
- 块数对不上不写文件，也不猜
- 不监听 127.0.0.1 以外的地址
- `src/core` 不读不写文件
- 不连接 k12-qbank，也不连接 PostgreSQL
- 参考答案只写 `origin` 为 `ocr` 的 `k12-answer-draft`。一份文件一条答案。不写模型答案
- 密钥不进仓库和日志

## 哪份文件能导入

- `.reviewed.json` 是 OCR 页块。它不是题目行，也不是答案行。
- `.questions.json` 是 `k12-question-draft`。`.answers/` 里一份文件是一条 `k12-answer-draft`。
- 字段以 k12-qbank 的 ADR 0013、ADR 0014 为准。本工具不调用题库。

## 强制项

曳光弹 MUST：M-01 到 M-09，外加 M-12。[D] 时 M-11。M-10 不适用。
任一 MUST 不满足不得说完成。豁免只认用户原话，记在 `docs/WAIVERS.md`。现在没有豁免。
