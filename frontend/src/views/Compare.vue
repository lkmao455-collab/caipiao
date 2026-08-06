<script setup lang="ts">
import { ref, onMounted, computed, watch } from "vue";
import {
  listStrategies,
  getStats,
  generate,
  type Strategy,
  type ProfileStats,
  type Ticket,
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
        <button :disabled="busy" @click="run">比较生成</button>
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
</style>
