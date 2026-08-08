<script setup lang="ts">
import { ref } from "vue";
import Login from "./views/Login.vue";
import Profiles from "./views/Profiles.vue";
import Generate from "./views/Generate.vue";
import Stats from "./views/Stats.vue";
import Backtest from "./views/Backtest.vue";
import FilterRules from "./views/FilterRules.vue";
import Compare from "./views/Compare.vue";
import Favorites from "./views/Favorites.vue";
import Recommendations from "./views/Recommendations.vue";
import Dashboard from "./views/Dashboard.vue";
import MultiPeriodAnalysis from "./views/MultiPeriodAnalysis.vue";
import Tasks from "./views/Tasks.vue";
import Plugins from "./views/Plugins.vue";
import Admin from "./views/Admin.vue";
import { getMe, type CurrentUser } from "./api/client";
import ChatBot from "./views/ChatBot.vue";
import LanguageSwitcher from "./components/LanguageSwitcher.vue";
import { t } from "./i18n/index";

const token = ref<string>(localStorage.getItem("cp_token") ?? "");
const step = ref<"login" | "workspace">(token.value ? "workspace" : "login");
const role = ref<string>(localStorage.getItem("cp_role") ?? "");
const selection = ref<{ profileKey: string; strategyId: string }>({
  profileKey: "",
  strategyId: "",
});
const tab = ref<"generate" | "stats" | "backtest" | "filters" | "compare" | "plugins" | "admin" | "favorites" | "recommend" | "dashboard" | "multi" | "tasks">("generate");
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
  <h1>{{ t("common.appTitle") }} Web</h1>
  <div v-if="token" style="display: flex; gap: 8px; align-items: center; margin-bottom: 12px;">
    <LanguageSwitcher />
    <button style="background: #888" @click="logout">{{ t("auth.logout") }}</button>
  </div>

  <Login v-if="step === 'login'" @authed="onAuthed" />

  <template v-else-if="step === 'workspace'">
    <Profiles :token="token" @selected="onSelected" />
    <div v-if="selection.profileKey" class="tabs">
      <button :class="{ active: tab === 'generate' }" @click="tab = 'generate'">{{ t("nav.generate") }}</button>
      <button :class="{ active: tab === 'stats' }" @click="tab = 'stats'">{{ t("nav.stats") }}</button>
      <button :class="{ active: tab === 'backtest' }" @click="tab = 'backtest'">{{ t("nav.backtest") }}</button>
      <button :class="{ active: tab === 'filters' }" @click="tab = 'filters'">{{ t("nav.filters") }}</button>
      <button :class="{ active: tab === 'compare' }" @click="tab = 'compare'">{{ t("nav.compare") }}</button>
      <button :class="{ active: tab === 'favorites' }" @click="tab = 'favorites'">{{ t("nav.favorites") }}</button>
      <button :class="{ active: tab === 'recommend' }" @click="tab = 'recommend'">{{ t("nav.recommend") }}</button>
      <button :class="{ active: tab === 'dashboard' }" @click="tab = 'dashboard'">{{ t("nav.dashboard") }}</button>
      <button :class="{ active: tab === 'multi' }" @click="tab = 'multi'">{{ t("nav.multiPeriod") }}</button>
      <button :class="{ active: tab === 'tasks' }" @click="tab = 'tasks'">{{ t("nav.tasks") }}</button>
      <button v-if="role === 'admin'" :class="{ active: tab === 'plugins' }" @click="tab = 'plugins'">插件</button>
      <button v-if="role === 'admin'" :class="{ active: tab === 'admin' }" @click="tab = 'admin'">{{ t("nav.admin") }}</button>
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
    <Compare
      v-else-if="tab === 'compare'"
      :token="token"
      :profile-key="selection.profileKey"
      :strategy-id="selection.strategyId"
    />
    <Favorites
      v-else-if="tab === 'favorites'"
      :token="token"
      :profile-key="selection.profileKey"
      :strategy-id="selection.strategyId"
      @select="onSelected"
    />
    <Recommendations
      v-else-if="tab === 'recommend'"
      :token="token"
      :profile-key="selection.profileKey"
      @select="(sid) => onSelected(selection.profileKey, sid)"
    />
    <Dashboard
      v-else-if="tab === 'dashboard'"
      :token="token"
      :profile-key="selection.profileKey"
    />
    <MultiPeriodAnalysis
      v-else-if="tab === 'multi'"
      :token="token"
      :profile-key="selection.profileKey"
    />
    <Tasks
      v-else-if="tab === 'tasks'"
      :token="token"
      :profile-key="selection.profileKey"
    />
    <Plugins
      v-else-if="tab === 'plugins' && role === 'admin'"
      :token="token"
    />
    <Admin v-else-if="tab === 'admin' && role === 'admin'" :token="token" />
  </template>

  <ChatBot v-if="step === 'workspace'" :token="token" />
</template>

<style scoped>
.tabs { display: flex; gap: 8px; margin: 12px 0; flex-wrap: wrap; }
.tabs button { padding: 6px 14px; border: 1px solid #ccc; background: #f5f5f5; border-radius: 4px; cursor: pointer; font-size: 13px; }
.tabs button.active { background: #1976D2; color: #fff; border-color: #1976D2; }

@media (max-width: 768px) {
  .tabs { gap: 4px; }
  .tabs button { padding: 8px 10px; font-size: 12px; flex: 1; min-width: 0; text-align: center; }
}
</style>
