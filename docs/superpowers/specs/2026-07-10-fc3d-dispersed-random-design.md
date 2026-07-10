# 福彩3D「分散随机」策略设计文档

## 1. 背景与目标

在福彩3D现有策略中，`random_3d`（完全随机）按每位独立 0–9 生成号码。当用户一次性生成 20 注时，独立随机可能出现号码扎堆、形态集中等现象，视觉上不够"分散"。

本设计新增一个**独立存在、不依赖历史数据**的策略 `FC3DDispersedRandomStrategy`，核心目标：
- 不读取任何历史记录；
- 先生成随机候选池，再通过**局部搜索**优化，使最终 N 注号码在三维数字空间中的 pairwise 欧氏距离最大化；
- 保持随机性（候选池随机、可设 seed），同时获得统计意义上的空间分散性。

## 2. 策略元数据

| 项 | 值 |
|----|----|
| id | `dispersed_random_3d` |
| name | `分散随机` |
| description | 完全随机生成候选号码，并通过局部搜索使输出在三维数字空间中尽量分散。 |
| configurable | True |

## 3. 配置项

| 字段 | 类型 | 默认 | 范围 | 说明 |
|------|------|------|------|------|
| `candidate_multiplier` | int | 50 | 10–200 | 候选池大小 = count × multiplier |
| `max_iterations` | int | 100 | 10–1000 | 局部搜索最大迭代轮数 |
| `dedup` | bool | True | — | 是否按组选（sorted tuple）去重 |
| `seed` | int | None | 0–999999999 | 可选随机种子 |

## 4. 算法设计

### 4.1 距离定义

将一注 3D 号码 `(a, b, c)` 视为三维坐标，两注之间的差异用欧氏距离：

```
d((a1,b1,c1), (a2,b2,c2)) = sqrt((a1-a2)^2 + (b1-b2)^2 + (c1-c2)^2)
```

该距离兼顾了位置差异与数字差异。

### 4.2 整体流程

1. **生成候选池**：生成 `count × candidate_multiplier` 个独立随机 3D 号码；
2. **去重（可选）**：若 `dedup=True`，按 `tuple(sorted(nums))` 去重，保留直选形式；
3. **初始化**：使用 Greedy Farthest Point 从候选池中选出 `count` 个初始号码；
4. **局部搜索**：
   - 维护已选集合 S 的距离矩阵；
   - 每轮遍历所有 `(s in S, c in C\S)` 尝试单次交换；
   - 若交换后 `min_pairwise_distance(S)` 提升，则接受该交换；
   - 一轮结束后若没有任何交换被接受，或达到 `max_iterations`，则停止；
5. **返回**：将 S 中的号码封装为 `Ticket` 列表。

### 4.3 局部搜索实现要点

- 距离矩阵缓存：避免每轮重复计算；
- 增量更新：交换一个号码时，只更新该号码与其他已选号码的距离；
- 停止条件：无改进或达到最大迭代次数；
- 候选池不足：若去重后候选数量 < count，抛出 `ValueError` 提示用户降低数量或关闭去重。

## 5. 文件结构

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `caipiao/core/strategies/lotteries/fc3d/dispersed_random.py` | 新建 | 策略主实现，完全独立 |
| `caipiao/core/strategies/lotteries/fc3d/__init__.py` | 修改 | 导出 `FC3DDispersedRandomStrategy` |
| `caipiao/core/strategies/registry.py` | 修改 | 将策略加入 `STRATEGY_REGISTRY["3d"]` |
| `tests/test_fc3d_dispersed_random.py` | 新建 | 单元测试 |

## 6. UI 集成

策略注册到 `STRATEGY_REGISTRY["3d"]` 后，`caipiao/ui/lottery_context.py` 中通过 `build_strategies(self.profile)` 自动发现，`UI` 下拉框会自动出现「分散随机」选项，无需额外修改 UI 代码。

## 7. 测试计划

- `test_generate_without_history`：不传 `history` 也能生成指定数量；
- `test_dedup_limits_to_220`：`dedup=True` 时请求超过 220 注抛异常；
- `test_dispersion_positive`：生成的号码间最小 pairwise 距离 > 0；
- `test_seed_deterministic`：固定 seed 时结果可复现；
- `test_respects_dedup_setting`：`dedup=True` 时无 sorted-tuple 重复，`dedup=False` 允许直选重复。

## 8. 约束与假设

- 不依赖任何历史数据，`history` 字段可选；
- 局部搜索的候选池从均匀随机采样得到，因此结果仍具有随机性，只是比纯随机更分散；
- 默认候选池大小 `count × 50`，对 `count=20` 即 1000 个候选，计算量在可接受范围内。

## 9. 后续可扩展

- 支持多种距离度量（Hamming、Jaccard、自定义加权距离）；
- 支持多轮 restart 选择最优解；
- 支持形态（豹子/组三/组六）层面的分散约束。
