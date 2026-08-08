<script setup lang="ts">
import { ref, onMounted } from "vue";
import {
  listTasks,
  createTask,
  deleteTask,
  toggleTask,
  runTask,
  listStrategies,
  type ScheduledTask,
  type Strategy,
} from "../api/client";

const props = defineProps<{ token: string; profileKey: string }>();

const tasks = ref<ScheduledTask[]>([]);
const strategies = ref<Strategy[]>([]);
const error = ref("");
const busy = ref(false);
const showCreate = ref(false);

const newTask = ref({
  name: "",
  task_type: "fetch_data",
  strategy_id: "",
  interval_minutes: 60,
});

async function load() {
  error.value = "";
  try {
    const [t, s] = await Promise.all([
      listTasks(props.token),
      listStrategies(props.token, props.profileKey),
    ]);
    tasks.value = t;
    strategies.value = s;
  } catch (e) {
    error.value = String(e);
  }
}

onMounted(load);

async function create() {
  if (!newTask.value.name.trim()) return;
  error.value = "";
  busy.value = true;
  try {
    await createTask(props.token, {
      name: newTask.value.name.trim(),
      task_type: newTask.value.task_type,
      profile_key: props.profileKey,
      strategy_id: newTask.value.strategy_id || undefined,
      interval_minutes: newTask.value.interval_minutes,
    });
    newTask.value = { name: "", task_type: "fetch_data", strategy_id: "", interval_minutes: 60 };
    showCreate.value = false;
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
    await deleteTask(props.token, id);
    await load();
  } catch (e) {
    error.value = String(e);
  }
}

async function toggle(id: string, enabled: boolean) {
  error.value = "";
  try {
    await toggleTask(props.token, id, enabled);
    await load();
  } catch (e) {
    error.value = String(e);
  }
}

async function execute(id: string) {
  error.value = "";
  busy.value = true;
  try {
    await runTask(props.token, id);
    await load();
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}

function getTaskTypeName(type: string): string {
  const map: Record<string, string> = {
    fetch_data: "数据拉取",
    backtest: "自动回测",
    analysis: "数据分析",
  };
  return map[type] || type;
}

function getStatusClass(status: string): string {
  const map: Record<string, string> = {
    pending: "status-pending",
    running: "status-running",
    completed: "status-completed",
    failed: "status-failed",
  };
  return map[status] || "";
}
</script>

<template>
  <div class="tasks">
    <div class="header">
      <h3>自动化任务</h3>
      <button class="add-btn" @click="showCreate = !showCreate">
        {{ showCreate ? '取消' : '+ 新建任务' }}
      </button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>

    <!-- 新建任务表单 -->
    <div v-if="showCreate" class="create-form">
      <div class="form-row">
        <input v-model="newTask.name" placeholder="任务名称" maxlength="100" />
        <select v-model="newTask.task_type">
          <option value="fetch_data">数据拉取</option>
          <option value="backtest">自动回测</option>
          <option value="analysis">数据分析</option>
        </select>
      </div>
      <div class="form-row">
        <select v-model="newTask.strategy_id">
          <option value="">选择策略（可选）</option>
          <option v-for="s in strategies" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
        <label>
          间隔：
          <select v-model.number="newTask.interval_minutes">
            <option :value="30">30分钟</option>
            <option :value="60">1小时</option>
            <option :value="180">3小时</option>
            <option :value="360">6小时</option>
            <option :value="720">12小时</option>
            <option :value="1440">24小时</option>
          </select>
        </label>
      </div>
      <button :disabled="busy || !newTask.name.trim()" @click="create">创建</button>
    </div>

    <!-- 任务列表 -->
    <div v-if="tasks.length" class="task-list">
      <div v-for="task in tasks" :key="task.id" class="task-item">
        <div class="task-info">
          <span class="task-name">{{ task.name }}</span>
          <span class="task-type">{{ getTaskTypeName(task.task_type) }}</span>
          <span :class="['task-status', getStatusClass(task.status)]">{{ task.status }}</span>
        </div>
        <div class="task-meta">
          <span>间隔：{{ task.interval_minutes }}分钟</span>
          <span v-if="task.last_run">上次：{{ task.last_run.slice(0, 16) }}</span>
          <span v-if="task.next_run">下次：{{ task.next_run.slice(0, 16) }}</span>
        </div>
        <div class="task-actions">
          <button @click="toggle(task.id, !task.enabled)">
            {{ task.enabled ? '禁用' : '启用' }}
          </button>
          <button :disabled="busy" @click="execute(task.id)">立即执行</button>
          <button class="del" @click="remove(task.id)">删除</button>
        </div>
      </div>
    </div>
    <p v-else class="empty">暂无定时任务</p>
  </div>
</template>

<style scoped>
.tasks { padding: 12px; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.header h3 { margin: 0; }
.add-btn {
  font-size: 13px; padding: 6px 12px; border: 1px solid #1976D2;
  background: #fff; color: #1976D2; border-radius: 4px; cursor: pointer;
}
.add-btn:hover { background: #e3f2fd; }
.create-form {
  border: 1px solid #e0e0e0; border-radius: 6px; padding: 12px;
  margin-bottom: 12px; background: #fafafa;
}
.form-row { display: flex; gap: 10px; margin-bottom: 10px; }
.form-row input, .form-row select {
  flex: 1; padding: 6px 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px;
}
.create-form button {
  padding: 6px 16px; background: #43A047; color: #fff; border: none;
  border-radius: 4px; cursor: pointer; font-size: 13px;
}
.create-form button:disabled { opacity: 0.5; cursor: not-allowed; }
.task-list { display: flex; flex-direction: column; gap: 10px; }
.task-item {
  border: 1px solid #e0e0e0; border-radius: 6px; padding: 12px;
}
.task-info { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.task-name { font-weight: 600; font-size: 14px; }
.task-type { font-size: 12px; color: #666; background: #f5f5f5; padding: 2px 6px; border-radius: 3px; }
.task-status {
  font-size: 11px; padding: 2px 6px; border-radius: 3px; margin-left: auto;
}
.status-pending { background: #fff3e0; color: #e65100; }
.status-running { background: #e3f2fd; color: #1565c0; }
.status-completed { background: #e8f5e9; color: #2e7d32; }
.status-failed { background: #ffebee; color: #c62828; }
.task-meta { font-size: 12px; color: #888; display: flex; gap: 12px; margin-bottom: 8px; }
.task-actions { display: flex; gap: 8px; }
.task-actions button {
  font-size: 12px; padding: 4px 10px; border: 1px solid #ccc;
  background: #fff; border-radius: 3px; cursor: pointer;
}
.task-actions button:hover { background: #f5f5f5; }
.task-actions .del { color: #E53935; border-color: #E53935; }
.task-actions .del:hover { background: #ffebee; }
.empty { color: #999; font-size: 13px; text-align: center; }
</style>
