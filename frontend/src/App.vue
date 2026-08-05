<script setup lang="ts">
import { ref } from "vue";
import Login from "./views/Login.vue";
import Profiles from "./views/Profiles.vue";
import Generate from "./views/Generate.vue";

const token = ref<string>(localStorage.getItem("cp_token") ?? "");
const step = ref<"login" | "profiles" | "generate">(token.value ? "profiles" : "login");
const selection = ref<{ profileKey: string; strategyId: string }>({
  profileKey: "",
  strategyId: "",
});

function onAuthed(t: string) {
  token.value = t;
  localStorage.setItem("cp_token", t);
  step.value = "profiles";
}

function onSelected(profileKey: string, strategyId: string) {
  selection.value = { profileKey, strategyId };
  step.value = "generate";
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

  <template v-else-if="step === 'profiles'">
    <Profiles :token="token" @selected="onSelected" />
  </template>

  <template v-else-if="step === 'generate'">
    <Profiles :token="token" @selected="onSelected" />
    <Generate :token="token" :profile-key="selection.profileKey" :strategy-id="selection.strategyId" />
  </template>
</template>
