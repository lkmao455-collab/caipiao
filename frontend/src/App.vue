<script setup lang="ts">
import { ref } from "vue";
import Login from "./views/Login.vue";
import Profiles from "./views/Profiles.vue";
import Generate from "./views/Generate.vue";
import Stats from "./views/Stats.vue";
import Backtest from "./views/Backtest.vue";
import FilterRules from "./views/FilterRules.vue";
import Admin from "./views/Admin.vue";
import { getMe, type CurrentUser } from "./api/client";

const token = ref<string>(localStorage.getItem("cp_token") ?? "");
const step = ref<"login" | "workspace">(token.value ? "workspace" : "login");
const role = ref<string>(localStorage.getItem("cp_role") ?? "");
const selection = ref<{ profileKey: string; strategyId: string }>({
  profileKey: "",
  strategyId: "",
});
const tab = ref<"generate" | "stats" | "backtest" | "filters" | "admin">("generate");
const postFilters = ref<{ name: string; params: Record<string, unknown> }[]>([]);

async function loadRole() {
  if (!token.value) return;
  try {
    const me: CurrentUser = await getMe(token.value);
    role.value = me.role;
    localStorage.setItem("cp_role", me.role);
  } catch {
    role.value = "";
  }
}

async function onAuthed(t: string) {
  token.value = t;
  localStorage.setItem("cp_token", t);
  step.value = "workspace";
  await loadRole();
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
  role.value = "";
  localStorage.removeItem("cp_token");
  localStorage.removeItem("cp_role");
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
      <button v-if="role === 'admin'" :class="{ active: tab === 'admin' }" @click="tab = 'admin'">管理</button>
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
      v-else-if="tab === 'generate'"
      :token="token"
      :profile-key="selection.profileKey"
      :strategy-id="selection.strategyId"
      :post-filters="postFilters"
    />
    <Admin v-else-if="tab === 'admin' && role === 'admin'" :token="token" />
  </template>
</template>

<style scoped>
.tabs { display: flex; gap: 8px; margin: 12px 0; }
.tabs button { padding: 6px 14px; border: 1px solid #ccc; background: #f5f5f5; border-radius: 4px; cursor: pointer; }
.tabs button.active { background: #1976D2; color: #fff; border-color: #1976D2; }
</style>
