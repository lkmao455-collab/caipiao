<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  data: { label: string; value: number; color?: string }[];
  height?: number;
}>();

const h = computed(() => props.height ?? 200);

// 计算圆柱体属性
const cylinders = computed(() => {
  const maxVal = Math.max(...props.data.map((d) => d.value), 1);
  return props.data.map((d, i) => ({
    label: d.label,
    value: d.value,
    height: (d.value / maxVal) * (h.value - 40),
    color: d.color ?? `hsl(${210 + i * 15}, 70%, 55%)`,
    x: (i / props.data.length) * 100,
  }));
});
</script>

<template>
  <div class="chart3d-container">
    <svg :viewBox="`0 0 100 ${h}`" preserveAspectRatio="none">
      <!-- 背景网格 -->
      <g opacity="0.15">
        <line
          v-for="i in 5"
          :key="`grid-${i}`"
          x1="0"
          :y1="(i / 5) * h"
          x2="100"
          :y2="(i / 5) * h"
          stroke="#666"
          stroke-width="0.2"
          stroke-dasharray="1,1"
        />
      </g>

      <!-- 圆柱体 -->
      <g v-for="(c, i) in cylinders" :key="`col-${i}`">
        <!-- 3D 底座 -->
        <ellipse
          :cx="c.x + 50 / cylinders.length / 2"
          :cy="h - 5"
          :rx="50 / cylinders.length / 2 - 1"
          :ry="3"
          :fill="c.color"
          opacity="0.3"
        />

        <!-- 圆柱体主体 -->
        <rect
          :x="c.x + 50 / cylinders.length / 4"
          :y="h - c.height - 10"
          :width="50 / cylinders.length / 2"
          :height="c.height"
          :fill="`url(#cylGrad${i})`"
          rx="1"
          class="cylinder"
          :style="{ animationDelay: `${i * 0.1}s` }"
        />

        <!-- 3D 顶部 -->
        <ellipse
          :cx="c.x + 50 / cylinders.length / 2"
          :cy="h - c.height - 10"
          :rx="50 / cylinders.length / 2 - 1"
          :ry="3"
          :fill="c.color"
        />

        <!-- 数值标签 -->
        <text
          :x="c.x + 50 / cylinders.length / 2"
          :y="h - c.height - 18"
          text-anchor="middle"
          font-size="2.5"
          fill="#333"
          font-weight="600"
        >
          {{ c.value }}
        </text>

        <!-- 底部标签 -->
        <text
          :x="c.x + 50 / cylinders.length / 2"
          :y="h"
          text-anchor="middle"
          font-size="2.2"
          fill="#666"
        >
          {{ c.label }}
        </text>

        <!-- 渐变定义 -->
        <defs>
          <linearGradient :id="`cylGrad${i}`" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" :stop-color="c.color" stop-opacity="0.8" />
            <stop offset="50%" :stop-color="c.color" stop-opacity="1" />
            <stop offset="100%" :stop-color="c.color" stop-opacity="0.6" />
          </linearGradient>
        </defs>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.chart3d-container {
  width: 100%;
}

svg {
  width: 100%;
}

.cylinder {
  animation: cylGrow 0.6s ease-out both;
}

@keyframes cylGrow {
  from {
    transform: scaleY(0);
    transform-origin: bottom;
  }
  to {
    transform: scaleY(1);
    transform-origin: bottom;
  }
}
</style>
