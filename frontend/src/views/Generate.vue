<script setup lang="ts">
import { ref } from "vue";
import { generate, type Ticket } from "../api/client";

const props = defineProps<{ token: string; profileKey: string; strategyId: string }>();

const count = ref(5);
const tickets = ref<Ticket[]>([]);
const error = ref("");
const busy = ref(false);

async function run() {
  error.value = "";
  busy.value = true;
  tickets.value = [];
  try {
    const res = await generate(props.token, props.profileKey, props.strategyId, count.value);
    tickets.value = res.tickets;
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="card">
    <h2>生成号码</h2>
    <div class="row">
      <span>彩种：{{ profileKey }} / 策略：{{ strategyId }}</span>
      <input v-model.number="count" type="number" min="1" max="100" style="width: 80px" />
      <button :disabled="busy" @click="run">生成</button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
    <div v-for="(t, i) in tickets" :key="i" class="ticket">{{ JSON.stringify(t) }}</div>
  </div>
</template>
