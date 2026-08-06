# P5.D: 前端多阶段镜像（Node 构建 -> nginx 静态服务）
#
# 构建：  docker build -f frontend/Dockerfile -t caipiao-frontend ./frontend
# 说明：  第二阶段 nginx 同时托管 SPA 静态资源，并把 API/WebSocket 请求
#         反向代理到后端服务（compose 中名为 web，端口 8000）。
#         SPA 使用相对 BASE（import.meta.env.VITE_API_BASE 留空），
#         因此所有 /auth /profiles /generate ... 均经同源 nginx 转发。

# --------------------------- build 阶段 --------------------------- #
FROM node:20-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# --------------------------- runtime 阶段 ------------------------- #
FROM nginx:1.27-alpine AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
