<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  data: { date: string; value: number }[];
  color?: string;
  height?: number;
  showDots?: boolean;
  title?: string;
}>();

const width = computed(() => Math.max(300, props.data.length * 28));
const heightVal = computed(() => props.height ?? 150);
const lineColor = computed(() => props.color ?? "#1976D2");

const chartData = computed(() => {
  if (!props.data.length) return { points: "", dots: [], minY: 0, maxY: 1, labels: [] };
  const values = props.data.map((d) => d.value);
  const minY = Math.min(...values);
  const maxY = Math.max(...values);
  const range = maxY - minY || 1;
  const padding = 20;
  const chartWidth = width.value - padding * 2;
  const chartHeight = heightVal.value - padding * 2;

  const points = props.data.map((d, i) => {
    const x = padding + (i / (props.data.length - 1 || 1)) * chartWidth;
    const y = padding + chartHeight - ((d.value - minY) / range) * chartHeight;
    return `${x},${y}`;
  });

  const dots = props.data.map((d, i) => {
    const x = padding + (i / (props.data.length - 1 || 1)) * chartWidth;
    const y = padding + chartHeight - ((d.value - minY) / range) * chartHeight;
    return { x, y, value: d.value, date: d.date };
  });

  const labels = props.data.filter((_, i) => i % Math.ceil(props.data.length / 8) === 0).map((d, i) => {
    const idx = props.data.indexOf(d);
    const x = padding + (idx / (props.data.length - 1 || 1)) * chartWidth;
    return { x, label: d.date.slice(5) };
  });

  return { points: points.join(" "), dots, minY, maxY, labels };
});
</script>

<template>
  <div class="trend-chart">
    <h5 v-if="title" class="chart-title">{{ title }}</h5>
    <svg :width="width" :height="heightVal" class="chart-svg">
      <!-- 网格线 -->
      <line
        v-for="i in 4"
        :key="'grid-' + i"
        :x1="20"
        :x2="width - 20"
        :y1="20 + ((heightVal - 40) / 4) * i"
        :y2="20 + ((heightVal - 40) / 4) * i"
        stroke="#f0f0f0"
        stroke-width="1"
      />
      <!-- Y轴标签 -->
      <text
        v-for="i in 5"
        :key="'ylabel-' + i"
        :x="16"
        :y="20 + ((heightVal - 40) / 4) * (i - 1) + 4"
        text-anchor="end"
        font-size="10"
        fill="#999"
      >
        {{ Math.round(chartData.maxY - ((chartData.maxY - chartData.minY) / 4) * (i - 1)) }}
      </text>
      <!-- X轴标签 -->
      <text
        v-for="label in chartData.labels"
        :key="'xlabel-' + label.label"
        :x="label.x"
        :y="heightVal - 4"
        text-anchor="middle"
        font-size="10"
        fill="#999"
      >
        {{ label.label }}
      </text>
      <!-- 折线 -->
      <polyline
        v-if="chartData.points"
        :points="chartData.points"
        fill="none"
        :stroke="lineColor"
        stroke-width="2"
        stroke-linejoin="round"
        stroke-linecap="round"
      />
      <!-- 数据点 -->
      <template v-if="showDots !== false">
        <circle
          v-for="(dot, i) in chartData.dots"
          :key="'dot-' + i"
          :cx="dot.x"
          :cy="dot.y"
          r="3"
          :fill="lineColor"
          stroke="#fff"
          stroke-width="1.5"
        >
          <title>{{ dot.date }}: {{ dot.value }}</title>
        </circle>
      </template>
    </svg>
  </div>
</template>

<style scoped>
.trend-chart { display: inline-block; }
.chart-title { margin: 0 0 6px; font-size: 13px; color: #666; }
.chart-svg { display: block; }
</style>
