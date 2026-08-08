# 移动端应用说明

## PWA 支持

本应用支持 PWA（渐进式 Web 应用），可以在移动设备上获得原生应用般的体验。

### 安装到主屏幕

#### iOS (Safari)
1. 打开 Safari 浏览器访问应用
2. 点击底部分享按钮
3. 选择「添加到主屏幕」
4. 确认添加

#### Android (Chrome)
1. 打开 Chrome 浏览器访问应用
2. 点击右上角菜单按钮
3. 选择「添加到主屏幕」或「安装应用」
4. 确认安装

### 功能特性

- **离线访问**: 静态资源可离线使用
- **推送通知**: 支持开奖提醒（需用户授权）
- **全屏体验**: 安装后可全屏使用
- **快速启动**: 从主屏幕快速启动

## 原生应用开发

### 技术方案

如需开发原生 iOS/Android 应用，推荐以下方案：

#### 方案 1: Capacitor (推荐)
- 基于现有 Vue 代码打包原生应用
- 支持所有原生 API 访问
- 跨平台统一代码库

```bash
# 安装 Capacitor
npm install @capacitor/core @capacitor/cli

# 初始化
npx cap init lottery-app com.lottery.app

# 添加平台
npx cap add ios
npx cap add android

# 构建并同步
npm run build
npx cap sync
```

#### 方案 2: React Native
- 使用 React Native 重写 UI
- 原生性能更好
- 需要重写前端代码

#### 方案 3: Flutter
- 使用 Dart 语言
- 高性能渲染
- 需要完全重写

### 原生功能集成

1. **推送通知**: 使用 Firebase Cloud Messaging (FCM)
2. **本地存储**: 使用 SQLite 或 AsyncStorage
3. **生物认证**: 使用 Touch ID / Face ID
4. **相机扫描**: 用于扫描二维码分享

## 测试清单

### PWA 测试
- [ ] 可安装到主屏幕
- [ ] 离线模式可访问
- [ ] 推送通知正常
- [ ] 全屏显示正常
- [ ] 启动画面显示

### 原生应用测试
- [ ] iOS 编译通过
- [ ] Android 编译通过
- [ ] 推送通知集成
- [ ] 本地存储正常
- [ ] 性能达标

## 部署

### PWA 部署
1. 确保 HTTPS 配置
2. 配置 Service Worker 缓存策略
3. 验证 manifest.json 配置

### 原生应用部署
1. iOS: 通过 App Store Connect 提交
2. Android: 通过 Google Play Console 提交
3. 国内安卓市场: 各市场单独提交
