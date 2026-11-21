# 计划采集与解读

## 采集 JSON

优先在 CN 上对目标查询执行 `EXPLAIN (VERBOSE, FORMAT JSON)`，获取估算计划。只对已获授权且适合执行的查询使用 `EXPLAIN (ANALYZE, VERBOSE, BUFFERS, FORMAT JSON)`。`ANALYZE` 会实际执行语句，并引入计时开销。脚本不会连接数据库或生成执行命令。

采集时可把一条 EXPLAIN 语句写入 `capture.sql`，再用 `psql -X -A -t -v ON_ERROR_STOP=1 -f capture.sql -o plan.json` 保存单条 JSON 结果。数据库连接参数通过 psql 的常规方式提供。为每个节点和每次比较单独建文件。

如果 CN 只显示 `Remote Fast Query Execution` 等远程节点，先核对节点列表。可以从 `pgxc_node` 查到节点名、主机和端口，在具备权限的测试环境直连目标 DN，对同一条查询采集局部计划。查询应使用带 schema 的表名。OpenTenBase V5.21 的实验环境拒绝在 DN 的 `EXECUTE DIRECT` 中执行 `EXPLAIN`，所以该场景使用直连采集。

## 解读输出

- `analyzed=false` 时只有计划估算。缺失字段应保持未知。实际循环数为 0 时，该节点没有执行。
- `Actual Rows`、`Actual Total Time` 和过滤行数是每循环报告值。检查 `actual_loops`，特别是嵌套循环和并行计划，避免直接把每轮值当作总量。累计缓冲块是另一种口径，父节点会包含子节点的使用量。
- `Index Cond` 是索引访问条件，`Filter` 是在输出行前应用的过滤。位图扫描通常把索引条件与索引名放在 `Bitmap Index Scan` 子节点，堆节点则展示 `Recheck Cond` 和额外过滤。
- 根节点缓冲块和局部路径可用于同节点对照。单次 `execution_ms` 属于该计划的服务端测量，CN 请求延迟需另作重复计时。两个 DN 的独立直连耗时不可相加推算 CN 端到端延迟。
- 返回行数相同可以帮助检查输入是否配对，结果等价仍需对照业务值。扫描方式本身不能决定索引是否更好。用同一查询、参数、节点和数据比较，记录统计信息、缓存及负载差异。

参考 [OpenTenBase 性能优化文档](https://docs.opentenbase.org/guide/09-problem-performance/)和 [PostgreSQL 10 执行计划说明](https://www.postgresql.org/docs/10/using-explain.html)。
