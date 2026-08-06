<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import {
  runBacktest,
  listBacktests,
  deleteBacktest,
  getBacktest,
  getStats,
  fetchProfileData,
  type BacktestRecord,
  type BacktestRound,
  type BacktestSummary,
  type BacktestTicket,
  type ProfileStats,
  type FetchResult,
} from "../api/client";

const props = defineProps<{ token: string; profileKey: string; strategyId: string }>();

const count = ref(5);
const rounds = ref(20);
const error = ref("");
const busy = ref(false);

const rounds_out = ref<BacktestRound[]>([]);
const summary = ref<BacktestSummary | null>(null);
const history = ref<BacktestRecord[]>([]);

const detail = ref<{ id: number; kind: string; data: Record<string, unknown> | null }>({
  id: 0,
  kind: "",
  data: null,
});
const detailTickets = ref<BacktestTicket[]>([]);
const detailLoading = ref(false);

// 空数据引导
const needsBootstrap = ref(false);
const bootstrapped = ref(false);
const fetching = ref(false);
const fetchMsg = ref("");
const lastFetch = ref<FetchResult | null>(null);

async function loadStats() {
  try {
    const s: ProfileStats = await getStats(props.token, props.profileKey);
    needsBootstrap.value = (s.total_records ?? 0) === 0;
    // 首次加载自动引导：本地无历史时自动拉取一次全量历史
    if (needsBootstrap.value && !bootstrapped.value) {
      bootstrapped.value = true;
      await refresh("all");
    }
  } catch {
    // 统计接口异常时不阻断回测，交由回测接口报错
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
    await loadStats();
  } catch (e) {
    fetchMsg.value = String(e);
  } finally {
    fetching.value = false;
  }
}

async function run() {
  error.value = "";
  busy.value = true;
  rounds_out.value = [];
  summary.value = null;
  try {
    const res = await runBacktest(props.token, props.profileKey, props.strategyId, count.value, rounds.value);
    rounds_out.value = res.rounds;
    summary.value = res.summary;
    await refreshHistory();
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}

async function refreshHistory() {
  history.value = await listBacktests(props.token);
  detail.value = { id: 0, kind: "", data: null };
  detailTickets.value = [];
}

async function remove(id: number, kind: string) {
  try {
    await deleteBacktest(props.token, id, kind);
    await refreshHistory();
  } catch (e) {
    error.value = String(e);
  }
}

async function openDetail(h: BacktestRecord) {
  error.value = "";
  detailLoading.value = true;
  detail.value = { id: h.id, kind: h.kind, data: null };
  detailTickets.value = [];
  try {
    const data = await getBacktest(props.token, h.id, h.kind);
    detail.value = { id: h.id, kind: h.kind, data };
    detailTickets.value = (data.tickets as BacktestTicket[]) || [];
  } catch (e) {
    error.value = String(e);
  } finally {
    detailLoading.value = false;
  }
}

function closeDetail() {
  detail.value = { id: 0, kind: "", data: null };
  detailTickets.value = [];
}

watch(
  () => [props.profileKey, props.strategyId],
  () => {
    bootstrapped.value = false;
    needsBootstrap.value = false;
    loadStats();
  }
);

onMounted(loadStats);
</script>

<template>
  <div class="card">
    <h2>走查式回测 · {{ profileKey }}</h2>
    <div v-if="needsBootstrap" class="banner">
      <div class="banner-text">
        本地暂无历史数据，回测前请先拉取开奖数据。
      </div>
      <div class="banner-actions">
        <button :disabled="fetching" @click="refresh('all')">拉取全量历史</button>
        <button :disabled="fetching" @click="refresh('latest')">仅拉取最新</button>
        <span v-if="fetching" class="banner-loading">拉取中…</span>
        <span v-else-if="fetchMsg" class="banner-msg">{{ fetchMsg }}</span>
      </div>
    </div>

    <div class="row">
      <span>策略：{{ strategyId }}</span>
      <label>每期注数<input v-model.number="count" type="number" min="1" max="100" style="width: 70px" /></label>
      <label>回测期数<input v-model.number="rounds" type="number" min="1" max="300" style="width: 70px" /></label>
      <button :disabled="busy || needsBootstrap" @click="run">运行回测</button>
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
          <td>
            <button class="det" @click="openDetail(h)">详情</button>
            <button class="del" @click="remove(h.id, h.kind)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="detail.data" class="detail">
      <div class="detail-head">
        <strong>回测详情 #{{ detail.id }}（{{ detail.kind }}）</strong>
        <button class="det" @click="closeDetail">关闭</button>
      </div>
      <div v-if="detailLoading">加载中…</div>
      <template v-else>
        <div v-if="detail.kind === 'single'" class="single-meta">
          <span>期号：{{ (detail.data as any).issue }}</span>
          <span>成本：{{ (detail.data as any).total_cost }}</span>
          <span>固定奖金：{{ (detail.data as any).total_fixed_prize }}</span>
          <span>浮动奖：{{ (detail.data as any).float_prize_count }}</span>
          <span>盈亏：{{ (detail.data as any).profit }}</span>
        </div>
        <table v-if="detail.kind === 'single' && detailTickets.length" class="tickets">
          <thead>
            <tr><th>#</th><th>号码</th><th>命中数</th><th>奖级</th><th>奖金</th></tr>
          </thead>
          <tbody>
            <tr v-for="t in detailTickets" :key="t.ticket_index">
              <td>{{ t.ticket_index }}<span v-if="t.is_first">（首注）</span></td>
              <td>{{ Object.entries(t.groups).map(([k, v]) => `${k}:${v.join(',')}`).join(' ') }}</td>
              <td>{{ Object.entries(t.hits).map(([k, v]) => `${k}:${v}`).join(' ') }}</td>
              <td :class="{ win: t.prize_name !== '未中奖' }">{{ t.prize_name }}</td>
              <td>{{ t.prize_amount == null ? '浮动' : t.prize_amount }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else-if="detail.kind === 'batch'" class="batch-meta">
          <span>总期数：{{ (detail.data as any).total_rounds }}</span>
          <span>首注命中：{{ (detail.data as any).first_ticket_hit_count }}</span>
          <span>固定奖金：{{ (detail.data as any).total_fixed_prize }}</span>
          <span>浮动奖：{{ (detail.data as any).float_prize_count }}</span>
          <span>盈亏：{{ (detail.data as any).profit }}</span>
          <div v-if="(detail.data as any).ticket_index_hits" class="idx-hits">
            各注位命中期数：<span v-for="(c, i) in (detail.data as any).ticket_index_hits" :key="i">{{ i }}:{{ c }} </span>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.banner { background: #fff8e1; border: 1px solid #ffd54f; border-radius: 6px; padding: 10px 12px; margin: 8px 0; }
.banner-text { font-size: 13px; color: #795548; margin-bottom: 8px; }
.banner-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.banner-actions button { border: 1px solid #f9a825; background: #fff; color: #f57f17; border-radius: 4px; padding: 4px 10px; cursor: pointer; }
.banner-actions button:disabled { opacity: 0.5; cursor: not-allowed; }
.banner-loading { font-size: 13px; color: #888; }
.banner-msg { font-size: 13px; color: #555; }
.row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.summary { display: flex; gap: 16px; flex-wrap: wrap; font-size: 13px; color: #333; margin: 10px 0; }
.summary .hit, td.hit { color: #388E3C; font-weight: bold; }
.tiers { display: flex; gap: 10px; flex-wrap: wrap; font-size: 13px; margin: 4px 0 10px; align-items: center; }
.tiers .tier { background: #fff3e0; border: 1px solid #ffcc80; border-radius: 4px; padding: 2px 8px; }
.tiers .tier:first-of-type { margin-left: 6px; }
.rounds, .history { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }
.rounds th, .rounds td, .history th, .history td { border: 1px solid #eee; padding: 4px 8px; text-align: left; }
.del { color: #b00; background: none; border: 1px solid #b00; border-radius: 4px; padding: 2px 6px; cursor: pointer; }
.det { color: #1565c0; background: none; border: 1px solid #1565c0; border-radius: 4px; padding: 2px 6px; cursor: pointer; margin-right: 4px; }
.detail { margin-top: 14px; border: 1px solid #ddd; border-radius: 6px; padding: 10px; background: #fafafa; }
.detail-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.single-meta, .batch-meta { display: flex; gap: 14px; flex-wrap: wrap; font-size: 13px; margin-bottom: 8px; }
.idx-hits { width: 100%; color: #555; }
.tickets { width: 100%; border-collapse: collapse; font-size: 13px; }
.tickets th, .tickets td { border: 1px solid #eee; padding: 4px 8px; text-align: left; vertical-align: top; }
.tickets td.win { color: #388E3C; font-weight: bold; }
</style>
