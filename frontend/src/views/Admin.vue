<script setup lang="ts">
import { onMounted, ref } from "vue";
import {
  deleteUser,
  getAdminStats,
  getMe,
  listAdminUsers,
  setUserRole,
  type AdminStats,
  type AdminUser,
  type CurrentUser,
} from "../api/client";

const props = defineProps<{ token: string }>();

const stats = ref<AdminStats | null>(null);
const users = ref<AdminUser[]>([]);
const me = ref<CurrentUser | null>(null);
const error = ref<string>("");

async function refresh() {
  error.value = "";
  try {
    const [s, u, m] = await Promise.all([
      getAdminStats(props.token),
      listAdminUsers(props.token),
      getMe(props.token),
    ]);
    stats.value = s;
    users.value = u;
    me.value = m;
  } catch (e) {
    error.value = String(e);
  }
}

async function changeRole(u: AdminUser, role: string) {
  if (u.id === me.value?.id) return;
  error.value = "";
  try {
    const updated = await setUserRole(props.token, u.id, role);
    users.value = users.value.map((x) => (x.id === updated.id ? updated : x));
  } catch (e) {
    error.value = String(e);
  }
}

async function remove(u: AdminUser) {
  if (u.id === me.value?.id) return;
  if (!confirm(`确认删除用户 ${u.username}？`)) return;
  error.value = "";
  try {
    await deleteUser(props.token, u.id);
    users.value = users.value.filter((x) => x.id !== u.id);
  } catch (e) {
    error.value = String(e);
  }
}

onMounted(refresh);
</script>

<template>
  <section>
    <h2>管理后台</h2>
    <p v-if="error" style="color: #c00">{{ error }}</p>

    <div v-if="stats" class="stats">
      <span>用户：{{ stats.user_count }}</span>
      <span>管理员：{{ stats.admin_count }}</span>
      <span>API Key：{{ stats.api_key_count }}</span>
      <span>累计调用：{{ stats.total_usage }}</span>
    </div>

    <table v-if="users.length">
      <thead>
        <tr>
          <th>用户名</th>
          <th>角色</th>
          <th>注册时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="u in users" :key="u.id">
          <td>{{ u.username }}<span v-if="u.id === me?.id">（我）</span></td>
          <td>{{ u.role }}</td>
          <td>{{ u.created_at }}</td>
          <td>
            <button :disabled="u.id === me?.id" @click="changeRole(u, u.role === 'admin' ? 'user' : 'admin')">
              设为{{ u.role === 'admin' ? '普通用户' : '管理员' }}
            </button>
            <button :disabled="u.id === me?.id" style="background: #c0392b" @click="remove(u)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>

    <button @click="refresh">刷新</button>
  </section>
</template>

<style scoped>
.stats { display: flex; gap: 16px; flex-wrap: wrap; margin: 12px 0; }
table { border-collapse: collapse; width: 100%; max-width: 640px; }
th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; }
button { margin-right: 6px; padding: 4px 10px; cursor: pointer; }
button:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
