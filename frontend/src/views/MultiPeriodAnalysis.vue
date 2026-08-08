<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import {
  getMultiPeriodAnalysis,
  type MultiPeriodAnalysisResponse,
} from "../api/client";
import BarChart from "../components/charts/BarChart.vue";
import GroupedBarChart from "../components/charts/GroupedBarChart.vue";

const props = defineProps<{ token: string; profileKey: string }>();

const data = ref<MultiPeriodAnalysisResponse | null>(null);
const error = ref("");
const busy = ref(false);
const periods = ref(5);

async function load() {
  error.value = "";
  busy.value = true;
  try {
    data.value = await getMultiPeriodAnalysis(props.token, props.profileKey, periods.value);
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}

onMounted(load);
watch([() => props.profileKey, periods], load);

const pairChartData = computed(() => {
  if (!data.value) return [];
  return data.value.common_pairs.map((p) => ({
    label: p.pair.join("-"),
    value: p.count,
  }));
});

const consecutiveData = computed(() => {
  if (!data.value) return [];
  return data.value.consecutive_appearances.slice(0, 10).map((c) => ({
    label: String(c.number),
    value: c.appearances,
  }));
});

const zoneChartData = computed(() => {
  if (!data.value) return [];
  return data.value.zone_history.map((z) => ({
    name: z.date.slice(5),
    color: "#1976D2",
    values: [z.zone1, z.zone2, z.zone3],
  }));
});

const zoneCategories = computed(() => ["区1(1-11)", "区2(12-22)", "区3(23-33)"]);
</script>

<template>
  <div class="multi-period">
    <h3>多期联合分析</h3>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="busy">加载中…</p>

    <div class="controls" v-if="!busy">
      <label>
        分析期数：
        <select v-model.number="periods">
          <option :value="3">3期</option>
          <option :value="5">5期</option>
          <option :value="10">10期</option>
          <option :value="15">15期</option>
        </select>
      </label>
    </div>

    <template v-if="data && !busy">
      <!-- 共现分析 -->
      <div class="section">
        <h4>号码共现分析</h4>
        <p class="hint">统计最近 {{ data.periods_analyzed }} 期中，哪些号码经常一起出现</p>
        <BarChart :items="pairChartData" :height="120" color="#8E24AA" />
      </div>

      <!-- 连续出现 -->
      <div class="section">
        <h4>连续出现号码</h4>
        <p class="hint">在多期中频繁出现的号码</p>
        <BarChart :items="consecutiveData" :height="120" color="#43A047" />
        <div class="consecutive-list">
          <div
            v-for="c in data.consecutive_appearances.slice(0, 8)"
            :key="c.number"
            :class="['consecutive-item', { streak: c.streak }]"
          >
            <span class="num">{{ c.number }}</span>
            <span class="count">{{ c.appearances }}期</span>
            <span v-if="c.streak" class="streak-badge">连续</span>
          </div>
        </div>
      </div>

      <!-- 区间轮动 -->
      <div class="section">
        <h4>区间轮动分析</h4>
        <p class="hint">分析号码在三个区间的分布变化趋势</p>
        <GroupedBarChart
          v-if="zoneChartData.length"
          :categories="zoneCategories"
          :series="zoneChartData"
        />
      </div>

      <!-- 组合建议 -->
      <div class="section suggestions">
        <h4>组合预测建议</h4>
        <div class="suggestion-list">
          <div v-for="(s, i) in data.suggestions" :key="i" class="suggestion-card">
            <div class="sug-header">
              <span class="sug-strategy">{{ s.strategy }}</span>
            </div>
            <div class="sug-numbers">
              <span v-for="n in s.numbers" :key="n" class="num">{{ n }}</span>
            </div>
            <p class="sug-reason">{{ s.reason }}</p>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.multi-period { padding: 12px; }
.section { margin-bottom: 20px; }
.section h4 { margin: 0 0 6px; font-size: 15px; color: #333; }
.hint { font-size: 12px; color: #888; margin: 0 0 10px; }
.controls { margin-bottom: 12px; }
.controls label { font-size: 13px; color: #555; }
.controls select { padding: 4px 8px; border: 1px solid #ccc; border-radius: 4px; }
.consecutive-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.consecutive-item {
  display: flex; align-items: center; gap: 6px;
  background: #f5f5f5; padding: 6px 10px; border-radius: 4px;
}
.consecutive-item.streak { background: #e8f5e9; }
.consecutive-item .num { font-weight: 600; font-size: 14px; }
.consecutive-item .count { font-size: 12px; color: #666; }
.streak-badge {
  font-size: 10px; background: #43A047; color: #fff;
  padding: 1px 5px; border-radius: 3px;
}
.suggestions h4 { margin-bottom: 12px; }
.suggestion-list { display: flex; flex-direction: column; gap: 12px; }
.suggestion-card {
  border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px;
}
.sug-header { margin-bottom: 8px; }
.sug-strategy { font-size: 14px; font-weight: 600; color: #1976D2; }
.sug-numbers { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.sug-numbers .num {
  display: inline-block; width: 32px; height: 32px; line-height: 32px;
  text-align: center; background: #1976D2; color: #fff; border-radius: 50%;
  font-weight: 600; font-size: 14px;
}
.sug-reason { font-size: 12px; color: #666; margin: 0; }
</style>
