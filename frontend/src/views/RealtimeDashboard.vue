<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from "vue";
import { getMetricsHistory, type RealtimeMetrics } from "../api/client";

const props = defineProps<{ token: string }>();

const metrics = ref<RealtimeMetrics[]>([]);
const connected = ref(false);
let ws: WebSocket | null = null;
let reconnectTimer: number | null = null;

function connect() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${protocol}//${window.location.host}/ws/monitor`);

  ws.onopen = () => {
    connected.value = true;
    ws?.send(JSON.stringify({ type: "ping" }));
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "metrics") {
        metrics.value.push(data.data);
        if (metrics.value.length > 60) metrics.value.shift();
      }
    } catch {}
  };

  ws.onclose = () => {
    connected.value = false;
    reconnectTimer = window.setTimeout(connect, 3000);
  };
}

async function loadHistory() {
  try {
    metrics.value = await getMetricsHistory(props.token, 5);
  } catch {}
}

const latest = computed(() => metrics.value[metrics.value.length - 1]);
const cpuHistory = computed(() => metrics.value.map((m) => m.cpu_percent));
const memHistory = computed(() => metrics.value.map((m) => m.memory_percent));

function buildPath(values: number[], width: number, height: number): string {
  if (values.length < 2) return "";
  const max = Math.max(...values, 1);
  const step = width / (values.length - 1);
  return values
    .map((v, i) => `${i === 0 ? "M" : "L"} ${(i * step).toFixed(1)} ${((height - (v / max) * (height - 10)) ).toFixed(1)}`)
    .join(" ");
}

const chartW = 280;
const chartH = 80;

onMounted(() => {
  loadHistory();
  connect();
});

onUnmounted(() => {
  ws?.close();
  if (reconnectTimer) clearTimeout(reconnectTimer);
});
</script>

<template>
  <div class="realtime-panel">
    <div class="panel-header">
      <h3>实时监控</h3>
      <span :class="['badge', connected ? 'on' : 'off']">{{ connected ? "已连接" : "离线" }}</span>
    </div>

    <div v-if="latest" class="metrics-grid">
      <div class="metric-card">
        <div class="metric-label">CPU</div>
        <div class="metric-value">{{ latest.cpu_percent.toFixed(1) }}%</div>
        <svg :viewBox="`0 0 ${chartW} ${chartH}`">
          <path :d="buildPath(cpuHistory, chartW, chartH)" fill="none" stroke="#1976D2" stroke-width="2" />
        </svg>
      </div>
      <div class="metric-card">
        <div class="metric-label">内存</div>
        <div class="metric-value">{{ latest.memory_percent.toFixed(1) }}%</div>
        <svg :viewBox="`0 0 ${chartW} ${chartH}`">
          <path :d="buildPath(memHistory, chartW, chartH)" fill="none" stroke="#388E3C" stroke-width="2" />
        </svg>
      </div>
    </div>

    <div v-else class="empty">等待数据...</div>
  </div>
</template>

<style scoped>
.realtime-panel {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.panel-header h3 {
  margin: 0;
  font-size: 15px;
}
.badge {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 10px;
}
.badge.on { background: #c8e6c9; color: #2e7d32; }
.badge.off { background: #ffcdd2; color: #c62828; }
.metrics-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.metric-card {
  background: #f8f9fa;
  padding: 12px;
  border-radius: 6px;
}
.metric-label {
  font-size: 11px;
  color: #999;
}
.metric-value {
  font-size: 20px;
  font-weight: 600;
  margin: 4px 0;
}
.metric-card svg {
  width: 100%;
  height: 60px;
}
.empty {
  text-align: center;
  padding: 24px;
  color: #999;
}
</style>
