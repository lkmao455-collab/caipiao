<script setup lang="ts">
import { computed } from "vue";

interface BarItem {
  label: string | number;
  value: number;
  color?: string;
}

const props = withDefaults(
  defineProps<{
    items: BarItem[];
    height?: number;
    color?: string;
    slot?: number;
    pad?: number;
  }>(),
  {
    height: 120,
    color: "#1976D2",
    slot: 18,
    pad: 10,
  },
);

const max = computed(() => {
  const m = Math.max(0, ...props.items.map((i) => i.value));
  return m > 0 ? m : 1;
});

const width = computed(() => props.pad * 2 + props.items.length * props.slot);

function barHeight(v: number): number {
  return (v / max.value) * (props.height - props.pad);
}
function barY(v: number): number {
  return props.height - barHeight(v);
}
function barX(i: number): number {
  return props.pad + i * props.slot + props.slot * 0.15;
}
function barW(): number {
  return props.slot * 0.7;
}
</script>

<template>
  <div class="chart-scroll">
    <svg :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`" class="barchart">
      <g v-for="(it, i) in items" :key="i">
        <rect
          :x="barX(i)"
          :y="barY(it.value)"
          :width="barW()"
          :height="barHeight(it.value)"
          :fill="it.color || color"
          rx="1"
        />
        <text :x="barX(i) + barW() / 2" :y="height - 3" text-anchor="middle" class="blabel">
          {{ it.label }}
        </text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.chart-scroll {
  overflow-x: auto;
}
.barchart {
  display: block;
}
.blabel {
  font-size: 9px;
  fill: #888;
}
</style>
