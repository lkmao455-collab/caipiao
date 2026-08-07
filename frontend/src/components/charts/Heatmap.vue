<script setup lang="ts">
import { computed } from "vue";

interface Cell {
  row: number;
  col: number;
  value: number;
  label?: string;
}

const props = withDefaults(
  defineProps<{
    cells: Cell[];
    rows: number;
    cols: number;
    cellSize?: number;
    gap?: number;
    colorLow?: string;
    colorHigh?: string;
  }>(),
  {
    cellSize: 24,
    gap: 2,
    colorLow: "#e3f2fd",
    colorHigh: "#1565c0",
  },
);

const maxVal = computed(() => Math.max(0, ...props.cells.map((c) => c.value)));
const minVal = computed(() => Math.min(...props.cells.map((c) => c.value)));

function intensity(val: number): number {
  if (maxVal.value === minVal.value) return 0.5;
  return (val - minVal.value) / (maxVal.value - minVal.value);
}

function cellColor(val: number): string {
  const t = intensity(val);
  const low = props.colorLow;
  const high = props.colorHigh;
  const r1 = parseInt(low.slice(1, 3), 16);
  const g1 = parseInt(low.slice(3, 5), 16);
  const b1 = parseInt(low.slice(5, 7), 16);
  const r2 = parseInt(high.slice(1, 3), 16);
  const g2 = parseInt(high.slice(3, 5), 16);
  const b2 = parseInt(high.slice(5, 7), 16);
  const r = Math.round(r1 + (r2 - r1) * t);
  const g = Math.round(g1 + (g2 - g1) * t);
  const b = Math.round(b1 + (b2 - b1) * t);
  return `rgb(${r},${g},${b})`;
}

const svgW = computed(() => props.cols * (props.cellSize + props.gap) + props.gap + 30);
const svgH = computed(() => props.rows * (props.cellSize + props.gap) + props.gap + 20);

const cellMap = computed(() => {
  const map = new Map<string, Cell>();
  for (const c of props.cells) map.set(`${c.row}:${c.col}`, c);
  return map;
});
</script>

<template>
  <div class="heatmap-scroll">
    <svg :width="svgW" :height="svgH" :viewBox="`0 0 ${svgW} ${svgH}`" class="heatmap">
      <g v-for="r in rows" :key="'r' + r">
        <g v-for="c in cols" :key="'c' + c">
          <rect
            :x="28 + (c - 1) * (cellSize + gap)"
            :y="16 + (r - 1) * (cellSize + gap)"
            :width="cellSize"
            :height="cellSize"
            :fill="cellColor((cellMap.get(`${r - 1}:${c - 1}`)?.value) ?? 0)"
            rx="2"
          >
            <title>{{ cellMap.get(`${r - 1}:${c - 1}`)?.label ?? `${r - 1},${c - 1}` }}: {{ (cellMap.get(`${r - 1}:${c - 1}`)?.value ?? 0) }}</title>
          </rect>
          <text
            v-if="cellSize >= 20"
            :x="28 + (c - 1) * (cellSize + gap) + cellSize / 2"
            :y="16 + (r - 1) * (cellSize + gap) + cellSize / 2 + 3"
            text-anchor="middle"
            class="cell-text"
          >{{ cellMap.get(`${r - 1}:${c - 1}`)?.value ?? "" }}</text>
        </g>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.heatmap-scroll { overflow-x: auto; }
.heatmap { display: block; }
.cell-text { font-size: 8px; fill: #fff; pointer-events: none; }
</style>
