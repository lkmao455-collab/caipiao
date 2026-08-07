<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import {
  getStats,
  fetchProfileData,
  type ProfileStats,
  type GroupStats,
  type FetchResult,
} from "../api/client";
import BarChart from "../components/charts/BarChart.vue";
import DonutChart from "../components/charts/DonutChart.vue";
import Heatmap from "../components/charts/Heatmap.vue";

const props = defineProps<{ token: string; profileKey: string }>();

const stats = ref<ProfileStats | null>(null);
const error = ref("");
const busy = ref(false);
const fetching = ref(false);
const fetchMsg = ref("");
const lastFetch = ref<FetchResult | null>(null);
const needsBootstrap = ref(false);
const bootstrapped = ref(false);

async function load() {
  error.value = "";
  busy.value = true;
  try {
    stats.value = await getStats(props.token, props.profileKey);
    needsBootstrap.value = (stats.value?.total_records ?? 0) === 0;
    if (needsBootstrap.value && !bootstrapped.value) {
      bootstrapped.value = true;
      await refresh("all");
    }
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}

async function refresh(mode: "latest" | "all" = "latest") {
  fetching.value = true;
  fetchMsg.value = "";
  lastFetch.value = null;
  try {
    const res = await fetchProfileData(props.token, props.profileKey, mode);
    lastFetch.value = res;
    fetchMsg.value =
      mode === "all"
        ? `已拉取 ${res.fetched} 期，新增 ${res.added} 期，本地共 ${res.total} 期`
        : `已抓取 ${res.fetched} 期，新增 ${res.added} 期，本地共 ${res.total} 期`;
    await load();
  } catch (e) {
    fetchMsg.value = String(e);
  } finally {
    fetching.value = false;
  }
}

onMounted(load);

watch(
  () => props.profileKey,
  () => {
    bootstrapped.value = false;
    needsBootstrap.value = false;
    load();
  },
);

function maxFreq(g: GroupStats): number {
  const vals = Object.values(g.frequency);
  return vals.length ? Math.max(...vals) : 1;
}

const oddEvenSlices = computed(() => {
  if (!stats.value) return [];
  const [odd, even] = stats.value.odd_even_ratio;
  return [
    { label: "奇数", value: Math.round(odd * 100), color: "#1976D2" },
    { label: "偶数", value: Math.round(even * 100), color: "#FF9800" },
  ];
});

const highLowSlices = computed(() => {
  if (!stats.value) return [];
  const [high, low] = stats.value.high_low_ratio;
  return [
    { label: "大号", value: Math.round(high * 100), color: "#E53935" },
    { label: "小号", value: Math.round(low * 100), color: "#43A047" },
  ];
});

const heatmapCells = computed(() => {
  if (!stats.value) return [];
  const cells: { row: number; col: number; value: number; label: string }[] = [];
  const primary = stats.value.primary_group;
  const g = stats.value.groups[primary];
  if (!g) return [];
  const vals = Object.entries(g.frequency);
  const rows = Math.ceil(vals.length / 10);
  for (let i = 0; i < vals.length; i++) {
    const row = Math.floor(i / 10);
    const col = i % 10;
    cells.push({ row, col, value: vals[i][1], label: `${vals[i][0]}: ${vals[i][1]}` });
  }
  return { cells, rows, cols: 10 };
});

const missingData = computed(() => {
  if (!stats.value) return [];
  const primary = stats.value.primary_group;
  const g = stats.value.groups[primary];
  if (!g) return [];
  return g.missing.slice(0, 20).map(([num, gap]) => ({ label: String(num), value: gap }));
});
</script>

<template>
  <div class="card">
    <h2>统计分析 · {{ profileKey }}</h2>
    <div class="row">
      <button :disabled="fetching" @click="refresh('latest')">拉取最新开奖</button>
      <span v-if="fetching">拉取中…</span>
    </div>

    <div v-if="needsBootstrap" class="banner">
      <p>本地暂无该彩种历史数据，已为您自动拉取全量历史；若失败可手动重试：</p>
      <div class="row">
        <button :disabled="fetching" @click="refresh('all')">拉取全量历史</button>
        <button :disabled="fetching" @click="refresh('latest')">仅拉取最新</button>
      </div>
    </div>

    <p v-if="fetchMsg" class="hint">{{ fetchMsg }}</p>
    <p v-if="busy">加载中…</p>
    <p v-if="error" class="error">{{ error }}</p>
    <template v-if="stats">
      <p>共 {{ stats.total_records }} 期 · 主号组：{{ stats.primary_group }}</p>

      <div v-for="(_g, key) in stats.groups" :key="key" class="group-block">
        <h3 :style="{ color: stats.groups[key as string].color }">
          {{ stats.groups[key as string].name }}（{{ stats.groups[key as string].lo }}-{{ stats.groups[key as string].hi }}）
        </h3>
        <BarChart
          :items="Object.entries(stats.groups[key as string].frequency).map(([n, v]) => ({
            label: n,
            value: v,
            color: stats.groups[key as string].color,
          }))"
          :height="100"
        />
        <div class="meta">
          <span>热号：{{ stats.groups[key as string].hot.join(", ") }}</span>
          <span>冷号：{{ stats.groups[key as string].cold.join(", ") }}</span>
        </div>
      </div>

      <div class="charts-row" v-if="missingData.length">
        <h3>最近遗漏值（主号组）</h3>
        <BarChart :items="missingData" :height="120" color="#FF7043" />
      </div>

      <div class="charts-row" v-if="oddEvenSlices.length">
        <h3>综合分析</h3>
        <div class="chart-pair">
          <div class="chart-box">
            <h4>奇偶分布</h4>
            <DonutChart :slices="oddEvenSlices" :size="140" />
          </div>
          <div class="chart-box">
            <h4>大小分布</h4>
            <DonutChart :slices="highLowSlices" :size="140" />
          </div>
        </div>
      </div>

      <div v-if="heatmapCells.cells?.length" class="charts-row">
        <h3>号码频率热力图（主号组）</h3>
        <Heatmap
          :cells="heatmapCells.cells"
          :rows="heatmapCells.rows"
          :cols="heatmapCells.cols"
          :cell-size="26"
          color-low="#e8f5e9"
          color-high="#2e7d32"
        />
      </div>

      <h3>综合统计</h3>
      <ul class="summary">
        <li>奇偶比：{{ stats.odd_even_ratio[0].toFixed(2) }} : {{ stats.odd_even_ratio[1].toFixed(2) }}</li>
        <li>大小比：{{ stats.high_low_ratio[0].toFixed(2) }} : {{ stats.high_low_ratio[1].toFixed(2) }}</li>
        <li>和值：均值 {{ (stats.sum_statistics.mean ?? 0).toFixed(1) }} / 跨度 {{ (stats.sum_statistics.span ?? 0).toFixed(1) }}</li>
        <li>最大跨度：{{ (stats.span.max ?? 0).toFixed(1) }}</li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.hint { color: #888; font-size: 12px; }
.banner {
  background: #fff8e1; border: 1px solid #ffe082; border-radius: 6px;
  padding: 10px 12px; margin: 8px 0; font-size: 13px; color: #6d4c00;
}
.banner .row { margin-top: 6px; }
.group-block { margin-bottom: 18px; }
.meta { font-size: 12px; color: #555; display: flex; gap: 16px; margin-top: 4px; }
.summary { font-size: 13px; color: #444; line-height: 1.7; }
.charts-row { margin: 16px 0; }
.chart-pair { display: flex; gap: 24px; flex-wrap: wrap; }
.chart-box { border: 1px solid #eee; border-radius: 8px; padding: 12px; }
.chart-box h4 { margin: 0 0 8px 0; font-size: 13px; color: #666; }
</style>
