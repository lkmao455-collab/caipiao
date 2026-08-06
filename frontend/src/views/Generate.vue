<script setup lang="ts">
import { ref, watch, onMounted } from "vue";
import {
  generate,
  getStats,
  fetchProfileData,
  type Ticket,
  type ProfileStats,
  type FetchResult,
} from "../api/client";

const props = defineProps<{
  token: string;
  profileKey: string;
  strategyId: string;
  postFilters?: { name: string; params: Record<string, unknown> }[];
}>();

const count = ref(5);
const tickets = ref<Ticket[]>([]);
const filteredCount = ref(0);
const error = ref("");
const busy = ref(false);

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
    // 统计接口异常时不阻断生成，交由生成接口报错
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
  tickets.value = [];
  try {
    const res = await generate(
      props.token,
      props.profileKey,
      props.strategyId,
      count.value,
      props.postFilters ?? [],
    );
    tickets.value = res.tickets;
    filteredCount.value = res.filtered_count;
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}

onMounted(loadStats);

// 切换彩种/策略时重置结果，并重新检查空数据引导
watch(
  () => [props.profileKey, props.strategyId],
  () => {
    tickets.value = [];
    error.value = "";
    bootstrapped.value = false;
    needsBootstrap.value = false;
    loadStats();
  },
);
</script>

<template>
  <div class="card">
    <h2>生成号码</h2>
    <div class="row">
      <span>彩种：{{ profileKey }} / 策略：{{ strategyId }}</span>
      <input v-model.number="count" type="number" min="1" max="100" style="width: 80px" />
      <button :disabled="busy || needsBootstrap" @click="run">生成</button>
    </div>

    <div v-if="needsBootstrap" class="banner">
      <p>本地暂无该彩种历史数据，生成需要先有开奖历史。已为您自动拉取全量历史；若失败可手动重试：</p>
      <div class="banner-actions">
        <button :disabled="fetching" @click="refresh('all')">拉取全量历史</button>
        <button :disabled="fetching" @click="refresh('latest')">仅拉取最新</button>
        <span v-if="fetching">拉取中…</span>
      </div>
    </div>
    <p v-if="fetchMsg" class="hint">{{ fetchMsg }}</p>

    <p v-if="props.postFilters && props.postFilters.length" class="hint">
      已应用后过滤（{{ props.postFilters[0].params && Object.keys(props.postFilters[0].params).length }} 项）
    </p>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="tickets.length" class="hint">
      原始 {{ count }} 注 → 过滤后 {{ filteredCount }} 注
    </p>
    <div v-for="(t, i) in tickets" :key="i" class="ticket">{{ JSON.stringify(t) }}</div>
  </div>
</template>

<style scoped>
.banner {
  background: #fff8e1;
  border: 1px solid #ffe082;
  border-radius: 6px;
  padding: 10px 12px;
  margin: 8px 0;
  font-size: 13px;
  color: #6d4c00;
}
.banner-actions { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
.hint { color: #888; font-size: 12px; }
</style>
