# CatBoost 入门教程：用双色球数据学习梯度提升

> 本文档与《XGBoost 入门教程》《LightGBM 入门教程》配套，讲解 CatBoost 的特点与使用。再次强调：**这个模型不能预测彩票开奖结果**，仅作为学习机器学习流程的教学示例。

---

## 目录

1. [什么是 CatBoost？](#1-什么是-catboost)
2. [CatBoost 与 XGBoost/LightGBM 的区别](#2-catboost-与-xgboostlightgbm-的区别)
3. [本项目的问题定义](#3-本项目的问题定义)
4. [训练流程](#4-训练流程)
5. [模型参数白话解释](#5-模型参数白话解释)
6. [预测与号码生成](#6-预测与号码生成)
7. [常见误区](#7-常见误区)
8. [扩展学习](#8-扩展学习)

---

## 1. 什么是 CatBoost？

CatBoost = **Categorical Boosting**（类别特征提升）。

它是由 Yandex 开源的梯度提升库，主要特点是：

- **对类别特征处理特别好**：自动做目标编码（Ordered Target Encoding），减少过拟合。
- **默认参数表现优秀**：通常不需要大量调参就能拿到不错的效果。
- **训练稳定**：对过拟合有较好的内置防护。

虽然本项目中的双色球特征主要是数值型（频率、遗漏值、奇偶比等），但 CatBoost 仍然是一个很好的学习对象，因为它展示了不同梯度提升实现之间的差异。

---

## 2. CatBoost 与 XGBoost/LightGBM 的区别

| 特性 | XGBoost | LightGBM | CatBoost |
|------|---------|----------|----------|
| 开发者 | DMLC | 微软 | Yandex |
| 分裂策略 | Level-wise | Leaf-wise | Oblivious Trees（对称树） |
| 类别特征 | 需手动编码 | 需手动编码 | 原生支持 |
| 默认参数 | 一般 | 对 num_leaves 敏感 | 通常最稳定 |
| 训练速度 | 快 | 很快 | 较慢但稳定 |

### 2.1 Oblivious Trees 是什么？

CatBoost 默认使用**对称树（Oblivious Trees）**：

- 同一层的所有节点使用相同的分裂条件。
- 这使得模型更不容易过拟合，预测速度也更快。
- 代价是单棵树的表达能力稍弱，但 Boosting 会通过多棵树弥补。

### 2.2 为什么在本项目中用 CatBoost？

主要是为了让你体验三种主流梯度提升库：

- **XGBoost**：经典、文档丰富；
- **LightGBM**：速度快、Leaf-wise；
- **CatBoost**：默认参数稳定、对类别特征友好。

它们在本项目中的表现不会有本质差异，因为彩票开奖本质上是随机的。

---

## 3. 本项目的问题定义

与 XGBoost、LightGBM 策略完全一致：

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
3. 为每个号码训练一个 CatBoost 二分类器
4. 保存训练好的模型
5. 用最新一期数据预测下一期概率
```

代码逻辑（简化版）：

```python
from catboost import CatBoostClassifier

# 33 个红球分类器
for i in range(33):
    model = CatBoostClassifier(iterations=100, depth=4, learning_rate=0.1, verbose=False)
    model.fit(X, y_red[:, i])
    red_models.append(model)

# 蓝球多输出分类器
blue_clf = CatBoostClassifier(iterations=100, depth=4, learning_rate=0.1, verbose=False)
blue_model = MultiOutputClassifier(blue_clf)
blue_model.fit(X, y_blue)
```

---

## 5. 模型参数白话解释

本项目的 CatBoost 参数如下：

```python
CatBoostClassifier(
    iterations=100,      # 训练 100 轮（类似 n_estimators）
    depth=4,             # 每棵树深度为 4
    learning_rate=0.1,   # 学习率
    loss_function="Logloss",  # 二分类对数损失
    random_seed=42,      # 随机种子
    verbose=False,       # 不输出训练日志
    thread_count=1,      # 单线程，避免界面卡顿
)
```

### 5.1 iterations = 100

类似 XGBoost/LightGBM 的 `n_estimators`，表示训练多少棵树（或多少轮提升）。

### 5.2 depth = 4

树的深度。CatBoost 默认使用对称树，`depth=4` 表示每棵树有 4 层分裂。

### 5.3 loss_function = "Logloss"

二分类目标函数。CatBoost 也支持 `CrossEntropy` 等，但 `Logloss` 是标准选择。

### 5.4 scale_pos_weight

与 XGBoost/LightGBM 一样，本项目对每个号码使用 `scale_pos_weight` 处理类别不平衡：

```python
pos = y_i.sum()
neg = len(y_i) - pos
scale = neg / max(pos, 1)
model.set_params(scale_pos_weight=min(scale, 10.0))
```

---

## 6. 预测与号码生成

训练完成后，调用 `predict_proba()` 获取概率：

```python
red_proba = [model.predict_proba(latest_X)[0, 1] for model in red_models]
```

然后与 XGBoost、LightGBM 策略一样，使用多样性增强（`diversity_boost`）的概率加权采样生成多注号码。

你可以在软件的「工具 → 历史回测」中对比三种 ML 策略在相同参数下的表现。通常会发现：

- 三者的盈亏曲线都很接近随机波动；
- 短期差异主要来自采样随机性和模型对历史噪声的拟合方式。

---

## 7. 常见误区

### ❌ 误区 1：CatBoost 的类别特征优势能帮我中奖

**真相**：本项目特征都是数值型（频率、遗漏值、统计量），没有类别特征。即使有，类别特征处理也无法预测随机事件。

### ❌ 误区 2：CatBoost 默认参数好，所以它更准

**真相**：默认参数稳定意味着它更容易上手，但不代表它能从随机数据中学到真实规律。

### ❌ 误区 3：三种模型一起用可以提高中奖率

**真相**：多种模型组合可以降低方差，但无法把随机信号变成可预测信号。对彩票这种独立随机事件， ensemble 也没用。

---

## 8. 扩展学习

- [CatBoost 官方文档](https://catboost.ai/en/docs/)
- [CatBoost: unbiased boosting with categorical features](https://arxiv.org/abs/1706.09516)
- 《统计学习方法》李航（第 8 章 提升方法）

---

## 总结

CatBoost 是第三种主流梯度提升实现：

- 默认参数稳定，适合快速上手；
- 对类别特征有原生支持；
- 使用对称树减少过拟合；
- 在本项目中与 XGBoost、LightGBM 一样，仅用于学习机器学习流程。

建议你分别运行三种 ML 策略的批量回测，把它们的汇总结果保存到「回测记录」里对比——这是理解“机器学习无法预测彩票”的最佳实践。
