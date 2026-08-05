<script setup lang="ts">
import { onMounted, ref } from "vue";
import { listProfiles, listStrategies, type Profile, type Strategy } from "../api/client";

const props = defineProps<{ token: string }>();
const emit = defineEmits<{ selected: [profileKey: string, strategyId: string] }>();

const profiles = ref<Profile[]>([]);
const strategies = ref<Strategy[]>([]);
const profileKey = ref("");
const strategyId = ref("");
const error = ref("");

onMounted(loadProfiles);

async function loadProfiles() {
  error.value = "";
  try {
    profiles.value = await listProfiles(props.token);
    if (profiles.value.length) {
      profileKey.value = profiles.value[0].key;
      await onProfileChange();
    }
  } catch (e) {
    error.value = String(e);
  }
}

async function onProfileChange() {
  error.value = "";
  strategies.value = [];
  strategyId.value = "";
  if (!profileKey.value) return;
  try {
    strategies.value = await listStrategies(props.token, profileKey.value);
    if (strategies.value.length) strategyId.value = strategies.value[0].id;
  } catch (e) {
    error.value = String(e);
  }
}

function confirm() {
  if (profileKey.value && strategyId.value) {
    emit("selected", profileKey.value, strategyId.value);
  }
}
</script>

<template>
  <div class="card">
    <h2>选择彩种与策略</h2>
    <div class="row">
      <select v-model="profileKey" @change="onProfileChange">
        <option v-for="p in profiles" :key="p.key" :value="p.key">
          {{ p.name }}（{{ p.key }}）
        </option>
      </select>
      <select v-model="strategyId">
        <option v-for="s in strategies" :key="s.id" :value="s.id">
          {{ s.name }}
        </option>
      </select>
      <button :disabled="!strategyId" @click="confirm">下一步：生成</button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>
