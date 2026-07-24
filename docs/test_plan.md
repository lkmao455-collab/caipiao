# Test Plan

## Unit Tests

### Core Layer
- `test_ticket.py`: Ticket 构造、校验、序列化、双色球兼容
- `test_profile.py`: LotteryProfile 查询、NumberGroup 校验
- `test_engine.py`: 策略注册/调用/过滤

### Data Layer
- `test_models.py`: DrawRecord 构造、序列化
- `test_repository.py`: 加载、保存、去重、查询
- `test_analyzer.py`: 频率、热冷、遗漏、奇偶比

### ML Layer
- `test_features.py`: 特征工程正确性
- `test_model_store.py`: 模型缓存、指纹校验
- `test_lottery_ml_backends.py`: 多后端模型一致性

### Persistence Layer
- `test_settings.py`: 设置读写
- `test_history.py`: 历史记录 CRUD
- `test_parameter_group.py`: 参数组存储

### UI Layer
- `test_main_window_toolbar.py`: 工具栏按钮
- `test_markdown_view.py`: Markdown 渲染
- `test_parameter_group_dialog.py`: 参数组对话框

## Integration Tests

### End-to-End Generation Flow
1. 构造 DrawRecord 列表
2. 注册策略到 Engine
3. 调用 generate()
4. 验证 Ticket 数量和格式

### Data Update Flow
1. Mock 网络响应
2. 调用 Fetcher.fetch_all()
3. 调用 Repository.update()
4. 验证本地存储

### ML Training Flow
1. 构造训练数据
2. 调用 MLPredictor.train()
3. 调用 MLPredictor.predict()
4. 验证概率分布合理

## Edge Cases

- 空数据: records = []
- 最小数据: records = [1 record]
- 数据不足: records < 100 (ML 训练)
- 网络超时: timeout 模拟
- 重复数据: Dedup 逻辑
- 跨年期号: 年份变更时的期号生成

## Running Tests

```bash
# 全部测试
python -m pytest tests/ -v

# 指定模块
python -m pytest tests/test_model_store.py -v

# 带覆盖率
python -m pytest tests/ --cov=caipiao --cov-report=html
```
