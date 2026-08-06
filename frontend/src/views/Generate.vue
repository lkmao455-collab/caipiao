<script setup lang="ts">
import { ref, watch } from "vue";
import { generate, type Ticket } from "../api/client";

const props = defineProps<{
  token: string;
  profileKey: string;
  strategyId: string;
  postFilters?: { name: string; params: Record<string, unknown> }[];
}>();

const count = ref(5);
const tickets = ref<Ticket[]>([]);
const filteredCount = ref(0);
const error = ref("");
const busy = ref(false);

async function run() {
  error.value = "";
  busy.value = true;
  tickets.value = [];
  try {
    const res = await generate(
      props.token,
      props.profileKey,
      props.strategyId,
      count.value,
      props.postFilters ?? [],
    );
    tickets.value = res.tickets;
    filteredCount.value = res.filtered_count;
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}

// 切换彩种/策略时重置结果
watch(
  () => [props.profileKey, props.strategyId],
  () => {
    tickets.value = [];
    error.value = "";
  },
);
</script>

<template>
  <div class="card">
    <h2>生成号码</h2>
    <div class="row">
      <span>彩种：{{ profileKey }} / 策略：{{ strategyId }}</span>
      <input v-model.number="count" type="number" min="1" max="100" style="width: 80px" />
      <button :disabled="busy" @click="run">生成</button>
    </div>
    <p v-if="props.postFilters && props.postFilters.length" class="hint">
      已应用后过滤（{{ props.postFilters[0].params && Object.keys(props.postFilters[0].params).length }} 项）
    </p>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="tickets.length" class="hint">
      原始 {{ count }} 注 → 过滤后 {{ filteredCount }} 注
    </p>
    <div v-for="(t, i) in tickets" :key="i" class="ticket">{{ JSON.stringify(t) }}</div>
  </div>
</template>
