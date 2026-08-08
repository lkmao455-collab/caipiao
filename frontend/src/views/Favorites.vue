<script setup lang="ts">
import { ref, onMounted } from "vue";
import {
  getFavorites,
  addFavorite,
  deleteFavorite,
  listStrategies,
  type Favorite,
  type Strategy,
} from "../api/client";

const props = defineProps<{
  token: string;
  profileKey: string;
  strategyId: string;
}>();

const emit = defineEmits<{
  (e: "select", profileKey: string, strategyId: string): void;
}>();

const favorites = ref<Favorite[]>([]);
const strategies = ref<Strategy[]>([]);
const error = ref("");
const busy = ref(false);
const showAdd = ref(false);
const newName = ref("");

async function load() {
  error.value = "";
  try {
    const [favs, strats] = await Promise.all([
      getFavorites(props.token),
      listStrategies(props.token, props.profileKey),
    ]);
    favorites.value = favs.filter((f) => f.profile_key === props.profileKey);
    strategies.value = strats;
  } catch (e) {
    error.value = String(e);
  }
}

onMounted(load);

function getStrategyName(strategyId: string): string {
  const s = strategies.value.find((s) => s.id === strategyId);
  return s?.name ?? strategyId;
}

async function add() {
  if (!newName.value.trim()) return;
  error.value = "";
  busy.value = true;
  try {
    await addFavorite(props.token, props.profileKey, props.strategyId, newName.value.trim());
    newName.value = "";
    showAdd.value = false;
    await load();
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}

async function remove(id: string) {
  error.value = "";
  try {
    await deleteFavorite(props.token, id);
    await load();
  } catch (e) {
    error.value = String(e);
  }
}

function applyFav(fav: Favorite) {
  emit("select", fav.profile_key, fav.strategy_id);
}
</script>

<template>
  <div class="favorites">
    <div class="header">
      <h4>我的收藏</h4>
      <button class="add-btn" @click="showAdd = !showAdd">
        {{ showAdd ? '取消' : '+ 收藏当前' }}
      </button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="showAdd" class="add-form">
      <input v-model="newName" placeholder="收藏名称" maxlength="100" />
      <button :disabled="busy || !newName.trim()" @click="add">保存</button>
    </div>

    <div v-if="favorites.length" class="fav-list">
      <div v-for="fav in favorites" :key="fav.id" class="fav-item">
        <div class="fav-info">
          <span class="name">{{ fav.name }}</span>
          <span class="strategy">{{ getStrategyName(fav.strategy_id) }}</span>
        </div>
        <div class="fav-actions">
          <button class="use" @click="applyFav(fav)">使用</button>
          <button class="del" @click="remove(fav.id)">删除</button>
        </div>
      </div>
    </div>
    <p v-else class="empty">暂无收藏</p>
  </div>
</template>

<style scoped>
.favorites { margin-top: 8px; }
.header { display: flex; justify-content: space-between; align-items: center; }
.header h4 { margin: 0; font-size: 14px; }
.add-btn {
  font-size: 12px; padding: 4px 10px; border: 1px solid #1976D2;
  background: #fff; color: #1976D2; border-radius: 4px; cursor: pointer;
}
.add-btn:hover { background: #e3f2fd; }
.add-form { display: flex; gap: 8px; margin: 8px 0; }
.add-form input {
  flex: 1; padding: 6px 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px;
}
.add-form button {
  padding: 6px 12px; border: 1px solid #43A047; background: #43A047;
  color: #fff; border-radius: 4px; cursor: pointer; font-size: 13px;
}
.add-form button:disabled { opacity: 0.5; cursor: not-allowed; }
.fav-list { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
.fav-item {
  display: flex; justify-content: space-between; align-items: center;
  border: 1px solid #eee; border-radius: 4px; padding: 8px 12px;
}
.fav-info { display: flex; flex-direction: column; gap: 2px; }
.fav-info .name { font-size: 13px; font-weight: 600; color: #333; }
.fav-info .strategy { font-size: 11px; color: #888; }
.fav-actions { display: flex; gap: 6px; }
.fav-actions button {
  font-size: 11px; padding: 3px 8px; border-radius: 3px; cursor: pointer;
}
.fav-actions .use { border: 1px solid #1976D2; background: #fff; color: #1976D2; }
.fav-actions .use:hover { background: #e3f2fd; }
.fav-actions .del { border: 1px solid #E53935; background: #fff; color: #E53935; }
.fav-actions .del:hover { background: #ffebee; }
.empty { font-size: 12px; color: #999; text-align: center; margin: 12px 0; }
</style>
