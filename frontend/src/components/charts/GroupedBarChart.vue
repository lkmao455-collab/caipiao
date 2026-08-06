<script setup lang="ts">
import { computed } from "vue";

interface Series {
  name: string;
  color: string;
  values: number[];
}

const props = withDefaults(
  defineProps<{
    categories: (string | number)[];
    series: Series[];
    height?: number;
    barW?: number;
    gap?: number;
    pad?: number;
  }>(),
  {
    height: 160,
    barW: 10,
    gap: 3,
    pad: 10,
  },
);

const max = computed(() => {
  let m = 0;
  for (const s of props.series) {
    for (const v of s.values) m = Math.max(m, v);
  }
  return m > 0 ? m : 1;
});

const catSlot = computed(() => props.barW * props.series.length + props.gap);
const width = computed(() => props.pad * 2 + props.categories.length * catSlot.value);

function barHeight(v: number): number {
  return (v / max.value) * (props.height - props.pad);
}
function barY(v: number): number {
  return props.height - barHeight(v);
}
function barX(ci: number, si: number): number {
  return props.pad + ci * catSlot.value + si * (props.barW + 1);
}
</script>

<template>
  <div class="chart-scroll">
    <svg :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`" class="grouped">
      <g v-for="(cat, ci) in categories" :key="ci">
        <g v-for="(s, si) in series" :key="si">
          <rect
            :x="barX(ci, si)"
            :y="barY(s.values[ci] ?? 0)"
            :width="barW"
            :height="barHeight(s.values[ci] ?? 0)"
            :fill="s.color"
            rx="1"
          />
        </g>
        <text :x="barX(ci, 0) + (barW * series.length) / 2" :y="height - 3" text-anchor="middle" class="clabel">
          {{ cat }}
        </text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.chart-scroll {
  overflow-x: auto;
}
.grouped {
  display: block;
}
.clabel {
  font-size: 9px;
  fill: #888;
}
</style>
