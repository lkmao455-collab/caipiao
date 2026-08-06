<script setup lang="ts">
import { ref } from "vue";
import Login from "./views/Login.vue";
import Profiles from "./views/Profiles.vue";
import Generate from "./views/Generate.vue";
import Stats from "./views/Stats.vue";
import Backtest from "./views/Backtest.vue";
import FilterRules from "./views/FilterRules.vue";

const token = ref<string>(localStorage.getItem("cp_token") ?? "");
const step = ref<"login" | "workspace">(token.value ? "workspace" : "login");
const selection = ref<{ profileKey: string; strategyId: string }>({
  profileKey: "",
  strategyId: "",
});
const tab = ref<"generate" | "stats" | "backtest" | "filters">("generate");
const postFilters = ref<{ name: string; params: Record<string, unknown> }[]>([]);

function onAuthed(t: string) {
  token.value = t;
  localStorage.setItem("cp_token", t);
  step.value = "workspace";
}

function onSelected(profileKey: string, strategyId: string) {
  selection.value = { profileKey, strategyId };
  postFilters.value = [];
  tab.value = "generate";
}

function onFiltersApply(filters: { name: string; params: Record<string, unknown> }[]) {
  postFilters.value = filters;
  tab.value = "generate";
}

function logout() {
  token.value = "";
  localStorage.removeItem("cp_token");
  step.value = "login";
}
</script>

<template>
  <h1>彩票号码生成器 Web</h1>
  <button v-if="token" style="background: #888" @click="logout">退出</button>

  <Login v-if="step === 'login'" @authed="onAuthed" />

  <template v-else-if="step === 'workspace'">
    <Profiles :token="token" @selected="onSelected" />
    <div v-if="selection.profileKey" class="tabs">
      <button :class="{ active: tab === 'generate' }" @click="tab = 'generate'">生成</button>
      <button :class="{ active: tab === 'stats' }" @click="tab = 'stats'">统计</button>
      <button :class="{ active: tab === 'backtest' }" @click="tab = 'backtest'">回测</button>
      <button :class="{ active: tab === 'filters' }" @click="tab = 'filters'">过滤</button>
    </div>

    <Stats
      v-if="tab === 'stats'"
      :token="token"
      :profile-key="selection.profileKey"
    />
    <Backtest
      v-else-if="tab === 'backtest'"
      :token="token"
      :profile-key="selection.profileKey"
      :strategy-id="selection.strategyId"
    />
    <FilterRules
      v-else-if="tab === 'filters'"
      :token="token"
      :profile-key="selection.profileKey"
      @apply="onFiltersApply"
    />
    <Generate
      v-else
      :token="token"
      :profile-key="selection.profileKey"
      :strategy-id="selection.strategyId"
      :post-filters="postFilters"
    />
  </template>
</template>

<style scoped>
.tabs { display: flex; gap: 8px; margin: 12px 0; }
.tabs button { padding: 6px 14px; border: 1px solid #ccc; background: #f5f5f5; border-radius: 4px; cursor: pointer; }
.tabs button.active { background: #1976D2; color: #fff; border-color: #1976D2; }
</style>
