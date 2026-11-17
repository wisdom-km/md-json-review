# 拆分规则

`split_rules.json` 是题目页和参考答案页共用的拆分规则。`src/app/split_rules.py` 读这个文件，编译后再交给 `src/core`。core 不读文件。不新增第三方包，所以这里用 JSON，不用 YAML。

| 字段 | 含义 |
| --- | --- |
| `type_patterns` | 题型标题。每条有 `pattern` 和 `type`。先匹配到的生效。`type` 只能是 `single_choice`、`multiple_choice`、`choice`、`fill_blank`、`solution`。`choice` 表示标题只写了「选择题」，单选还是多选留到后面判断。现有式子允许字和字之间有空格，用来接 OCR 把「单选题」拆开的情况。 |
| `option_pattern` | 选项标记。必须有一个捕获组，组里是选项字母。 |
| `option_keys` | 允许的选项字母。参考答案页只认这些字母。 |
| `option_required_types` | 这些题型必须有足够的选项。 |
| `subquestion_markers` | 小问标记。每条正则要有一个捕获组，组里是小问序号。 |
| `reject_on_missing_options` | true 时，选择题选项不够就整页不拆。false 时，这一题标 `needs_confirm`，其余题照常留下。 |
| `needs_confirm_threshold` | 至少几个选项才算齐。不够时不把半个选项从题干里剥走。 |

块对齐仍看独占一行的 `---`，不在这个文件里。
