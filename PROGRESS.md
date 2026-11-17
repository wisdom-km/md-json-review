# 进度

做到：本机网页能打开书目录和 PDF，改 Markdown，另存 reviewed 文件。块数不对会停。原始文件不改。手动保存会备份上一份另存稿。自动保存不每次备份。题目页写 `k12-question-draft`。参考答案页按同样的题号写成一份一份的 `k12-answer-draft`。2026-11-17，`py -3 -m unittest discover -s tests` 为 27 个测试通过。

下一步：下一次公开用分支和 PR。连上 PostgreSQL 时由题库按 ADR 0014 建答案表，不在这个工具里建，也不在这里连接数据库。

卡住：无。公共仓库和 CI 已跑通。当前 main 是 `5d41fcd`。https://github.com/wisdom-km/md-json-review/actions/runs/44077771910
