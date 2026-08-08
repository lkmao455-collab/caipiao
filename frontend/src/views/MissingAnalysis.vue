<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import {
  getMissingAnalysis,
  getComboAnalysis,
  getStats,
  type MissingAnalysisResponse,
  type ComboAnalysisResponse,
  type ProfileStats,
} from "../api/client";
import BarChart from "../components/charts/BarChart.vue";
import GroupedBarChart from "../components/charts/GroupedBarChart.vue";

const props = defineProps<{ token: string; profileKey: string }>();

const missing = ref<MissingAnalysisResponse | null>(null);
const combo = ref<ComboAnalysisResponse | null>(null);
const stats = ref<ProfileStats | null>(null);
const error = ref("");
const busy = ref(false);
const selectedWindow = ref(50);

async function load() {
  error.value = "";
  busy.value = true;
  try {
    const [m, c, s] = await Promise.all([
      getMissingAnalysis(props.token, props.profileKey),
      getComboAnalysis(props.token, props.profileKey),
      getStats(props.token, props.profileKey),
    ]);
    missing.value = m;
    combo.value = c;
    stats.value = s;
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}

onMounted(load);
watch(() => props.profileKey, load);

const currentMissingData = computed(() => {
  if (!missing.value) return [];
  const data = missing.value.missing_by_window[selectedWindow.value] || [];
  return data.slice(0, 20).map((item) => ({
    label: String(item.number),
    value: item.gap,
  }));
});

const gapDistData = computed(() => {
  if (!missing.value) return [];
  return Object.entries(missing.value.gap_distribution)
    .map(([gap, count]) => ({ label: gap, value: count }))
    .sort((a, b) => Number(a.label) - Number(b.label));
});

const trendUpData = computed(() => {
  if (!missing.value) return [];
  return missing.value.trend_data
    .filter((t) => t.trend === "up" && t.change > 0)
    .sort((a, b) => b.change - a.change)
    .slice(0, 10)
    .map((t) => ({ label: String(t.number), value: t.change }));
});

const trendDownData = computed(() => {
  if (!missing.value) return [];
  return missing.value.trend_data
    .filter((t) => t.trend === "down" && t.change < 0)
    .sort((a, b) => a.change - b.change)
    .slice(0, 10)
    .map((t) => ({ label: String(t.number), value: Math.abs(t.change) }));
});

const pairData = computed(() => {
  if (!combo.value) return [];
  return combo.value.common_pairs.slice(0, 10).map((p) => ({
    label: p.pair.join("-"),
    value: p.count,
  }));
});

const tripleData = computed(() => {
  if (!combo.value) return [];
  return combo.value.common_triples.slice(0, 8).map((t) => ({
    label: t.triple.join("-"),
    value: t.count,
  }));
});

const zoneDistData = computed(() => {
  if (!combo.value) return [];
  return Object.entries(combo.value.zone_distribution).map(([zone, ratio]) => ({
    label: zone.replace("zone", "区"),
    value: Math.round(ratio * 100),
  }));
});
</script>

<template>
  <div class="missing-analysis">
    <h3>遗漏值深度分析</h3>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="busy">加载中…</p>

    <template v-if="missing && stats">
      <!-- 多窗口遗漏对比 -->
      <div class="section">
        <h4>多窗口遗漏对比</h4>
        <div class="window-tabs">
          <button
            v-for="w in missing.windows"
            :key="w"
            :class="{ active: selectedWindow === w }"
            @click="selectedWindow = w"
          >
            {{ w }}期
          </button>
        </div>
        <div class="chart-row">
          <div class="chart-box">
            <h5>当前遗漏值 Top20（{{ selectedWindow }}期）</h5>
            <BarChart :items="currentMissingData" :height="150" color="#FF7043" />
          </div>
          <div class="chart-box">
            <h5>遗漏值分布</h5>
            <BarChart :items="gapDistData" :height="150" color="#1976D2" />
          </div>
        </div>
      </div>

      <!-- 遗漏趋势信号 -->
      <div class="section">
        <h4>冷热转换信号</h4>
        <div class="signals">
          <div class="signal-card hot">
            <span class="label">热信号（遗漏减少）</span>
            <div class="numbers">
              <span v-for="n in missing.hot_signals" :key="n" class="num hot">{{ n }}</span>
              <span v-if="!missing.hot_signals.length" class="empty">暂无</span>
            </div>
            <p class="desc">遗漏值近期明显下降，可能出现频率增加</p>
          </div>
          <div class="signal-card cold">
            <span class="label">冷信号（遗漏增加）</span>
            <div class="numbers">
              <span v-for="n in missing.cold_signals" :key="n" class="num cold">{{ n }}</span>
              <span v-if="!missing.cold_signals.length" class="empty">暂无</span>
            </div>
            <p class="desc">遗漏值近期明显上升，出现频率可能降低</p>
          </div>
        </div>
      </div>

      <!-- 遗漏趋势图 -->
      <div class="section">
        <h4>遗漏趋势变化</h4>
        <div class="chart-row">
          <div class="chart-box">
            <h5>遗漏上升号码（近期出现减少）</h5>
            <BarChart :items="trendUpData" :height="120" color="#E53935" />
          </div>
          <div class="chart-box">
            <h5>遗漏下降号码（近期出现增加）</h5>
            <BarChart :items="trendDownData" :height="120" color="#43A047" />
          </div>
        </div>
      </div>

      <!-- 常见组合分析 -->
      <div class="section" v-if="combo">
        <h4>常见号码组合</h4>
        <div class="combo-grid">
          <div class="combo-card">
            <h5>常见对子</h5>
            <BarChart :items="pairData" :height="150" color="#8E24AA" />
          </div>
          <div class="combo-card">
            <h5>常见三连号</h5>
            <BarChart :items="tripleData" :height="150" color="#00897B" />
          </div>
          <div class="combo-card">
            <h5>三区分布</h5>
            <BarChart :items="zoneDistData" :height="150" color="#FB8C00" />
            <p class="meta">连号率：{{ (combo.consecutive_frequency * 100).toFixed(1) }}%</p>
          </div>
        </div>
      </div>

      <!-- 遗漏值汇总表 -->
      <div class="section">
        <h4>遗漏值汇总</h4>
        <table class="missing-table">
          <thead>
            <tr>
              <th>号码</th>
              <th v-for="w in missing.windows" :key="w">{{ w }}期</th>
              <th>趋势</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in missing.trend_data.slice(0, 15)" :key="t.number">
              <td>{{ t.number }}</td>
              <td v-for="w in missing.windows" :key="w">
                {{ missing.missing_by_window[w]?.find((m: any) => m.number === t.number)?.gap ?? '-' }}
              </td>
              <td :class="'trend-' + t.trend">
                {{ t.trend === 'up' ? '↑' : t.trend === 'down' ? '↓' : '→' }}
                {{ t.change }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.missing-analysis { padding: 12px; }
.section { margin-bottom: 20px; }
.section h4 { margin: 0 0 10px; color: #333; font-size: 15px; }
.window-tabs { display: flex; gap: 8px; margin-bottom: 12px; }
.window-tabs button {
  padding: 6px 12px; border: 1px solid #ccc; border-radius: 4px;
  background: #f5f5f5; cursor: pointer; font-size: 13px;
}
.window-tabs button.active { background: #1976D2; color: #fff; border-color: #1976D2; }
.chart-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.chart-box { border: 1px solid #eee; border-radius: 6px; padding: 12px; }
.chart-box h5 { margin: 0 0 8px; font-size: 13px; color: #666; }
.signals { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.signal-card { border: 1px solid #eee; border-radius: 6px; padding: 12px; }
.signal-card.hot { border-color: #ffcdd2; background: #fff5f5; }
.signal-card.cold { border-color: #bbdefb; background: #f5f9ff; }
.signal-card .label { font-size: 13px; font-weight: 600; color: #555; }
.signal-card .numbers { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
.signal-card .num {
  display: inline-block; padding: 2px 8px; border-radius: 4px;
  font-size: 13px; font-weight: 600;
}
.signal-card .num.hot { background: #ff8a80; color: #c62828; }
.signal-card .num.cold { background: #82b1ff; color: #1565c0; }
.signal-card .desc { font-size: 11px; color: #888; margin: 0; }
.combo-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.combo-card { border: 1px solid #eee; border-radius: 6px; padding: 12px; }
.combo-card h5 { margin: 0 0 8px; font-size: 13px; color: #666; }
.combo-card .meta { font-size: 12px; color: #888; margin: 8px 0 0; }
.missing-table { border-collapse: collapse; font-size: 12px; width: 100%; }
.missing-table th, .missing-table td { border: 1px solid #eee; padding: 4px 8px; text-align: center; }
.missing-table th { background: #f5f5f5; font-weight: 600; }
.trend-up { color: #E53935; }
.trend-down { color: #43A047; }
.trend-stable { color: #888; }
.empty { color: #999; font-size: 12px; }
</style>
