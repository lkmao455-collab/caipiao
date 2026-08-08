<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import {
  createCollabSession,
  listCollabSessions,
  joinCollabSession,
  type CollaborationSession,
} from "../api/client";

const props = defineProps<{ token: string }>();

const sessions = ref<CollaborationSession[]>([]);
const loading = ref(true);
const error = ref("");
const newSessionName = ref("");
const creating = ref(false);
const activeSessionId = ref<string | null>(null);
const messages = ref<{ user: string; content: string }[]>([]);
const chatInput = ref("");
let ws: WebSocket | null = null;

async function loadSessions() {
  loading.value = true;
  try {
    sessions.value = await listCollabSessions(props.token);
  } catch (e: any) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function handleCreate() {
  if (!newSessionName.value.trim()) return;
  creating.value = true;
  try {
    const session = await createCollabSession(props.token, newSessionName.value);
    newSessionName.value = "";
    await loadSessions();
    joinSession(session.id);
  } catch (e: any) {
    error.value = e.message;
  } finally {
    creating.value = false;
  }
}

function joinSession(sessionId: string) {
  activeSessionId.value = sessionId;
  messages.value = [];

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(
    `${protocol}//${window.location.host}/ws/collab/${sessionId}?user_id=user-${Date.now()}&username=User`
  );

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "chat") {
        messages.value.push({ user: data.username, content: data.content });
      } else if (data.type === "user_join") {
        messages.value.push({ user: "系统", content: `${data.username} 加入了会话` });
      } else if (data.type === "user_leave") {
        messages.value.push({ user: "系统", content: `${data.username} 离开了会话` });
      }
    } catch {}
  };
}

function leaveSession() {
  ws?.close();
  activeSessionId.value = null;
  messages.value = [];
}

function sendChat() {
  if (!chatInput.value.trim() || !ws) return;
  ws.send(JSON.stringify({ type: "chat", content: chatInput.value }));
  messages.value.push({ user: "我", content: chatInput.value });
  chatInput.value = "";
}

onMounted(loadSessions);
onUnmounted(() => ws?.close());
</script>

<template>
  <div class="collab-panel">
    <h3>协作空间</h3>

    <div v-if="error" class="error">{{ error }}</div>

    <!-- 创建会话 -->
    <div class="create-form">
      <input v-model="newSessionName" placeholder="会话名称..." @keyup.enter="handleCreate" :disabled="creating" />
      <button @click="handleCreate" :disabled="creating || !newSessionName.trim()">创建</button>
    </div>

    <!-- 会话列表 -->
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="!activeSessionId" class="session-list">
      <div
        v-for="s in sessions"
        :key="s.id"
        class="session-card"
        @click="joinSession(s.id)"
      >
        <div class="session-name">{{ s.name }}</div>
        <div class="session-meta">{{ s.collaborators }} 人在线</div>
      </div>
      <div v-if="sessions.length === 0" class="empty">暂无会话</div>
    </div>

    <!-- 聊天区域 -->
    <div v-else class="chat-area">
      <div class="chat-header">
        <span>会话中</span>
        <button class="leave-btn" @click="leaveSession">离开</button>
      </div>
      <div class="messages">
        <div v-for="(msg, i) in messages" :key="i" :class="['msg', msg.user === '我' ? 'mine' : '']">
          <span class="user">{{ msg.user }}:</span> {{ msg.content }}
        </div>
      </div>
      <div class="chat-input">
        <input v-model="chatInput" placeholder="输入消息..." @keyup.enter="sendChat" />
        <button @click="sendChat">发送</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.collab-panel {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
h3 { margin: 0 0 12px; font-size: 15px; }
.error { background: #ffebee; color: #c62828; padding: 8px; border-radius: 4px; margin-bottom: 8px; font-size: 12px; }
.create-form { display: flex; gap: 8px; margin-bottom: 12px; }
.create-form input { flex: 1; padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px; }
.create-form button { padding: 8px 16px; background: #1976D2; color: #fff; border: none; border-radius: 4px; cursor: pointer; }
.create-form button:disabled { background: #ccc; }
.session-list { display: flex; flex-direction: column; gap: 8px; }
.session-card { padding: 10px; background: #f5f5f5; border-radius: 6px; cursor: pointer; transition: background 0.2s; }
.session-card:hover { background: #e3f2fd; }
.session-name { font-weight: 500; font-size: 13px; }
.session-meta { font-size: 11px; color: #999; }
.loading, .empty { text-align: center; padding: 20px; color: #999; font-size: 13px; }
.chat-area { display: flex; flex-direction: column; height: 300px; }
.chat-header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 8px; border-bottom: 1px solid #eee; font-size: 13px; }
.leave-btn { padding: 4px 8px; background: #fff; border: 1px solid #ef5350; color: #ef5350; border-radius: 4px; cursor: pointer; font-size: 11px; }
.messages { flex: 1; overflow-y: auto; padding: 8px 0; font-size: 13px; }
.msg { margin-bottom: 6px; }
.msg.mine { color: #1976D2; }
.msg .user { font-weight: 500; }
.chat-input { display: flex; gap: 8px; padding-top: 8px; border-top: 1px solid #eee; }
.chat-input input { flex: 1; padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px; }
.chat-input button { padding: 8px 12px; background: #1976D2; color: #fff; border: none; border-radius: 4px; cursor: pointer; }
</style>
