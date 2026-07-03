# LightGBM 入门教程：用双色球数据学习梯度提升

> 本文档与《XGBoost 入门教程》配套，重点讲解 LightGBM 与 XGBoost 的异同。同样要强调：**这个模型不能预测彩票开奖结果**，仅作为学习机器学习流程的教学示例。

---

## 目录

1. [什么是 LightGBM？](#1-什么是-lightgbm)
2. [LightGBM 与 XGBoost 的区别](#2-lightgbm-与-xgboost-的区别)
3. [本项目的问题定义](#3-本项目的问题定义)
4. [训练流程](#4-训练流程)
5. [模型参数白话解释](#5-模型参数白话解释)
6. [预测与号码生成](#6-预测与号码生成)
7. [常见误区](#7-常见误区)
8. [扩展学习](#8-扩展学习)

---

## 1. 什么是 LightGBM？

LightGBM = **Light Gradient Boosting Machine**（轻量级梯度提升机）。

它和 XGBoost 一样属于梯度提升树（GBDT）家族，核心思想都是：

> 训练多棵决策树，把它们的结果加起来做预测。

LightGBM 由微软开源，主要优势是：

- **训练速度快**：采用基于直方图（Histogram）的决策树算法，内存占用更低。
- **支持大规模数据**：在海量样本上表现优异。
- **对类别特征更友好**：虽然本项目特征主要是数值型，但这一点在实际业务中很有用。

---

## 2. LightGBM 与 XGBoost 的区别

| 特性 | XGBoost | LightGBM |
|------|---------|----------|
| 分裂策略 | Level-wise（按层生长） | Leaf-wise（按叶子生长） |
| 主要优化 | 预排序 + 二阶导数 | 直方图算法 |
| 训练速度 | 快 | 通常更快 |
| 内存占用 | 较大 | 较小 |
| 默认参数 | 相对稳定 | 对 `num_leaves` 更敏感 |

### 2.1 Level-wise vs Leaf-wise

- **XGBoost 的 Level-wise**：每次分裂时，先对同一层的所有叶子都尝试分裂，选出最优的一个。
- **LightGBM 的 Leaf-wise**：每次只选择当前损失下降最大的一个叶子进行分裂。

Leaf-wise 的好处是模型精度通常更高，但容易过拟合，所以需要控制叶子数量。

### 2.2 为什么在本项目中看起来差不多？

因为双色球历史数据量不大（几千期），特征维度也不高，所以 XGBoost 和 LightGBM 的差距不明显。它们更多是**让你体验不同算法**，而不是真正帮你找到中奖规律。

---

## 3. 本项目的问题定义

与 XGBoost 策略完全一致：

> 给定最近 `lookback` 期的开奖数据，预测下一期每个红球和蓝球是否会出现。

因此同样是：

- **33 个红球二分类器**
- **1 个蓝球多输出分类器**（内部包含 16 个二分类器）

训练完成后，输出每个号码的出现概率，再按概率加权采样生成号码。

---

## 4. 训练流程

```
1. 加载历史开奖数据
2. 构建特征矩阵 X 和标签 y
3. 为每个号码训练一个 LightGBM 二分类器
4. 保存训练好的模型
5. 用最新一期数据预测下一期概率
```

代码逻辑（简化版）：

```python
from lightgbm import LGBMClassifier

# 33 个红球分类器
for i in range(33):
    model = LGBMClassifier(n_estimators=100, max_depth=4, num_leaves=15)
    model.fit(X, y_red[:, i])
    red_models.append(model)

# 蓝球多输出分类器
blue_clf = LGBMClassifier(n_estimators=100, max_depth=4, num_leaves=15)
blue_model = MultiOutputClassifier(blue_clf)
blue_model.fit(X, y_blue)
```

---

## 5. 模型参数白话解释

本项目的 LightGBM 参数如下：

```python
LGBMClassifier(
    n_estimators=100,   # 训练 100 棵树
    max_depth=4,        # 每棵树最多 4 层
    num_leaves=15,      # 每棵树最多 15 个叶子
    learning_rate=0.1,  # 学习率
    subsample=0.8,      # 每次随机用 80% 的样本
    subsample_freq=1,   # 每轮都进行子采样
    colsample_bytree=0.8,  # 每次随机用 80% 的特征
    objective="binary",    # 二分类
    random_state=42,
    verbose=-1,
)
```

### 5.1 num_leaves = 15

这是 LightGBM 最重要的参数之一。因为 LightGBM 按 Leaf-wise 生长，`num_leaves` 控制模型复杂度。

- 值越大，模型越复杂，越容易过拟合。
- 通常 `num_leaves = 2^max_depth - 1` 附近，这里设为 15，对应 `max_depth=4` 的满二叉树叶子数。

### 5.2 subsample_freq = 1

每轮迭代都进行样本子采样。配合 `subsample=0.8`，相当于每棵树用 80% 的随机样本训练。

### 5.3 objective = "binary"

二分类目标函数，输出每个号码是否会出现的概率。

---

## 6. 预测与号码生成

训练完成后，对每个号码调用 `predict_proba()`，得到出现概率：

```python
red_proba = [model.predict_proba(latest_X)[0, 1] for model in red_models]
```

然后与 XGBoost 策略一样，使用多样性增强（`diversity_boost`）的概率加权采样生成多注号码。

你可以在软件的「工具 → 历史回测」中对比 XGBoost 和 LightGBM 在相同日期、相同参数下的表现，通常会发现：

- 两者都没有真正的预测能力；
- 差异主要来自采样随机性和模型对历史噪声的拟合方式不同。

---

## 7. 常见误区

### ❌ 误区 1：LightGBM 比 XGBoost 更能预测彩票

**真相**：两者都是梯度提升树，本质上没有区别。彩票开奖是独立随机事件，再好的算法也无法预测未来。

### ❌ 误区 2：训练速度快等于预测准确

**真相**：训练速度快只是工程优势，不代表模型学到了真实规律。对随机数据，再快的训练也只是在拟合噪声。

### ❌ 误区 3：调整 `num_leaves` 能找到中奖模式

**真相**：`num_leaves` 只能控制模型复杂度。在随机数据上，调参不会让模型获得超能力。

---

## 8. 扩展学习

- [LightGBM 官方文档](https://lightgbm.readthedocs.io/)
- [XGBoost vs LightGBM 对比](https://neptune.ai/blog/xgboost-vs-lightgbm)
- 《统计学习方法》李航（第 8 章 提升方法）

---

## 总结

LightGBM 是 XGBoost 之后另一种流行的梯度提升实现：

- 训练更快、内存更省；
- 采用 Leaf-wise 树生长策略；
- 在本项目中与 XGBoost 一样，仅用于学习机器学习流程。

建议你在软件里分别用 XGBoost、LightGBM、CatBoost 做批量回测，比较它们的盈亏曲线——这是理解“模型无法预测随机事件”的最好方式。
