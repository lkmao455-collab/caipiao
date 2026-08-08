<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    data: { label: string; values: number[]; colors?: string[] }[];
    seriesNames?: string[];
    height?: number;
    animate?: boolean;
  }>(),
  { height: 200, animate: true },
);

const h = computed(() => props.height);
const chartPad = 30;

const seriesColors = [
  ["#1976D2", "#42A5F5"],
  ["#388E3C", "#66BB6A"],
  ["#F57C00", "#FFB74D"],
  ["#D32F2F", "#EF5350"],
  ["#7B1FA2", "#AB47BC"],
];

const maxVal = computed(() => {
  let m = 0;
  for (const d of props.data) {
    for (const v of d.values) {
      if (v > m) m = v;
    }
  }
  return m || 1;
});

const barWidth = computed(() => {
  const n = props.data.length;
  const groupW = (100 - chartPad * 2) / n;
  return Math.min(groupW * 0.7, 8);
});

const bars = computed(() => {
  const n = props.data.length;
  const groupW = (100 - chartPad * 2) / n;
  const result: {
    x: number;
    y: number;
    w: number;
    h: number;
    color: string;
    value: number;
    label: string;
    series: number;
    delay: number;
  }[] = [];

  props.data.forEach((d, di) => {
    const groupX = chartPad + di * groupW;
    const bw = barWidth.value;
    const gap = 1;

    d.values.forEach((v, vi) => {
      const barH = (v / maxVal.value) * (h.value - chartPad * 2);
      const colors = d.colors ?? seriesColors[vi % seriesColors.length];
      result.push({
        x: groupX + vi * (bw + gap),
        y: h.value - chartPad - barH,
        w: bw,
        h: barH,
        color: colors[vi % colors.length],
        value: v,
        label: d.label,
        series: vi,
        delay: di * 0.05 + vi * 0.1,
      });
    });
  });

  return result;
});
</script>

<template>
  <div class="animated-bar-chart">
    <svg :viewBox="`0 0 100 ${h}`" preserveAspectRatio="none">
      <!-- Y 轴网格 -->
      <g opacity="0.15">
        <line
          v-for="i in 5"
          :key="i"
          :x1="chartPad"
          :y1="(i / 5) * (h - chartPad * 2) + chartPad"
          x2="98"
          :y2="(i / 5) * (h - chartPad * 2) + chartPad"
          stroke="#666"
          stroke-width="0.2"
          stroke-dasharray="1,1"
        />
      </g>

      <!-- 柱状图 -->
      <g v-for="(bar, i) in bars" :key="`bar-${i}`">
        <!-- 柱体 -->
        <rect
          :x="bar.x"
          :y="bar.y"
          :width="bar.w"
          :height="bar.h"
          :fill="bar.color"
          rx="0.5"
          :class="animate ? 'animated-bar' : ''"
          :style="{ animationDelay: `${bar.delay}s` }"
        />

        <!-- 数值标签 -->
        <text
          :x="bar.x + bar.w / 2"
          :y="bar.y - 1.5"
          text-anchor="middle"
          font-size="2"
          fill="#333"
          font-weight="500"
        >
          {{ bar.value }}
        </text>
      </g>

      <!-- X 轴标签 -->
      <g>
        <text
          v-for="(d, i) in data"
          :key="`label-${i}`"
          :x="chartPad + i * ((100 - chartPad * 2) / data.length) + ((100 - chartPad * 2) / data.length) / 2"
          :y="h - 5"
          text-anchor="middle"
          font-size="2.2"
          fill="#666"
        >
          {{ d.label }}
        </text>
      </g>
    </svg>

    <!-- 图例 -->
    <div v-if="seriesNames?.length" class="legend">
      <div
        v-for="(name, i) in seriesNames"
        :key="name"
        class="legend-item"
      >
        <span
          class="dot"
          :style="{ background: seriesColors[i % seriesColors.length][0] }"
        />
        {{ name }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.animated-bar-chart {
  width: 100%;
}

svg {
  width: 100%;
}

.animated-bar {
  animation: barGrow 0.5s ease-out both;
}

@keyframes barGrow {
  from {
    transform: scaleY(0);
    transform-origin: bottom;
  }
  to {
    transform: scaleY(1);
    transform-origin: bottom;
  }
}

.legend {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-top: 8px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #666;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
</style>
