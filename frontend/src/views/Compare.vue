<script setup lang="ts">
import { ref, onMounted, computed, watch } from "vue";
import {
  listStrategies,
  getStats,
  generate,
  compareStrategies,
  suggestParameters,
  type Strategy,
  type ProfileStats,
  type Ticket,
  type StrategyCompareResult,
  type ParameterSuggestionResponse,
} from "../api/client";
import BarChart from "../components/charts/BarChart.vue";
import GroupedBarChart from "../components/charts/GroupedBarChart.vue";

const props = defineProps<{
  token: string;
  profileKey: string;
  strategyId?: string;
}>();

const PALETTE = [
  "#1976D2",
  "#E53935",
  "#43A047",
  "#FB8C00",
  "#8E24AA",
  "#00897B",
  "#C0CA33",
  "#6D4C41",
];

const strategies = ref<Strategy[]>([]);
const stats = ref<ProfileStats | null>(null);
const selected = ref<string[]>([]);
const count = ref(10);
const error = ref("");
const busy = ref(false);
const results = ref<StrategyResult[]>([]);
const compareBusy = ref(false);
const compareResults = ref<StrategyCompareResult[]>([]);
const compareRanking = ref<string[]>([]);
const backtestRounds = ref(30);
const suggestBusy = ref(false);
const suggestions = ref<ParameterSuggestionResponse | null>(null);

interface StrategyResult {
  strategyId: string;
  name: string;
  color: string;
  tickets: Ticket[];
  freq: Record<number, number>;
  totalNumbers: number;
  sums: number[];
  oddPct: number;
  highPct: number;
  distinct: Set<number>;
}

const primaryGroup = computed(() => stats.value?.primary_group ?? "");
const lo = computed(() => {
  const g = primaryGroup.value ? stats.value?.groups[primaryGroup.value] : undefined;
  return g ? g.lo : 1;
});
const hi = computed(() => {
  const g = primaryGroup.value ? stats.value?.groups[primaryGroup.value] : undefined;
  return g ? g.hi : 33;
});
const numbers = computed(() => {
  const out: number[] = [];
  for (let n = lo.value; n <= hi.value; n++) out.push(n);
  return out;
});

async function load() {
  error.value = "";
  try {
    const [ss, st] = await Promise.all([
      listStrategies(props.token, props.profileKey),
      getStats(props.token, props.profileKey),
    ]);
    strategies.value = ss;
    stats.value = st;
    const initial =
      props.strategyId && ss.some((s) => s.id === props.strategyId)
        ? [props.strategyId]
        : ss.length
          ? [ss[0].id]
          : [];
    selected.value = initial;
  } catch (e) {
    error.value = String(e);
  }
}

onMounted(load);
watch(
  () => props.profileKey,
  () => {
    results.value = [];
    load();
  },
);

function primaryNumbers(t: Ticket): number[] {
  const groups = (t.groups ?? {}) as Record<string, unknown>;
  const pg = primaryGroup.value;
  let arr = pg ? groups[pg] : undefined;
  if (!Array.isArray(arr)) {
    const first = Object.values(groups)[0];
    arr = Array.isArray(first) ? first : [];
  }
  return Array.isArray(arr) ? (arr as number[]) : [];
}

function computeResult(s: Strategy, color: string, tickets: Ticket[]): StrategyResult {
  const freq: Record<number, number> = {};
  const sums: number[] = [];
  const distinct = new Set<number>();
  let totalNumbers = 0;
  let odd = 0;
  const highThreshold = Math.floor((lo.value + hi.value) / 2) + 1;
  let high = 0;
  for (const t of tickets) {
    const nums = primaryNumbers(t);
    let sum = 0;
    for (const n of nums) {
      freq[n] = (freq[n] ?? 0) + 1;
      totalNumbers++;
      sum += n;
      distinct.add(n);
      if (n % 2 === 1) odd++;
      if (n >= highThreshold) high++;
    }
    sums.push(sum);
  }
  return {
    strategyId: s.id,
    name: s.name,
    color,
    tickets,
    freq,
    totalNumbers,
    sums,
    oddPct: totalNumbers ? (odd / totalNumbers) * 100 : 0,
    highPct: totalNumbers ? (high / totalNumbers) * 100 : 0,
    distinct,
  };
}

const sumBuckets = computed(() => {
  const all = results.value.flatMap((r) => r.sums);
  if (!all.length) return { min: 0, max: 1, size: 1, count: 10 };
  const min = Math.min(...all);
  const max = Math.max(...all);
  const count = 10;
  const size = (max - min) / count || 1;
  return { min, max, size, count };
});

function sumHistogram(r: StrategyResult): { label: string | number; value: number }[] {
  const { min, size, count } = sumBuckets.value;
  const buckets = new Array(count).fill(0);
  for (const s of r.sums) {
    let idx = Math.floor((s - min) / size);
    if (idx >= count) idx = count - 1;
    if (idx < 0) idx = 0;
    buckets[idx]++;
  }
  return buckets.map((v, i) => {
    const from = Math.round(min + i * size);
    const to = Math.round(min + (i + 1) * size);
    return { label: `${from}-${to}`, value: v };
  });
}

const comparisonSeries = computed(() => {
  if (!results.value.length) return [];
  return results.value.map((r) => ({
    name: r.name,
    color: r.color,
    values: numbers.value.map((n) => (r.totalNumbers ? ((r.freq[n] ?? 0) / r.totalNumbers) * 100 : 0)),
  }));
});

const historicalSeries = computed(() => {
  if (!stats.value || !primaryGroup.value) return [];
  const g = stats.value.groups[primaryGroup.value];
  const total = Object.values(g.frequency).reduce((a, b) => a + b, 0) || 1;
  return numbers.value.map((n) => ({
    label: n,
    value: ((g.frequency[String(n)] ?? 0) / total) * 100,
  }));
});

const overlap = computed(() => {
  if (results.value.length < 2) return [];
  const base = results.value[0];
  return results.value.slice(1).map((r) => {
    let inter = 0;
    for (const n of r.distinct) if (base.distinct.has(n)) inter++;
    const union = base.distinct.size + r.distinct.size - inter;
    return {
      name: r.name,
      distinct: r.distinct.size,
      overlap: inter,
      jaccard: union ? (inter / union) * 100 : 0,
    };
  });
});

async function run() {
  error.value = "";
  if (!selected.value.length) {
    error.value = "请至少选择一个策略";
    return;
  }
  busy.value = true;
  results.value = [];
  try {
    const byId = new Map(strategies.value.map((s) => [s.id, s]));
    const out: StrategyResult[] = [];
    for (let i = 0; i < selected.value.length; i++) {
      const sid = selected.value[i];
      const s = byId.get(sid);
      if (!s) continue;
      const res = await generate(props.token, props.profileKey, sid, count.value, []);
      out.push(computeResult(s, PALETTE[i % PALETTE.length], res.tickets));
    }
    results.value = out;
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}

async function runCompare() {
  error.value = "";
  if (!selected.value.length) {
    error.value = "请至少选择一个策略";
    return;
  }
  compareBusy.value = true;
  compareResults.value = [];
  compareRanking.value = [];
  try {
    const res = await compareStrategies(props.token, {
      profile_key: props.profileKey,
      strategy_ids: selected.value,
      count: count.value,
      rounds: backtestRounds.value,
    });
    compareResults.value = res.strategies;
    compareRanking.value = res.ranking;
  } catch (e) {
    error.value = String(e);
  } finally {
    compareBusy.value = false;
  }
}

function getRankBadge(idx: number): string {
  if (idx === 0) return "🥇";
  if (idx === 1) return "🥈";
  if (idx === 2) return "🥉";
  return `#${idx + 1}`;
}

function getRoiClass(roi: number): string {
  if (roi > 0) return "positive";
  if (roi < 0) return "negative";
  return "";
}

const rankingData = computed(() => {
  return compareRanking.value.map((sid) => {
    return compareResults.value.find((r) => r.strategy_id === sid);
  }).filter(Boolean) as StrategyCompareResult[];
});

const profitChartData = computed(() => {
  return compareResults.value.map((r) => ({
    label: r.strategy_name,
    value: r.profit,
  }));
});

const hitRateChartData = computed(() => {
  return compareResults.value.map((r) => ({
    label: r.strategy_name,
    value: +(r.hit_rate * 100).toFixed(1),
  }));
});

async function runSuggest() {
  error.value = "";
  if (!selected.value.length) {
    error.value = "请至少选择一个策略";
    return;
  }
  suggestBusy.value = true;
  suggestions.value = null;
  try {
    const res = await suggestParameters(
      props.token,
      props.profileKey,
      selected.value[0],
      backtestRounds.value,
    );
    suggestions.value = res;
  } catch (e) {
    error.value = String(e);
  } finally {
    suggestBusy.value = false;
  }
}
</script>

<template>
  <div class="card">
    <h2>策略对比 · {{ profileKey }}</h2>
    <p v-if="error" class="error">{{ error }}</p>

    <div class="controls">
      <div class="strat-list">
        <label
          v-for="(s, i) in strategies"
          :key="s.id"
          class="strat-item"
          :style="{ borderColor: selected.includes(s.id) ? PALETTE[i % PALETTE.length] : '#ccc' }"
        >
          <input type="checkbox" :value="s.id" v-model="selected" />
          <span :style="{ color: selected.includes(s.id) ? PALETTE[i % PALETTE.length] : '#333' }">
            {{ s.name }}
          </span>
        </label>
      </div>
      <div class="row">
        <span>每策略注数：</span>
        <input v-model.number="count" type="number" min="1" max="100" style="width: 80px" />
        <span>回测期数：</span>
        <input v-model.number="backtestRounds" type="number" min="5" max="100" style="width: 80px" />
        <button :disabled="busy" @click="run">比较生成</button>
        <button :disabled="compareBusy" @click="runCompare">策略对比回测</button>
        <button :disabled="suggestBusy" @click="runSuggest">参数优化建议</button>
      </div>
    </div>

    <template v-if="results.length">
      <!-- 号码频率分布对比 -->
      <h3>号码频率分布对比（%）</h3>
      <GroupedBarChart :categories="numbers" :series="comparisonSeries" />
      <div class="legend">
        <span v-for="r in results" :key="r.strategyId" class="legend-item">
          <i :style="{ background: r.color }"></i>{{ r.name }}
        </span>
      </div>

      <!-- 历史基线 -->
      <h3>历史频率基线（%）</h3>
      <p class="hint">基于 {{ stats?.total_records }} 期开奖数据的各号码出现频率，作为对比参照。</p>
      <BarChart v-if="historicalSeries.length" :items="historicalSeries" color="#9E9E9E" />

      <!-- 各策略明细 -->
      <div v-for="r in results" :key="r.strategyId" class="strat-card">
        <h4 :style="{ color: r.color }">{{ r.name }}</h4>
        <ul class="metrics">
          <li>注数：{{ r.tickets.length }}</li>
          <li>均和值：{{ (r.sums.reduce((a, b) => a + b, 0) / (r.sums.length || 1)).toFixed(1) }}</li>
          <li>奇偶比：{{ r.oddPct.toFixed(0) }}% / {{ (100 - r.oddPct).toFixed(0) }}%</li>
          <li>大小比：{{ r.highPct.toFixed(0) }}% / {{ (100 - r.highPct).toFixed(0) }}%</li>
          <li>去重号码：{{ r.distinct.size }}</li>
        </ul>
        <h5>和值分布</h5>
        <BarChart :items="sumHistogram(r)" :color="r.color" />
      </div>

      <!-- 重叠度 -->
      <template v-if="overlap.length">
        <h3>与「{{ results[0].name }}」号码重叠度</h3>
        <table class="ov-table">
          <thead>
            <tr><th>策略</th><th>去重号码</th><th>重叠号码</th><th>Jaccard</th></tr>
          </thead>
          <tbody>
            <tr v-for="o in overlap" :key="o.name">
              <td>{{ o.name }}</td>
              <td>{{ o.distinct }}</td>
              <td>{{ o.overlap }}</td>
              <td>{{ o.jaccard.toFixed(0) }}%</td>
            </tr>
          </tbody>
        </table>
      </template>
    </template>

    <!-- 策略对比回测结果 -->
    <template v-if="compareResults.length">
      <h2>策略对比回测分析</h2>
      <p class="hint">基于最近 {{ backtestRounds }} 期历史数据的回测结果对比。</p>

      <!-- 排名表 -->
      <h3>综合排名</h3>
      <table class="rank-table">
        <thead>
          <tr>
            <th>排名</th>
            <th>策略</th>
            <th>命中率</th>
            <th>命中次数</th>
            <th>利润</th>
            <th>ROI</th>
            <th>平均每期利润</th>
            <th>最大回撤</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in rankingData" :key="r.strategy_id" :class="{ 'top-rank': i < 3 }">
            <td class="rank-badge">{{ getRankBadge(i) }}</td>
            <td>{{ r.strategy_name }}</td>
            <td>{{ (r.hit_rate * 100).toFixed(1) }}%</td>
            <td>{{ r.hit_count }} / {{ r.total_rounds }}</td>
            <td :class="getRoiClass(r.profit)">{{ r.profit >= 0 ? '+' : '' }}{{ r.profit }} 元</td>
            <td :class="getRoiClass(r.roi)">{{ (r.roi * 100).toFixed(1) }}%</td>
            <td :class="getRoiClass(r.profit_per_round)">{{ r.profit_per_round >= 0 ? '+' : '' }}{{ r.profit_per_round.toFixed(1) }}</td>
            <td>{{ (r.max_drawdown * 100).toFixed(1) }}%</td>
          </tr>
        </tbody>
      </table>

      <!-- 图表对比 -->
      <div class="compare-charts">
        <div class="chart-card">
          <h4>命中率对比（%）</h4>
          <BarChart :items="hitRateChartData" color="#1976D2" />
        </div>
        <div class="chart-card">
          <h4>利润对比（元）</h4>
          <BarChart :items="profitChartData" color="#43A047" />
        </div>
      </div>

      <!-- 详细指标 -->
      <h3>详细指标</h3>
      <div class="detail-grid">
        <div v-for="r in rankingData" :key="r.strategy_id" class="detail-card">
          <h4 :style="{ color: PALETTE[compareRanking.indexOf(r.strategy_id) % PALETTE.length] }">
            {{ r.strategy_name }}
          </h4>
          <ul class="detail-list">
            <li><span class="label">总轮数：</span>{{ r.total_rounds }}</li>
            <li><span class="label">中奖次数：</span>{{ r.hit_count }}</li>
            <li><span class="label">首注命中：</span>{{ r.first_ticket_hit_count }}</li>
            <li><span class="label">总成本：</span>{{ r.total_cost }} 元</li>
            <li><span class="label">固定奖金：</span>{{ r.total_fixed_prize }} 元</li>
            <li><span class="label">浮动奖注数：</span>{{ r.float_prize_count }}</li>
            <li>
              <span class="label">奖级分布：</span>
              <span v-for="(count, tier) in r.tier_breakdown" :key="tier" class="tier-badge">
                {{ tier }}: {{ count }}
              </span>
            </li>
          </ul>
        </div>
      </div>
    </template>

    <!-- 参数优化建议 -->
    <template v-if="suggestions">
      <h2>参数优化建议</h2>
      <p class="hint">基于最近 {{ suggestions.based_on_rounds }} 期回测数据的参数优化建议。</p>
      <div class="suggestion-list">
        <div v-for="(s, i) in suggestions.suggestions" :key="i" class="suggestion-card">
          <h4>{{ s.strategy_name }} · {{ i + 1 }}</h4>
          <p class="reason">{{ s.reason }}</p>
          <div class="params-compare">
            <div class="param-box current">
              <span class="label">当前参数</span>
              <pre>{{ JSON.stringify(s.current_params, null, 2) }}</pre>
            </div>
            <div class="arrow">→</div>
            <div class="param-box suggested">
              <span class="label">建议参数</span>
              <pre>{{ JSON.stringify(s.suggested_params, null, 2) }}</pre>
            </div>
          </div>
          <div v-if="s.expected_improvement > 0" class="improvement">
            预期提升：<span class="positive">+{{ s.expected_improvement }}%</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.controls { margin-bottom: 12px; }
.strat-list { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.strat-item {
  display: inline-flex; align-items: center; gap: 4px;
  border: 1px solid #ccc; border-radius: 4px; padding: 4px 8px; font-size: 13px;
}
.row { display: flex; align-items: center; gap: 8px; }
.legend { display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; margin: 6px 0 14px; }
.legend-item { display: inline-flex; align-items: center; gap: 4px; }
.legend-item i { width: 12px; height: 12px; border-radius: 2px; display: inline-block; }
.strat-card { border: 1px solid #eee; border-radius: 6px; padding: 10px; margin: 10px 0; }
.metrics { font-size: 12px; color: #444; display: flex; flex-wrap: wrap; gap: 4px 16px; list-style: none; padding: 0; }
.metrics li { white-space: nowrap; }
.ov-table { border-collapse: collapse; font-size: 13px; margin-top: 6px; }
.ov-table th, .ov-table td { border: 1px solid #ddd; padding: 4px 10px; text-align: left; }
.hint { color: #888; font-size: 12px; }
.rank-table { border-collapse: collapse; font-size: 13px; margin: 12px 0; width: 100%; }
.rank-table th, .rank-table td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
.rank-table th { background: #f5f5f5; font-weight: 600; }
.top-rank { background: #f0f7ff; }
.rank-badge { font-size: 16px; text-align: center; }
.positive { color: #43A047; font-weight: 600; }
.negative { color: #E53935; font-weight: 600; }
.compare-charts { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 16px 0; }
.chart-card { border: 1px solid #eee; border-radius: 6px; padding: 12px; }
.chart-card h4 { margin: 0 0 8px; font-size: 14px; }
.detail-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.detail-card { border: 1px solid #eee; border-radius: 6px; padding: 12px; }
.detail-list { font-size: 12px; color: #444; list-style: none; padding: 0; margin: 8px 0 0; }
.detail-list li { margin: 4px 0; }
.detail-list .label { color: #888; }
.tier-badge {
  display: inline-block;
  background: #e3f2fd;
  color: #1976D2;
  border-radius: 3px;
  padding: 1px 6px;
  margin: 2px;
  font-size: 11px;
}
.suggestion-list { display: flex; flex-direction: column; gap: 12px; margin: 12px 0; }
.suggestion-card { border: 1px solid #e0e0e0; border-radius: 6px; padding: 12px; }
.suggestion-card h4 { margin: 0 0 8px; color: #1976D2; }
.reason { font-size: 13px; color: #555; margin: 0 0 10px; }
.params-compare { display: flex; align-items: center; gap: 12px; }
.param-box { flex: 1; background: #f9f9f9; border: 1px solid #eee; border-radius: 4px; padding: 8px; }
.param-box .label { display: block; font-size: 11px; color: #888; margin-bottom: 4px; }
.param-box pre { margin: 0; font-size: 12px; white-space: pre-wrap; }
.arrow { font-size: 20px; color: #43A047; }
.improvement { margin-top: 8px; font-size: 13px; color: #666; }
</style>
