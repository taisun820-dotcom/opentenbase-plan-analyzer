# OpenTenBase SQL 执行计划分析 Skill

用 Python 标准库读取 OpenTenBase 的 `EXPLAIN (FORMAT JSON)` 结果。可以给协调节点（CN）和多个数据节点（DN）的文件分别加标签，输出扫描路径、索引条件、过滤条件、返回行数、循环数和缓冲块。比较模式按节点标签配对，提供同一查询前后两份计划的证据。脚本离线运行，适合复核慢 SQL 分析，也可以供 Agent 调用。

## 快速开始

需要 Python 3.9 或以上。在仓库根目录运行下列命令。Linux 或 macOS 上可将 `python` 替换成 `python3`。

```sh
python scripts/analyze_plan.py analyze --plan cn=examples/q2-customer-index-cn.json --plan dn0001=examples/q2-customer-index-dn0001.json
python scripts/analyze_plan.py compare --before dn0001=examples/q2-customer-index-dn0001.json --after dn0001=examples/q2-composite-index-dn0001.json
python -m unittest discover -s tests -v
```

每个文件应包含一条 EXPLAIN 结果。`analyze` 可重复指定 `--plan`。`compare` 的两组标签须一致，标签顺序可以不同。使用引号包住含空格的 `LABEL=FILE` 参数。成功时标准输出为 JSON，退出码为 0。文件或参数无效时，标准错误输出原因，退出码为 2。

省略的指标代表原始计划没有提供该指标。`_per_loop` 字段保留每轮值，`root_delta` 为每节点对应根节点的后值减前值。使用根节点缓冲块代表该计划已报告的总访问，避免累加父子节点造成重复计算。`findings` 标注需要结合查询语义核查的位置。

## 从 Agent 调用

将整个 `opentenbase-plan-analyzer` 目录加入支持 Agent Skills 的客户端的 Skill 目录。可以用如下请求触发 `SKILL.md` 中的流程。

> 用 OpenTenBase 执行计划分析 Skill 对比 `examples` 中 Q2 的单列索引和复合索引计划。分别说明两个 DN 的访问路径和缓冲块变化，然后解释 CN 能看到什么。

使用自有计划前，请阅读[计划采集与解读](references/collect-and-interpret.md)。分享计划前检查其中的查询条件、业务对象名和常量。

## 课程演示与验证

[演示记录](examples/demo.md)使用 OpenTenBase V5.21 的 50 万行双 DN 实验计划，展示 CN 的远程计划、两个 DN 的局部路径变化，以及筛选大部分数据时顺序扫描仍然合理的例子。记录提供可直接运行的命令和实际输出文件。[测试用例](tests/test_analyze_plan.py)覆盖 CLI、真实样本、估算计划与错误输入。
