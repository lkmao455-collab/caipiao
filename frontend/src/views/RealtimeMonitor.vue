<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from "vue";
import { getSystemStats, type SystemStats } from "../api/client";

const props = defineProps<{ token: string }>();

interface MetricsPoint {
  timestamp: number;
  cpu_percent: number;
  memory_mb: number;
  memory_percent: number;
  network_sent: number;
  network_recv: number;
}

const metrics = ref<MetricsPoint[]>([]);
const current = ref<SystemStats | null>(null);
const connected = ref(false);
const ws = ref<WebSocket | null>(null);
const chartWidth = 300;
const chartHeight = 100;

// 连接 WebSocket
function connect() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host;
  ws.value = new WebSocket(`${protocol}//${host}/ws/monitor`);

  ws.value.onopen = () => {
    connected.value = true;
    // 心跳
    setInterval(() => {
      if (ws.value?.readyState === WebSocket.OPEN) {
        ws.value.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);
  };

  ws.value.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "metrics") {
        metrics.value.push(data.data);
        if (metrics.value.length > 60) {
          metrics.value.shift();
        }
      }
    } catch {}
  };

  ws.value.onclose = () => {
    connected.value = false;
    // 自动重连
    setTimeout(connect, 3000);
  };

  ws.value.onerror = () => {
    connected.value = false;
  };
}

// 初始加载
async function loadStats() {
  try {
    current.value = await getSystemStats(props.token);
  } catch {}
}

// CPU 图表路径
const cpuPath = computed(() => {
  if (metrics.value.length < 2) return "";
  const step = chartWidth / (metrics.value.length - 1);
  return metrics.value
    .map((m, i) => {
      const x = i * step;
      const y = chartHeight - (m.cpu_percent / 100) * chartHeight;
      return `${i === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");
});

// 内存图表路径
const memoryPath = computed(() => {
  if (metrics.value.length < 2) return "";
  const step = chartWidth / (metrics.value.length - 1);
  return metrics.value
    .map((m, i) => {
      const x = i * step;
      const y = chartHeight - (m.memory_percent / 100) * chartHeight;
      return `${i === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");
});

const latestCpu = computed(() => metrics.value[metrics.value.length - 1]?.cpu_percent ?? 0);
const latestMemory = computed(() => metrics.value[metrics.value.length - 1]?.memory_percent ?? 0);

let reconnectTimer: number | null = null;

onMounted(() => {
  loadStats();
  connect();
});

onUnmounted(() => {
  ws.value?.close();
  if (reconnectTimer) clearTimeout(reconnectTimer);
});
</script>

<template>
  <div class="realtime-monitor">
    <div class="monitor-header">
      <h3>实时监控</h3>
      <span :class="['status', { connected }]">
        {{ connected ? "已连接" : "未连接" }}
      </span>
    </div>

    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-label">CPU</div>
        <div class="stat-value">{{ latestCpu.toFixed(1) }}%</div>
        <div class="stat-bar">
          <div class="bar-fill cpu" :style="{ width: `${latestCpu}%` }" />
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">内存</div>
        <div class="stat-value">{{ latestMemory.toFixed(1) }}%</div>
        <div class="stat-bar">
          <div class="bar-fill memory" :style="{ width: `${latestMemory}%` }" />
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">当前连接</div>
        <div class="stat-value">{{ current?.threads ?? 0 }}</div>
      </div>
    </div>

    <div class="charts-row">
      <div class="chart-card">
        <h4>CPU 使用率</h4>
        <svg :viewBox="`0 0 ${chartWidth} ${chartHeight}`" preserveAspectRatio="none">
          <defs>
            <linearGradient id="cpuGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#1976D2" stop-opacity="0.3" />
              <stop offset="100%" stop-color="#1976D2" stop-opacity="0.05" />
            </linearGradient>
          </defs>
          <!-- 网格 -->
          <g opacity="0.2">
            <line v-for="i in 5" :key="i" :x1="0" :y1="i * 20" :x2="chartWidth" :y2="i * 20" stroke="#666" stroke-width="0.5" stroke-dasharray="2,2" />
          </g>
          <!-- 面积 -->
          <path :d="cpuPath + ` L ${chartWidth} ${chartHeight} L 0 ${chartHeight} Z`" fill="url(#cpuGrad)" />
          <!-- 线条 -->
          <path :d="cpuPath" fill="none" stroke="#1976D2" stroke-width="2" />
        </svg>
      </div>

      <div class="chart-card">
        <h4>内存使用率</h4>
        <svg :viewBox="`0 0 ${chartWidth} ${chartHeight}`" preserveAspectRatio="none">
          <defs>
            <linearGradient id="memGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#388E3C" stop-opacity="0.3" />
              <stop offset="100%" stop-color="#388E3C" stop-opacity="0.05" />
            </linearGradient>
          </defs>
          <g opacity="0.2">
            <line v-for="i in 5" :key="i" :x1="0" :y1="i * 20" :x2="chartWidth" :y2="i * 20" stroke="#666" stroke-width="0.5" stroke-dasharray="2,2" />
          </g>
          <path :d="memoryPath + ` L ${chartWidth} ${chartHeight} L 0 ${chartHeight} Z`" fill="url(#memGrad)" />
          <path :d="memoryPath" fill="none" stroke="#388E3C" stroke-width="2" />
        </svg>
      </div>
    </div>

    <div v-if="current" class="detail-stats">
      <div class="detail-item">
        <span class="label">内存</span>
        <span class="value">{{ current.memory_mb.toFixed(0) }} MB</span>
      </div>
      <div class="detail-item">
        <span class="label">线程</span>
        <span class="value">{{ current.threads }}</span>
      </div>
      <div class="detail-item">
        <span class="label">运行时间</span>
        <span class="value">{{ Math.floor(current.uptime_seconds / 3600) }}h</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.realtime-monitor {
  padding: 16px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.monitor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.monitor-header h3 {
  margin: 0;
  font-size: 16px;
}

.status {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 12px;
  background: #ffcdd2;
  color: #c62828;
}

.status.connected {
  background: #c8e6c9;
  color: #2e7d32;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.stat-card {
  background: #f5f5f5;
  padding: 12px;
  border-radius: 6px;
}

.stat-label {
  font-size: 11px;
  color: #999;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 20px;
  font-weight: 600;
  color: #333;
}

.stat-bar {
  height: 4px;
  background: #e0e0e0;
  border-radius: 2px;
  margin-top: 8px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s;
}

.bar-fill.cpu {
  background: #1976D2;
}

.bar-fill.memory {
  background: #388E3C;
}

.charts-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.chart-card {
  background: #f5f5f5;
  padding: 12px;
  border-radius: 6px;
}

.chart-card h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: #666;
}

.chart-card svg {
  width: 100%;
  height: 80px;
}

.detail-stats {
  display: flex;
  gap: 16px;
  justify-content: center;
}

.detail-item {
  text-align: center;
}

.detail-item .label {
  display: block;
  font-size: 11px;
  color: #999;
}

.detail-item .value {
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

@media (max-width: 768px) {
  .stats-row {
    grid-template-columns: 1fr;
  }
  .charts-row {
    grid-template-columns: 1fr;
  }
}
</style>
