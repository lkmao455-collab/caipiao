<script setup lang="ts">
import { ref } from "vue";
import { login, register } from "../api/client";

const emit = defineEmits<{ authed: [token: string] }>();

const username = ref("");
const password = ref("");
const error = ref("");
const busy = ref(false);

async function doLogin() {
  error.value = "";
  busy.value = true;
  try {
    const token = await login(username.value, password.value);
    emit("authed", token);
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}

async function doRegister() {
  error.value = "";
  busy.value = true;
  try {
    await register(username.value, password.value);
    await doLogin();
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="card">
    <h2>登录 / 注册</h2>
    <div class="row">
      <input v-model="username" placeholder="用户名" />
      <input v-model="password" type="password" placeholder="密码" />
      <button :disabled="busy" @click="doLogin">登录</button>
      <button :disabled="busy" @click="doRegister">注册并登录</button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>
