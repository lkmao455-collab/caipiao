"""pytest 全局配置：强制使用 offscreen 平台，避免无显示器环境下弹窗阻塞."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
