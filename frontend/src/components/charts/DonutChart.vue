<script setup lang="ts">
import { computed } from "vue";

interface Slice {
  label: string;
  value: number;
  color: string;
}

const props = withDefaults(
  defineProps<{
    slices: Slice[];
    size?: number;
    innerRadius?: number;
  }>(),
  {
    size: 140,
    innerRadius: 0.55,
  },
);

const total = computed(() => props.slices.reduce((s, v) => s + v.value, 0));
const cx = computed(() => props.size / 2);
const cy = computed(() => props.size / 2);
const outerR = computed(() => (props.size / 2) - 4);
const innerR = computed(() => outerR.value * props.innerRadius);

function slicePath(startAngle: number, endAngle: number): string {
  const r1 = outerR.value;
  const r2 = innerR.value;
  const mid = (startAngle + endAngle) / 2;
  const gap = 0.01;

  const sa = startAngle + gap;
  const ea = endAngle - gap;
  if (ea - sa < 0.001) return "";

  const x1 = cx.value + r1 * Math.cos(sa);
  const y1 = cy.value + r1 * Math.sin(sa);
  const x2 = cx.value + r1 * Math.cos(ea);
  const y2 = cy.value + r1 * Math.sin(ea);
  const x3 = cx.value + r2 * Math.cos(ea);
  const y3 = cy.value + r2 * Math.sin(ea);
  const x4 = cx.value + r2 * Math.cos(sa);
  const y4 = cy.value + r2 * Math.sin(sa);

  const large = ea - sa > Math.PI ? 1 : 0;
  return [
    `M ${x1} ${y1}`,
    `A ${r1} ${r1} 0 ${large} 1 ${x2} ${y2}`,
    `L ${x3} ${y3}`,
    `A ${r2} ${r2} 0 ${large} 0 ${x4} ${y4}`,
    "Z",
  ].join(" ");
}

const slicesData = computed(() => {
  if (total.value === 0) return [];
  let angle = -Math.PI / 2;
  return props.slices.map((s) => {
    const start = angle;
    const sweep = (s.value / total.value) * Math.PI * 2;
    angle += sweep;
    return { ...s, startAngle: start, endAngle: start + sweep, pct: ((s.value / total.value) * 100).toFixed(1) };
  });
});
</script>

<template>
  <div class="donut-wrap">
    <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`" class="donut">
      <circle :cx="cx" :cy="cy" :r="innerR" fill="none" stroke="#e0e0e0" stroke-width="0.5" />
      <path
        v-for="(s, i) in slicesData"
        :key="i"
        :d="slicePath(s.startAngle, s.endAngle)"
        :fill="s.color"
        :stroke="s.color"
        stroke-width="0.5"
      >
        <title>{{ s.label }}: {{ s.value }} ({{ s.pct }}%)</title>
      </path>
      <text :x="cx" :y="cy + 4" text-anchor="middle" class="center-text">{{ total }}</text>
    </svg>
    <div class="legend">
      <div v-for="(s, i) in slicesData" :key="i" class="legend-item">
        <span class="dot" :style="{ background: s.color }"></span>
        <span>{{ s.label }}: {{ s.value }} <small>({{ s.pct }}%)</small></span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.donut-wrap { display: flex; align-items: center; gap: 12px; }
.donut { display: block; flex-shrink: 0; }
.center-text { font-size: 14px; font-weight: bold; fill: #333; }
.legend { font-size: 12px; color: #555; }
.legend-item { display: flex; align-items: center; gap: 4px; margin-bottom: 3px; }
.dot { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
small { color: #999; }
</style>
