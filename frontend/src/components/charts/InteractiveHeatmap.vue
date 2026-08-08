<script setup lang="ts">
import { ref, computed } from "vue";

const props = withDefaults(
  defineProps<{
    data: number[][];
    xLabels?: string[];
    yLabels?: string[];
    colorRange?: [string, string];
    height?: number;
    title?: string;
  }>(),
  { height: 200 },
);

const emit = defineEmits<{ (e: "cell-click", row: number, col: number, value: number): void }>();

const hoveredCell = ref<{ row: number; col: number } | null>(null);

const colorStart = computed(() => props.colorRange?.[0] ?? "#e3f2fd");
const colorEnd = computed(() => props.colorRange?.[1] ?? "#1565C0");

const maxVal = computed(() => {
  let m = 0;
  for (const row of props.data) {
    for (const v of row) {
      if (v > m) m = v;
    }
  }
  return m || 1;
});

function getColor(value: number): string {
  const ratio = value / maxVal.value;
  // 简单的颜色插值
  const r1 = parseInt(colorStart.value.slice(1, 3), 16);
  const g1 = parseInt(colorStart.value.slice(3, 5), 16);
  const b1 = parseInt(colorStart.value.slice(5, 7), 16);
  const r2 = parseInt(colorEnd.value.slice(1, 3), 16);
  const g2 = parseInt(colorEnd.value.slice(3, 5), 16);
  const b2 = parseInt(colorEnd.value.slice(5, 7), 16);
  const r = Math.round(r1 + (r2 - r1) * ratio);
  const g = Math.round(g1 + (g2 - g1) * ratio);
  const b = Math.round(b1 + (b2 - b1) * ratio);
  return `rgb(${r}, ${g}, ${b})`;
}

function onCellHover(row: number, col: number) {
  hoveredCell.value = { row, col };
}

function onCellLeave() {
  hoveredCell.value = null;
}

const cellSize = computed(() => {
  const cols = props.data[0]?.length ?? 1;
  const rows = props.data.length;
  const w = 100 / cols;
  const h = (props.height - 30) / rows;
  return Math.min(w, h);
});
</script>

<template>
  <div class="interactive-heatmap">
    <div v-if="title" class="heatmap-title">{{ title }}</div>
    <svg :viewBox="`0 0 100 ${height}`" preserveAspectRatio="none">
      <!-- 热力图单元格 -->
      <g v-for="(row, ri) in data" :key="`row-${ri}`">
        <g
          v-for="(val, ci) in row"
          :key="`cell-${ri}-${ci}`"
          class="cell-group"
          @mouseenter="onCellHover(ri, ci)"
          @mouseleave="onCellLeave"
          @click="emit('cell-click', ri, ci, val)"
        >
          <!-- 单元格 -->
          <rect
            :x="ci * (100 / row.length)"
            :y="ri * ((height - 30) / data.length)"
            :width="100 / row.length - 0.5"
            :height="(height - 30) / data.length - 0.5"
            :fill="getColor(val)"
            :rx="0.5"
            :class="[
              'cell',
              hoveredCell?.row === ri && hoveredCell?.col === ci ? 'hovered' : '',
            ]"
          />

          <!-- 数值 -->
          <text
            :x="ci * (100 / row.length) + (100 / row.length) / 2"
            :y="ri * ((height - 30) / data.length) + ((height - 30) / data.length) / 2 + 1"
            text-anchor="middle"
            dominant-baseline="central"
            font-size="2.5"
            :fill="val / maxVal > 0.5 ? '#fff' : '#333'"
            font-weight="500"
            pointer-events="none"
          >
            {{ val }}
          </text>
        </g>
      </g>

      <!-- X 轴标签 -->
      <text
        v-if="xLabels"
        v-for="(label, i) in xLabels"
        :key="`xlabel-${i}`"
        :x="i * (100 / xLabels.length) + (100 / xLabels.length) / 2"
        :y="height - 5"
        text-anchor="middle"
        font-size="2"
        fill="#666"
      >
        {{ label }}
      </text>

      <!-- Y 轴标签 -->
      <text
        v-if="yLabels"
        v-for="(label, i) in yLabels"
        :key="`ylabel-${i}`"
        x="2"
        :y="i * ((height - 30) / yLabels.length) + ((height - 30) / yLabels.length) / 2 + 1"
        text-anchor="start"
        dominant-baseline="central"
        font-size="2"
        fill="#666"
      >
        {{ label }}
      </text>
    </svg>

    <!-- 悬浮提示 -->
    <div
      v-if="hoveredCell"
      class="tooltip"
      :style="{
        left: `${(hoveredCell.col / (data[0]?.length ?? 1)) * 100}%`,
        top: `${(hoveredCell.row / data.length) * 100}%`,
      }"
    >
      {{ yLabels?.[hoveredCell.row] || `行${hoveredCell.row + 1}` }} -
      {{ xLabels?.[hoveredCell.col] || `列${hoveredCell.col + 1}` }}:
      {{ data[hoveredCell.row][hoveredCell.col] }}
    </div>
  </div>
</template>

<style scoped>
.interactive-heatmap {
  width: 100%;
  position: relative;
}

.heatmap-title {
  text-align: center;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #333;
}

svg {
  width: 100%;
}

.cell {
  transition: opacity 0.2s, transform 0.1s;
  cursor: pointer;
}

.cell.hovered {
  opacity: 0.8;
  stroke: #333;
  stroke-width: 0.3;
}

.cell-group {
  cursor: pointer;
}

.tooltip {
  position: absolute;
  background: rgba(0, 0, 0, 0.85);
  color: #fff;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
  pointer-events: none;
  transform: translate(-50%, -100%);
  margin-top: -8px;
  white-space: nowrap;
  z-index: 10;
}
</style>
