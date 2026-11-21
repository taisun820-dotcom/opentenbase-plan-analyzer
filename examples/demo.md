# OpenTenBase 执行计划分析演示

2026 年 11 月 21 日使用 CLI 回放 OpenTenBase V5.21 的计划。计划来自 1 个 CN、2 个 DN 的 50 万行分片订单表实验。公开样本保留了真实节点、计数和指标，统一了示例 schema 名，并去掉了 `Remote query` 和 `Output` 字段。运行演示只需要 Python 和仓库中的 JSON 文件。

## 比较客户与日期范围查询

同一查询按 `customer_id = 4243` 和 2025 年 6 月的日期范围筛选，CN 返回 5 行。第一组使用 `customer_id` 单列索引，第二组使用 `(customer_id, order_date)` 复合索引。

```sh
python scripts/analyze_plan.py compare --before cn=examples/q2-customer-index-cn.json --before dn0001=examples/q2-customer-index-dn0001.json --before dn0002=examples/q2-customer-index-dn0002.json --after cn=examples/q2-composite-index-cn.json --after dn0001=examples/q2-composite-index-dn0001.json --after dn0002=examples/q2-composite-index-dn0002.json
```

| 节点 | 单列索引根节点 | 复合索引根节点 | 返回行数 | 根节点共享缓冲块命中 |
| --- | --- | --- | --- | --- |
| CN | `Remote Fast Query Execution` | `Remote Fast Query Execution` | 5 → 5 | 远程 DN 明细不可见 |
| dn0001 | `Bitmap Heap Scan` | `Index Scan` | 3 → 3 | 31 → 6 |
| dn0002 | `Bitmap Heap Scan` | `Index Scan` | 2 → 2 | 25 → 5 |

这三个根节点的循环数都是 1。两份 CN 计划都给出了远程节点列表，工具标出 `remote_plan_not_expanded`。在单列索引下，位图索引子节点按客户取候选行，DN 的堆扫描还需用日期过滤，分别去掉 25 和 20 行。在复合索引下，两个条件都进入 `Index Cond`。这些数据说明该样本的局部缓冲块访问减少，端到端延迟需要在 CN 单独测量。

## 检查状态索引场景

```sh
python scripts/analyze_plan.py analyze --plan dn0001=examples/q3-status-index-dn0001.json
```

含 `status = 'paid'` 的汇总查询命中全表约 80%，建状态索引后仍观察到顺序扫描。输出把 `sequential_scan` 定位到 `0.0.0.0`，可在同一路径查看 `Filter`、两次循环和每循环实际行数。该场景的高命中率说明需要结合实际访问量判断索引收益。

## 验证记录

两次演示的命令参数及原始 CLI JSON 输出保存在 [demo-output.json](demo-output.json)。[6 项 CLI 测试](test-results.txt)全部通过，随后批量读取原实验的 36 份计划均成功。演示为已有数据库实测计划的离线回放。
