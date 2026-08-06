<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import {
  getStats,
  fetchProfileData,
  type ProfileStats,
  type GroupStats,
  type FetchResult,
} from "../api/client";

const props = defineProps<{ token: string; profileKey: string }>();

const stats = ref<ProfileStats | null>(null);
const error = ref("");
const busy = ref(false);
const fetching = ref(false);
const fetchMsg = ref("");
const lastFetch = ref<FetchResult | null>(null);
const needsBootstrap = ref(false);
// 每个组件实例仅自动引导一次，避免重复触发网络请求
const bootstrapped = ref(false);

async function load() {
  error.value = "";
  busy.value = true;
  try {
    stats.value = await getStats(props.token, props.profileKey);
    needsBootstrap.value = (stats.value?.total_records ?? 0) === 0;
    // 首次加载自动引导：本地无数据时自动拉取一次全量历史
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

// 切换彩种时重置引导状态，新彩种若为空同样会自动引导一次
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
        <div class="bars">
          <div
            v-for="n in (stats.groups[key as string].hi - stats.groups[key as string].lo + 1)"
            :key="n"
            class="bar-col"
            :title="`${stats.groups[key as string].lo + n - 1}: ${stats.groups[key as string].frequency[String(stats.groups[key as string].lo + n - 1)] ?? 0}`"
          >
            <div
              class="bar"
              :style="{
                height: ((stats.groups[key as string].frequency[String(stats.groups[key as string].lo + n - 1)] ?? 0) / maxFreq(stats.groups[key as string]) * 100) + '%',
                background: stats.groups[key as string].color,
              }"
            ></div>
            <span class="bar-label">{{ stats.groups[key as string].lo + n - 1 }}</span>
          </div>
        </div>
        <div class="meta">
          <span>热号：{{ stats.groups[key as string].hot.join(", ") }}</span>
          <span>冷号：{{ stats.groups[key as string].cold.join(", ") }}</span>
        </div>
      </div>

      <h3>综合</h3>
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
.bars { display: flex; align-items: flex-end; gap: 2px; height: 120px; overflow-x: auto; }
.bar-col { display: flex; flex-direction: column; align-items: center; justify-content: flex-end; min-width: 14px; }
.bar { width: 12px; border-radius: 2px 2px 0 0; min-height: 1px; }
.bar-label { font-size: 9px; color: #888; margin-top: 2px; }
.meta { font-size: 12px; color: #555; display: flex; gap: 16px; margin-top: 4px; }
.summary { font-size: 13px; color: #444; line-height: 1.7; }
</style>
