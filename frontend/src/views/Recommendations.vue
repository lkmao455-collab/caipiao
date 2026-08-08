<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import { getRecommendations, type Recommendation } from "../api/client";

const props = defineProps<{
  token: string;
  profileKey: string;
}>();

const emit = defineEmits<{
  (e: "select", strategyId: string): void;
}>();

const recommendations = ref<Recommendation[]>([]);
const error = ref("");
const busy = ref(false);

async function load() {
  error.value = "";
  busy.value = true;
  try {
    recommendations.value = await getRecommendations(props.token, props.profileKey);
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}

onMounted(load);
watch(() => props.profileKey, load);

function getScoreColor(score: number): string {
  if (score >= 80) return "#43A047";
  if (score >= 60) return "#FB8C00";
  if (score >= 40) return "#1976D2";
  return "#9E9E9E";
}

function getTagClass(tag: string): string {
  const map: Record<string, string> = {
    "常用": "tag-common",
    "高命中": "tag-hot",
    "盈利": "tag-profit",
    "收藏": "tag-fav",
    "可配置": "tag-config",
    "智能": "tag-ml",
  };
  return map[tag] || "tag-default";
}

function selectStrategy(strategyId: string) {
  emit("select", strategyId);
}
</script>

<template>
  <div class="recommendations">
    <h3>智能推荐</h3>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="busy" class="loading">分析中…</p>

    <template v-if="recommendations.length && !busy">
      <p class="hint">基于您的使用历史和回测结果，为您推荐以下策略：</p>
      <div class="rec-list">
        <div
          v-for="(rec, i) in recommendations"
          :key="rec.strategy_id"
          class="rec-card"
          :class="{ top: i === 0 }"
        >
          <div class="rec-header">
            <span class="rank">#{{ i + 1 }}</span>
            <span class="name">{{ rec.strategy_name }}</span>
            <span class="score" :style="{ color: getScoreColor(rec.score) }">
              {{ rec.score.toFixed(0) }}分
            </span>
          </div>
          <div class="rec-tags">
            <span
              v-for="tag in rec.tags"
              :key="tag"
              :class="['tag', getTagClass(tag)]"
            >
              {{ tag }}
            </span>
          </div>
          <p class="reason">{{ rec.reason }}</p>
          <button class="use-btn" @click="selectStrategy(rec.strategy_id)">
            使用此策略
          </button>
        </div>
      </div>
    </template>

    <p v-else-if="!busy && !error" class="empty">暂无推荐数据</p>
  </div>
</template>

<style scoped>
.recommendations { padding: 12px; }
.hint { font-size: 13px; color: #666; margin-bottom: 12px; }
.loading { color: #888; }
.rec-list { display: flex; flex-direction: column; gap: 10px; }
.rec-card {
  border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px;
  transition: box-shadow 0.2s;
}
.rec-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
.rec-card.top { border-color: #43A047; background: #f8fff8; }
.rec-header { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.rank {
  font-size: 14px; font-weight: 700; color: #888;
  min-width: 24px; text-align: center;
}
.rec-card.top .rank { color: #43A047; }
.name { font-size: 15px; font-weight: 600; color: #333; flex: 1; }
.score { font-size: 16px; font-weight: 700; }
.rec-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
.tag {
  font-size: 11px; padding: 2px 6px; border-radius: 3px;
  background: #f5f5f5; color: #666;
}
.tag-common { background: #e3f2fd; color: #1565c0; }
.tag-hot { background: #ffebee; color: #c62828; }
.tag-profit { background: #e8f5e9; color: #2e7d32; }
.tag-fav { background: #fff3e0; color: #e65100; }
.tag-config { background: #f3e5f5; color: #7b1fa2; }
.tag-ml { background: #e0f7fa; color: #00695c; }
.reason { font-size: 12px; color: #888; margin: 4px 0 8px; }
.use-btn {
  font-size: 12px; padding: 5px 12px; border: 1px solid #1976D2;
  background: #fff; color: #1976D2; border-radius: 4px; cursor: pointer;
}
.use-btn:hover { background: #e3f2fd; }
.empty { color: #999; font-size: 13px; text-align: center; }
</style>
