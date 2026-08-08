<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { getTrendAnalysis, getStats, type TrendAnalysisResponse, type ProfileStats } from "../api/client";
import TrendChart from "../components/charts/TrendChart.vue";

const props = defineProps<{ token: string; profileKey: string }>();

const trend = ref<TrendAnalysisResponse | null>(null);
const stats = ref<ProfileStats | null>(null);
const error = ref("");
const busy = ref(false);
const rounds = ref(30);
const selectedNumbers = ref<number[]>([]);

async function load() {
  error.value = "";
  busy.value = true;
  try {
    const [t, s] = await Promise.all([
      getTrendAnalysis(props.token, props.profileKey, rounds.value),
      getStats(props.token, props.profileKey),
    ]);
    trend.value = t;
    stats.value = s;
    // 默认选中前5个热号
    if (s && selectedNumbers.value.length === 0) {
      const primary = s.primary_group;
      selectedNumbers.value = s.groups[primary]?.hot.slice(0, 5) ?? [];
    }
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}

onMounted(load);
watch([() => props.profileKey, rounds], load);

function toggleNumber(n: number) {
  const idx = selectedNumbers.value.indexOf(n);
  if (idx >= 0) {
    selectedNumbers.value.splice(idx, 1);
  } else if (selectedNumbers.value.length < 8) {
    selectedNumbers.value.push(n);
  }
}

const allNumbers = computed(() => {
  if (!stats.value) return [];
  const primary = stats.value.primary_group;
  return stats.value.groups[primary]?.hot ?? [];
});

const trendChartData = computed(() => {
  if (!trend.value || !selectedNumbers.value.length) return {};
  const result: Record<number, { date: string; value: number }[]> = {};
  for (const n of selectedNumbers.value) {
    result[n] = trend.value.trends.map((t) => {
      const primary = stats.value?.primary_group ?? "";
      const nums = t.numbers[primary] ?? [];
      return {
        date: t.draw_date,
        value: nums.includes(n) ? 1 : 0,
      };
    });
  }
  return result;
});

const trendSummary = computed(() => {
  if (!trend.value || !selectedNumbers.value.length) return [];
  return selectedNumbers.value.map((n) => {
    const appearances = trend.value!.trends.filter((t) => {
      const primary = stats.value?.primary_group ?? "";
      const nums = t.numbers[primary] ?? [];
      return nums.includes(n);
    }).length;
    return {
      number: n,
      appearances,
      rate: ((appearances / trend.value!.total_rounds) * 100).toFixed(1),
    };
  });
});

const COLORS = ["#1976D2", "#E53935", "#43A047", "#FB8C00", "#8E24AA", "#00897B", "#C0CA33", "#6D4C41"];
</script>

<template>
  <div class="trend-analysis">
    <h3>号码趋势分析</h3>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="busy">加载中…</p>

    <div class="controls">
      <label>
        回溯期数：
        <select v-model.number="rounds">
          <option :value="20">20</option>
          <option :value="30">30</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
        </select>
      </label>
    </div>

    <template v-if="trend && stats">
      <!-- 号码选择 -->
      <div class="section">
        <h4>选择号码（最多8个）</h4>
        <div class="number-picker">
          <button
            v-for="n in allNumbers"
            :key="n"
            :class="{ selected: selectedNumbers.includes(n) }"
            @click="toggleNumber(n)"
          >
            {{ n }}
          </button>
        </div>
      </div>

      <!-- 趋势图 -->
      <div class="section" v-if="selectedNumbers.length">
        <h4>号码出现趋势</h4>
        <div class="charts-grid">
          <div v-for="(n, i) in selectedNumbers" :key="n" class="chart-box">
            <TrendChart
              :data="trendChartData[n] ?? []"
              :color="COLORS[i % COLORS.length]"
              :height="100"
              :title="`号码 ${n}`"
            />
          </div>
        </div>
      </div>

      <!-- 趋势统计 -->
      <div class="section" v-if="trendSummary.length">
        <h4>趋势统计</h4>
        <table class="trend-table">
          <thead>
            <tr>
              <th>号码</th>
              <th>出现次数</th>
              <th>出现率</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in trendSummary" :key="item.number">
              <td>{{ item.number }}</td>
              <td>{{ item.appearances }} / {{ trend.total_rounds }}</td>
              <td>{{ item.rate }}%</td>
              <td :class="{ hot: Number(item.rate) > 30, cold: Number(item.rate) < 15 }">
                {{ Number(item.rate) > 30 ? '热号' : Number(item.rate) < 15 ? '冷号' : '温号' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.trend-analysis { padding: 12px; }
.section { margin-bottom: 20px; }
.section h4 { margin: 0 0 10px; color: #333; font-size: 15px; }
.controls { display: flex; gap: 12px; margin-bottom: 12px; }
.controls label { font-size: 13px; color: #555; }
.controls select { padding: 4px 8px; border: 1px solid #ccc; border-radius: 4px; }
.number-picker { display: flex; flex-wrap: wrap; gap: 6px; }
.number-picker button {
  width: 36px; height: 36px; border: 1px solid #ccc; border-radius: 4px;
  background: #fff; cursor: pointer; font-size: 14px; font-weight: 600;
}
.number-picker button.selected { background: #1976D2; color: #fff; border-color: #1976D2; }
.number-picker button:hover:not(.selected) { background: #e3f2fd; }
.charts-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }
.chart-box { border: 1px solid #eee; border-radius: 6px; padding: 8px; }
.trend-table { border-collapse: collapse; font-size: 13px; width: 100%; }
.trend-table th, .trend-table td { border: 1px solid #eee; padding: 6px 10px; text-align: center; }
.trend-table th { background: #f5f5f5; font-weight: 600; }
.trend-table .hot { color: #E53935; font-weight: 600; }
.trend-table .cold { color: #1976D2; font-weight: 600; }
</style>
