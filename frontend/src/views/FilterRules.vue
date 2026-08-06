<script setup lang="ts">
import { ref, onMounted } from "vue";
import { getFilters, type FilterParamMeta } from "../api/client";

const props = defineProps<{ token: string; profileKey: string }>();
const emit = defineEmits<{
  (e: "apply", filters: { name: string; params: Record<string, unknown> }[]): void;
}>();

const params = ref<FilterParamMeta[]>([]);
const available = ref(false);
const error = ref("");
const values = ref<Record<string, unknown>>({});
const enabled = ref<Record<string, boolean>>({});

async function load() {
  error.value = "";
  try {
    const res = await getFilters(props.token, props.profileKey);
    available.value = res.available;
    params.value = res.params;
    for (const p of res.params) {
      values.value[p.name] = p.default;
      enabled.value[p.name] = false;
    }
  } catch (e) {
    error.value = String(e);
  }
}

onMounted(load);

function apply() {
  const out: { name: string; params: Record<string, unknown> }[] = [];
  if (available.value) {
    const chosen: Record<string, unknown> = {};
    for (const p of params.value) {
      if (enabled.value[p.name]) chosen[p.name] = values.value[p.name];
    }
    out.push({ name: props.profileKey, params: chosen });
  }
  emit("apply", out);
}
</script>

<template>
  <div class="card">
    <h2>后过滤规则 · {{ profileKey }}</h2>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="!available">该彩种暂不支持后过滤。</p>
    <template v-else>
      <div v-for="p in params" :key="p.name" class="rule-row">
        <label>
          <input type="checkbox" v-model="enabled[p.name]" />
          <strong>{{ p.name }}</strong>
          <small>{{ p.description }}</small>
        </label>
        <input
          v-if="p.type === 'int'"
          type="number"
          :min="p.min ?? undefined"
          :max="p.max ?? undefined"
          v-model.number="values[p.name]"
          :disabled="!enabled[p.name]"
          style="width: 90px"
        />
        <input
          v-else-if="p.type === 'bool'"
          type="checkbox"
          v-model="values[p.name]"
          :disabled="!enabled[p.name]"
        />
      </div>
      <button @click="apply">应用过滤到生成</button>
    </template>
  </div>
</template>

<style scoped>
.rule-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 6px 0; border-bottom: 1px solid #eee; }
.rule-row small { color: #888; margin-left: 8px; }
</style>
