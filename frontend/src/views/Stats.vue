<script setup lang="ts">
import { ref, onMounted } from "vue";
import { getStats, type ProfileStats, type GroupStats } from "../api/client";

const props = defineProps<{ token: string; profileKey: string }>();

const stats = ref<ProfileStats | null>(null);
const error = ref("");
const busy = ref(false);

async function load() {
  error.value = "";
  busy.value = true;
  try {
    stats.value = await getStats(props.token, props.profileKey);
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}

onMounted(load);

function maxFreq(g: GroupStats): number {
  const vals = Object.values(g.frequency);
  return vals.length ? Math.max(...vals) : 1;
}
</script>

<template>
  <div class="card">
    <h2>统计分析 · {{ profileKey }}</h2>
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
.group-block { margin-bottom: 18px; }
.bars { display: flex; align-items: flex-end; gap: 2px; height: 120px; overflow-x: auto; }
.bar-col { display: flex; flex-direction: column; align-items: center; justify-content: flex-end; min-width: 14px; }
.bar { width: 12px; border-radius: 2px 2px 0 0; min-height: 1px; }
.bar-label { font-size: 9px; color: #888; margin-top: 2px; }
.meta { font-size: 12px; color: #555; display: flex; gap: 16px; margin-top: 4px; }
.summary { font-size: 13px; color: #444; line-height: 1.7; }
</style>
