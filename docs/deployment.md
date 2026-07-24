# Deployment

## Prerequisites

- Windows 10+ / macOS / Linux
- Python 3.12+
- pip

## Quick Start (Windows)

```bat
:: 1. 创建虚拟环境
create_venv.bat

:: 2. 运行
run.bat
```

## Manual Setup

```bash
# 1. 创建虚拟环境
python -m venv venv

# 2. 激活
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 运行
python main.py
```

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| PySide6 | >=6.4.0 | Qt6 GUI |
| Pillow | >=9.0.0 | 图标生成 |
| requests | >=2.28.0 | HTTP 请求 |
| beautifulsoup4 | >=4.11.0 | HTML 解析 |
| xgboost | >=2.0.0 | XGBoost 模型 |
| lightgbm | >=4.0.0 | LightGBM 模型 |
| catboost | >=1.2.0 | CatBoost 模型 |
| numpy | >=1.24.0 | 数值计算 |
| scikit-learn | >=1.3.0 | ML 工具 |
| matplotlib | >=3.7.0 | 图表 |
| markdown | >=3.4.0 | MD 渲染 |
| Pygments | >=2.15.0 | 语法高亮 |

## Data Directory

应用数据存储在 `%APPDATA%/CaipiaoApp/` (Windows) 或 `~/.config/CaipiaoApp/` (Linux):
- `draws.json` — 双色球开奖数据
- `draws_3d.json` — 福彩3D 数据
- `models/` — 训练好的 ML 模型
- `history.json` — 生成历史
- `backtests.db` — 回测结果

## First Run

1. 启动应用
2. 切换到「开奖数据」标签页
3. 点击「更新开奖数据」下载历史数据
4. 点击「训练模型」训练 ML 模型（可选）
5. 切换到「生成号码」标签页开始使用

## Notes

- 无网络时使用本地缓存数据，功能完整
- 首次使用 ML 策略时会自动训练模型
- 模型训练需要 ≥100 期历史数据
