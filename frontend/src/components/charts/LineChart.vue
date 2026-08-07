<script setup lang="ts">
import { computed } from "vue";

interface DataPoint {
  label: string;
  value: number;
}

interface Series {
  name: string;
  color: string;
  data: DataPoint[];
}

const props = withDefaults(
  defineProps<{
    series: Series[];
    height?: number;
    width?: number;
    pad?: number;
    showDots?: boolean;
    smooth?: boolean;
  }>(),
  {
    height: 160,
    width: 400,
    pad: 30,
    showDots: true,
    smooth: true,
  },
);

const allLabels = computed(() => {
  const labels = new Set<string>();
  for (const s of props.series) {
    for (const p of s.data) labels.add(p.label);
  }
  return Array.from(labels);
});

const chartW = computed(() => Math.max(props.width, allLabels.value.length * 30 + props.pad * 2));
const chartH = computed(() => props.height);

const xScale = (i: number) => props.pad + (i / Math.max(allLabels.value.length - 1, 1)) * (chartW.value - props.pad * 2);
const yScale = (v: number, maxVal: number) => chartH.value - props.pad - (v / Math.max(maxVal, 1)) * (chartH.value - props.pad * 2);

const seriesMax = computed(() => {
  let m = 0;
  for (const s of props.series) {
    for (const p of s.data) m = Math.max(m, p.value);
  }
  return m > 0 ? m : 1;
});

const gridLines = computed(() => {
  const lines: { y: number; label: string }[] = [];
  const maxVal = seriesMax.value;
  const step = Math.ceil(maxVal / 5);
  for (let v = 0; v <= maxVal; v += step || 1) {
    lines.push({ y: yScale(v, maxVal), label: String(v) });
  }
  return lines;
});

function buildPath(data: DataPoint[], maxVal: number): string {
  const points = data.map((p, i) => {
    const idx = allLabels.value.indexOf(p.label);
    return { x: xScale(idx >= 0 ? idx : i), y: yScale(p.value, maxVal) };
  });
  if (points.length === 0) return "";
  if (!props.smooth || points.length < 3) {
    return points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  }
  let d = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const curr = points[i];
    const cpx = (prev.x + curr.x) / 2;
    d += ` C ${cpx} ${prev.y}, ${cpx} ${curr.y}, ${curr.x} ${curr.y}`;
  }
  return d;
}
</script>

<template>
  <div class="line-chart-scroll">
    <svg :width="chartW" :height="chartH" :viewBox="`0 0 ${chartW} ${chartH}`" class="line-chart">
      <g v-for="(line, i) in gridLines" :key="i">
        <line :x1="pad" :y1="line.y" :x2="chartW - pad" :y2="line.y" stroke="#e0e0e0" stroke-width="0.5" />
        <text :x="pad - 4" :y="line.y + 3" text-anchor="end" class="axis-label">{{ line.label }}</text>
      </g>
      <g v-for="(label, i) in allLabels" :key="'lbl-' + i">
        <text
          v-if="i % Math.ceil(allLabels.length / 10) === 0 || allLabels.length <= 10"
          :x="xScale(i)"
          :y="chartH - 4"
          text-anchor="middle"
          class="axis-label"
        >{{ label }}</text>
      </g>
      <g v-for="(s, si) in series" :key="si">
        <path :d="buildPath(s.data, seriesMax)" fill="none" :stroke="s.color" stroke-width="2" stroke-linejoin="round" />
        <g v-if="showDots">
          <circle
            v-for="(p, pi) in s.data"
            :key="pi"
            :cx="xScale(allLabels.indexOf(p.label) >= 0 ? allLabels.indexOf(p.label) : pi)"
            :cy="yScale(p.value, seriesMax)"
            r="3"
            :fill="s.color"
          />
        </g>
      </g>
      <g v-if="series.length > 1">
        <g v-for="(s, si) in series" :key="'legend-' + si">
          <rect :x="pad + si * 80" :y="4" width="12" height="12" :fill="s.color" rx="2" />
          <text :x="pad + si * 80 + 16" y="14" class="legend-text">{{ s.name }}</text>
        </g>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.line-chart-scroll { overflow-x: auto; }
.line-chart { display: block; }
.axis-label { font-size: 9px; fill: #888; }
.legend-text { font-size: 10px; fill: #555; }
</style>
