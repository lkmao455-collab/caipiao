<script setup lang="ts">
import { ref, onMounted } from "vue";
import {
  runBacktest,
  listBacktests,
  deleteBacktest,
  type BacktestRecord,
  type BacktestRound,
  type BacktestSummary,
} from "../api/client";

const props = defineProps<{ token: string; profileKey: string; strategyId: string }>();

const count = ref(5);
const rounds = ref(20);
const error = ref("");
const busy = ref(false);

const rounds_out = ref<BacktestRound[]>([]);
const summary = ref<BacktestSummary | null>(null);
const history = ref<BacktestRecord[]>([]);

async function run() {
  error.value = "";
  busy.value = true;
  rounds_out.value = [];
  summary.value = null;
  try {
    const res = await runBacktest(props.token, props.profileKey, props.strategyId, count.value, rounds.value);
    rounds_out.value = res.rounds;
    summary.value = res.summary;
    await refresh();
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}

async function refresh() {
  history.value = await listBacktests(props.token);
}

async function remove(id: number, kind: string) {
  try {
    await deleteBacktest(props.token, id, kind);
    await refresh();
  } catch (e) {
    error.value = String(e);
  }
}

onMounted(refresh);
</script>

<template>
  <div class="card">
    <h2>走查式回测 · {{ profileKey }}</h2>
    <div class="row">
      <span>策略：{{ strategyId }}</span>
      <label>每期注数<input v-model.number="count" type="number" min="1" max="100" style="width: 70px" /></label>
      <label>回测期数<input v-model.number="rounds" type="number" min="1" max="300" style="width: 70px" /></label>
      <button :disabled="busy" @click="run">运行回测</button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="summary" class="summary">
      <span>总期数：{{ summary.total_rounds }}</span>
      <span>命中：{{ summary.hit_count }}</span>
      <span>首注命中：{{ summary.first_ticket_hit_count }}</span>
      <span>固定奖金：{{ summary.total_fixed_prize }}</span>
      <span>浮动奖注数：{{ summary.float_prize_count }}</span>
      <span>成本：{{ summary.total_cost }}</span>
      <span>盈亏（不含浮动）：{{ summary.profit }}</span>
    </div>
    <div v-if="summary && summary.tier_breakdown && Object.keys(summary.tier_breakdown).length" class="tiers">
      <span>奖级分布：</span>
      <span v-for="(cnt, name) in summary.tier_breakdown" :key="name" class="tier">
        {{ name }} ×{{ cnt }}
      </span>
    </div>

    <table v-if="rounds_out.length" class="rounds">
      <thead>
        <tr><th>日期</th><th>期号</th><th>命中</th><th>最佳奖级</th><th>固定奖金</th><th>浮动奖</th></tr>
      </thead>
      <tbody>
        <tr v-for="(r, i) in rounds_out" :key="i">
          <td>{{ r.target_date }}</td>
          <td>{{ r.issue }}</td>
          <td :class="{ hit: r.hit }">{{ r.hit ? "中" : "—" }}</td>
          <td>{{ r.best_tier ?? "—" }}</td>
          <td>{{ r.round_fixed_prize }}</td>
          <td>{{ r.round_float_count }}</td>
        </tr>
      </tbody>
    </table>

    <h3>历史回测记录</h3>
    <table v-if="history.length" class="history">
      <thead>
        <tr><th>类型</th><th>彩种</th><th>策略</th><th>期数/日期</th><th>命中</th><th>浮动奖</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="h in history" :key="h.kind + h.id">
          <td>{{ h.kind }}</td>
          <td>{{ h.profile_key }}</td>
          <td>{{ h.strategy_id }}</td>
          <td>{{ h.kind === "batch" ? `${h.start_date} ~ ${h.end_date}` : h.target_date }}</td>
          <td>{{ h.hit_count }}</td>
          <td>{{ h.float_prize_count }}</td>
          <td><button class="del" @click="remove(h.id, h.kind)">删除</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.summary { display: flex; gap: 16px; flex-wrap: wrap; font-size: 13px; color: #333; margin: 10px 0; }
.summary .hit, td.hit { color: #388E3C; font-weight: bold; }
.tiers { display: flex; gap: 10px; flex-wrap: wrap; font-size: 13px; margin: 4px 0 10px; align-items: center; }
.tiers .tier { background: #fff3e0; border: 1px solid #ffcc80; border-radius: 4px; padding: 2px 8px; }
.tiers .tier:first-of-type { margin-left: 6px; }
.rounds, .history { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }
.rounds th, .rounds td, .history th, .history td { border: 1px solid #eee; padding: 4px 8px; text-align: left; }
.del { color: #b00; background: none; border: 1px solid #b00; border-radius: 4px; padding: 2px 6px; cursor: pointer; }
</style>
