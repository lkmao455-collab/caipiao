<script setup lang="ts">
import { ref, onMounted } from "vue";
import {
  getPlugins,
  enablePlugin,
  disablePlugin,
  installPlugin,
  uninstallPlugin,
  type PluginMeta,
} from "../api/client";

const props = defineProps<{ token: string }>();

const plugins = ref<PluginMeta[]>([]);
const loading = ref(true);
const error = ref("");
const installDir = ref("");
const installing = ref(false);

async function loadPlugins() {
  loading.value = true;
  error.value = "";
  try {
    plugins.value = await getPlugins(props.token);
  } catch (e: any) {
    error.value = e.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

async function togglePlugin(plugin: PluginMeta) {
  try {
    if (plugin.enabled) {
      await disablePlugin(props.token, plugin.id);
    } else {
      await enablePlugin(props.token, plugin.id);
    }
    await loadPlugins();
  } catch (e: any) {
    error.value = e.message || "操作失败";
  }
}

async function handleInstall() {
  if (!installDir.value.trim()) return;
  installing.value = true;
  error.value = "";
  try {
    await installPlugin(props.token, installDir.value);
    installDir.value = "";
    await loadPlugins();
  } catch (e: any) {
    error.value = e.message || "安装失败";
  } finally {
    installing.value = false;
  }
}

async function handleUninstall(pluginId: string) {
  if (!confirm(`确定要卸载插件 ${pluginId} 吗？`)) return;
  try {
    await uninstallPlugin(props.token, pluginId);
    await loadPlugins();
  } catch (e: any) {
    error.value = e.message || "卸载失败";
  }
}

onMounted(loadPlugins);
</script>

<template>
  <div class="plugins-view">
    <h2>插件管理</h2>

    <div v-if="error" class="error">{{ error }}</div>

    <!-- 安装插件 -->
    <div class="install-section">
      <h3>安装插件</h3>
      <div class="install-form">
        <input
          v-model="installDir"
          placeholder="输入插件目录路径..."
          :disabled="installing"
        />
        <button @click="handleInstall" :disabled="installing || !installDir.trim()">
          {{ installing ? "安装中..." : "安装" }}
        </button>
      </div>
    </div>

    <!-- 插件列表 -->
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="plugins.length === 0" class="empty">暂无插件</div>
    <div v-else class="plugin-list">
      <div
        v-for="plugin in plugins"
        :key="plugin.id"
        :class="['plugin-card', { disabled: !plugin.enabled }]"
      >
        <div class="plugin-header">
          <div class="plugin-info">
            <h4>{{ plugin.name }}</h4>
            <span class="version">v{{ plugin.version }}</span>
          </div>
          <label class="toggle">
            <input
              type="checkbox"
              :checked="plugin.enabled"
              @change="togglePlugin(plugin)"
            />
            <span class="slider"></span>
          </label>
        </div>

        <p class="description">{{ plugin.description || "暂无描述" }}</p>

        <div class="meta">
          <span v-if="plugin.author">作者: {{ plugin.author }}</span>
          <span>ID: {{ plugin.id }}</span>
        </div>

        <div v-if="plugin.hooks.length" class="hooks">
          <span class="label">钩子:</span>
          <span v-for="hook in plugin.hooks" :key="hook" class="hook-tag">{{ hook }}</span>
        </div>

        <button class="uninstall-btn" @click="handleUninstall(plugin.id)">
          卸载
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.plugins-view {
  padding: 16px;
  max-width: 800px;
  margin: 0 auto;
}

h2 {
  margin: 0 0 16px;
  font-size: 20px;
  color: #333;
}

h3 {
  margin: 0 0 12px;
  font-size: 16px;
  color: #555;
}

.error {
  background: #ffebee;
  color: #c62828;
  padding: 10px;
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 13px;
}

.loading,
.empty {
  text-align: center;
  padding: 40px;
  color: #999;
}

.install-section {
  background: #f5f5f5;
  padding: 16px;
  border-radius: 8px;
  margin-bottom: 20px;
}

.install-form {
  display: flex;
  gap: 8px;
}

.install-form input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
}

.install-form button {
  padding: 8px 16px;
  background: #1976D2;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.install-form button:disabled {
  background: #ccc;
}

.plugin-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.plugin-card {
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  transition: all 0.2s;
}

.plugin-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.plugin-card.disabled {
  opacity: 0.6;
}

.plugin-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.plugin-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.plugin-info h4 {
  margin: 0;
  font-size: 15px;
}

.version {
  font-size: 11px;
  color: #999;
  background: #f0f0f0;
  padding: 2px 6px;
  border-radius: 4px;
}

.toggle {
  position: relative;
  width: 44px;
  height: 24px;
}

.toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  inset: 0;
  background: #ccc;
  border-radius: 12px;
  cursor: pointer;
  transition: 0.2s;
}

.slider::before {
  content: "";
  position: absolute;
  width: 18px;
  height: 18px;
  left: 3px;
  bottom: 3px;
  background: #fff;
  border-radius: 50%;
  transition: 0.2s;
}

.toggle input:checked + .slider {
  background: #1976D2;
}

.toggle input:checked + .slider::before {
  transform: translateX(20px);
}

.description {
  font-size: 13px;
  color: #666;
  margin: 8px 0;
}

.meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: #999;
}

.hooks {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.hooks .label {
  font-size: 11px;
  color: #999;
}

.hook-tag {
  font-size: 10px;
  padding: 2px 6px;
  background: #e3f2fd;
  color: #1976D2;
  border-radius: 4px;
}

.uninstall-btn {
  margin-top: 12px;
  padding: 6px 12px;
  background: #fff;
  border: 1px solid #ef5350;
  color: #ef5350;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.uninstall-btn:hover {
  background: #ffebee;
}
</style>
