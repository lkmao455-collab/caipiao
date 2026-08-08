"""pytest 全局配置：强制使用 offscreen 平台，避免无显示器环境下弹窗阻塞."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# 测试环境调高限流阈值，避免大量注册/登录/默认路由请求触发 429。
# 限流功能本身仍开启（专门测限流的用例会临时压低阈值验证 429）。
os.environ["CAIPIAO_WEB_RATE_LIMIT"] = "100000/minute"
os.environ["CAIPIAO_WEB_AUTH_RATE_LIMIT"] = "100000/minute"
