# 前端（Phase 5 垂直切片）

Vue 3 + Vite + TypeScript 的最小前端，演示「登录 → 选彩种/策略 → 生成」端到端链路。

## 开发

```bash
npm install
npm run dev      # 启动 dev server（端口 5173，已配置代理到后端 8000）
```

后端需先启动：

```bash
# 仓库根目录
venv/Scripts/python.exe -m uvicorn web_main:app --reload --port 8000
```

## 构建

```bash
npm run build    # 产物输出到 dist/
npm run preview  # 预览构建产物
```

## 目录

- `src/api/client.ts` — 调用 `/auth/login`、`/profiles`、`/generate` 的轻量封装
- `src/views/Login.vue` `Profiles.vue` `Generate.vue` — 三个页面组件
- `src/App.vue` — 编排（含简单的登录态管理）

> 说明：本目录仅为 Phase 5 垂直切片，完整前端（回测 UI、统计图表、过滤规则编辑器等）见 `docs/phase5_plan.md` 路线图 P5.A。
