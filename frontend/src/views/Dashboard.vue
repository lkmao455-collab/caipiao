<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import {
  getStats,
  getTrendAnalysis,
  getMissingAnalysis,
  getRecommendations,
  type ProfileStats,
  type TrendAnalysisResponse,
  type MissingAnalysisResponse,
  type Recommendation,
} from "../api/client";
import BarChart from "../components/charts/BarChart.vue";
import DonutChart from "../components/charts/DonutChart.vue";
import TrendChart from "../components/charts/TrendChart.vue";

const props = defineProps<{ token: string; profileKey: string }>();

const stats = ref<ProfileStats | null>(null);
const trend = ref<TrendAnalysisResponse | null>(null);
const missing = ref<MissingAnalysisResponse | null>(null);
const recommendations = ref<Recommendation[]>([]);
const error = ref("");
const busy = ref(false);
const fullscreen = ref(false);

async function load() {
  error.value = "";
  busy.value = true;
  try {
    const [s, t, m, r] = await Promise.all([
      getStats(props.token, props.profileKey),
      getTrendAnalysis(props.token, props.profileKey, 20),
      getMissingAnalysis(props.token, props.profileKey),
      getRecommendations(props.token, props.profileKey, 3),
    ]);
    stats.value = s;
    trend.value = t;
    missing.value = m;
    recommendations.value = r;
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}

onMounted(load);
watch(() => props.profileKey, load);

function toggleFullscreen() {
  fullscreen.value = !fullscreen.value;
}

const oddEvenData = computed(() => {
  if (!stats.value) return [];
  const [odd, even] = stats.value.odd_even_ratio;
  return [
    { label: "奇", value: Math.round(odd * 100), color: "#1976D2" },
    { label: "偶", value: Math.round(even * 100), color: "#FF9800" },
  ];
});

const hotNumbers = computed(() => {
  if (!stats.value) return [];
  const primary = stats.value.primary_group;
  return stats.value.groups[primary]?.hot.slice(0, 8) ?? [];
});

const coldNumbers = computed(() => {
  if (!stats.value) return [];
  const primary = stats.value.primary_group;
  return stats.value.groups[primary]?.cold.slice(0, 8) ?? [];
});

const frequencyData = computed(() => {
  if (!stats.value) return [];
  const primary = stats.value.primary_group;
  const g = stats.value.groups[primary];
  if (!g) return [];
  return Object.entries(g.frequency)
    .slice(0, 15)
    .map(([n, v]) => ({ label: n, value: v }));
});

const trendChartData = computed(() => {
  if (!trend.value) return [];
  const primary = stats.value?.primary_group ?? "";
  const hot = hotNumbers.value;
  return trend.value.trends.map((t) => {
    const nums = t.numbers[primary] ?? [];
    return {
      date: t.draw_date.slice(5),
      value: hot.filter((n) => nums.includes(n)).length,
    };
  });
});
</script>

<template>
  <div :class="['dashboard', { fullscreen }]">
    <div class="dash-header">
      <h2>数据大屏 · {{ profileKey }}</h2>
      <button class="fs-btn" @click="toggleFullscreen">
        {{ fullscreen ? '退出全屏' : '全屏' }}
      </button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="busy" class="loading">加载中…</p>

    <template v-if="stats && !busy">
      <!-- 顶部统计卡片 -->
      <div class="stat-cards">
        <div class="stat-card">
          <span class="value">{{ stats.total_records }}</span>
          <span class="label">总期数</span>
        </div>
        <div class="stat-card">
          <span class="value hot">{{ hotNumbers.slice(0, 3).join(' ') }}</span>
          <span class="label">热号 TOP3</span>
        </div>
        <div class="stat-card">
          <span class="value cold">{{ coldNumbers.slice(0, 3).join(' ') }}</span>
          <span class="label">冷号 TOP3</span>
        </div>
        <div class="stat-card">
          <span class="value">{{ (stats.sum_statistics.mean ?? 0).toFixed(0) }}</span>
          <span class="label">平均和值</span>
        </div>
      </div>

      <!-- 主要图表区 -->
      <div class="charts-grid">
        <!-- 频率分布 -->
        <div class="chart-card">
          <h4>号码频率 TOP15</h4>
          <BarChart :items="frequencyData" :height="120" color="#1976D2" />
        </div>

        <!-- 奇偶分布 -->
        <div class="chart-card">
          <h4>奇偶分布</h4>
          <DonutChart :slices="oddEvenData" :size="120" />
        </div>

        <!-- 趋势图 -->
        <div class="chart-card wide">
          <h4>热号出现趋势（近20期）</h4>
          <TrendChart :data="trendChartData" :height="100" color="#E53935" />
        </div>
      </div>

      <!-- 遗漏信号 -->
      <div class="signals-section" v-if="missing">
        <h4>冷热信号</h4>
        <div class="signals">
          <div class="signal hot-signal">
            <span class="sig-label">热信号</span>
            <div class="nums">
              <span v-for="n in missing.hot_signals.slice(0, 6)" :key="n" class="num">{{ n }}</span>
              <span v-if="!missing.hot_signals.length" class="empty">暂无</span>
            </div>
          </div>
          <div class="signal cold-signal">
            <span class="sig-label">冷信号</span>
            <div class="nums">
              <span v-for="n in missing.cold_signals.slice(0, 6)" :key="n" class="num">{{ n }}</span>
              <span v-if="!missing.cold_signals.length" class="empty">暂无</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 推荐 -->
      <div class="rec-section" v-if="recommendations.length">
        <h4>推荐策略</h4>
        <div class="rec-cards">
          <div v-for="(r, i) in recommendations" :key="r.strategy_id" class="rec-card">
            <span class="rank">#{{ i + 1 }}</span>
            <span class="name">{{ r.strategy_name }}</span>
            <span class="score">{{ r.score.toFixed(0) }}分</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.dashboard { padding: 16px; }
.dashboard.fullscreen {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: #1a1a2e; color: #fff; z-index: 1000;
  overflow-y: auto; padding: 24px;
}
.dash-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.dash-header h2 { margin: 0; }
.fs-btn {
  padding: 6px 12px; border: 1px solid #666; background: transparent;
  color: inherit; border-radius: 4px; cursor: pointer;
}
.stat-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
.stat-card {
  background: rgba(255,255,255,0.1); border-radius: 8px; padding: 16px;
  text-align: center;
}
.stat-card .value { display: block; font-size: 24px; font-weight: 700; }
.stat-card .value.hot { color: #E53935; }
.stat-card .value.cold { color: #42A5F5; }
.stat-card .label { font-size: 12px; color: #999; margin-top: 4px; }
.charts-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-bottom: 16px; }
.chart-card {
  background: rgba(255,255,255,0.05); border-radius: 8px; padding: 12px;
}
.chart-card.wide { grid-column: span 2; }
.chart-card h4 { margin: 0 0 8px; font-size: 13px; color: #ccc; }
.signals-section { margin-bottom: 16px; }
.signals-section h4 { margin: 0 0 10px; font-size: 14px; }
.signals { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.signal { background: rgba(255,255,255,0.05); border-radius: 8px; padding: 12px; }
.signal.hot-signal { border-left: 3px solid #E53935; }
.signal.cold-signal { border-left: 3px solid #42A5F5; }
.sig-label { font-size: 12px; color: #999; }
.nums { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.nums .num {
  background: rgba(255,255,255,0.1); padding: 4px 8px; border-radius: 4px;
  font-size: 14px; font-weight: 600;
}
.nums .empty { color: #666; font-size: 12px; }
.rec-section h4 { margin: 0 0 10px; font-size: 14px; }
.rec-cards { display: flex; gap: 12px; }
.rec-card {
  flex: 1; background: rgba(255,255,255,0.05); border-radius: 8px;
  padding: 12px; display: flex; align-items: center; gap: 10px;
}
.rec-card .rank { font-size: 18px; font-weight: 700; color: #FB8C00; }
.rec-card .name { flex: 1; font-size: 14px; }
.rec-card .score { font-size: 16px; font-weight: 600; color: #43A047; }
.loading { color: #999; }
</style>
