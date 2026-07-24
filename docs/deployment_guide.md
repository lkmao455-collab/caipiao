# 部署指南

## 概述

本文档提供彩票号码生成器的部署指南，包括本地部署、Docker 部署和便携版部署。

## 1. 本地部署

### Windows

```bat
:: 1. 检查环境
python deploy.py check

:: 2. 安装依赖
python deploy.py install

:: 3. 运行测试
python deploy.py test

:: 4. 运行应用
python main.py
```

### macOS/Linux

```bash
# 1. 检查环境
python deploy.py check

# 2. 安装依赖
python deploy.py install

# 3. 运行测试
python deploy.py test

# 4. 运行应用
python main.py
```

## 2. Docker 部署

### 构建镜像

```bash
docker build -t caipiao-generator .
```

### 运行容器

```bash
docker run -d \
  --name caipiao \
  -v caipiao_data:/app/.caipiao \
  caipiao-generator
```

### 使用 docker-compose

```bash
# 启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止
docker-compose down
```

## 3. 便携版部署

### 创建便携版

```bash
python deploy.py portable
```

### 使用便携版

1. 将 `portable/` 目录复制到目标机器
2. 双击 `启动彩票生成器.bat` (Windows) 或运行 `./启动彩票生成器.sh` (Linux/macOS)

## 4. 分发包构建

### 构建分发包

```bash
python deploy.py build
```

### 分发包内容

```
dist/
├── main.py
├── requirements.txt
├── README.md
├── CHANGELOG.md
├── caipiao/
└── docs/
```

## 5. 完整部署流程

```bash
# 一键部署
python deploy.py all
```

## 6. 环境要求

### 系统要求

- Windows 10+ / macOS 10.15+ / Ubuntu 20.04+
- Python 3.10+
- 4GB RAM (推荐)
- 1GB 磁盘空间

### 网络要求

- 首次运行需要网络下载开奖数据
- 无网络时使用本地缓存数据
- ML 模型训练需要网络获取最新数据

## 7. 数据目录

### Windows

```
%APPDATA%/CaipiaoApp/
├── draws.json
├── draws_3d.json
├── models/
├── history.json
└── backtests.db
```

### Linux/macOS

```
~/.config/CaipiaoApp/
├── draws.json
├── draws_3d.json
├── models/
├── history.json
└── backtests.db
```

## 8. 故障排除

### 常见问题

1. **依赖安装失败**
   - 检查 Python 版本 (3.10+)
   - 检查网络连接
   - 尝试使用镜像源: `pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

2. **应用启动失败**
   - 检查 PySide6 是否正确安装
   - 检查 OpenGL 支持
   - 查看日志文件

3. **数据更新失败**
   - 检查网络连接
   - 检查防火墙设置
   - 使用本地缓存数据

4. **模型训练失败**
   - 检查历史数据数量 (≥100 期)
   - 检查内存空间
   - 查看训练日志

### 日志位置

- 应用日志: 控制台输出
- 模型训练日志: `models/` 目录下的 `.log` 文件

## 9. 卸载

### Windows

```bat
# 删除安装目录
rmdir /s /q caipiao

# 删除数据目录
rmdir /s /q %APPDATA%\CaipiaoApp
```

### Linux/macOS

```bash
# 删除安装目录
rm -rf caipiao

# 删除数据目录
rm -rf ~/.config/CaipiaoApp
```

### Docker

```bash
# 停止并删除容器
docker-compose down

# 删除镜像
docker rmi caipiao-generator

# 删除数据卷
docker volume rm caipiao_caipiao_data
```
