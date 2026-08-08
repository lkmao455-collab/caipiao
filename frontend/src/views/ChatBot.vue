<script setup lang="ts">
import { ref, nextTick, watch } from "vue";
import { sendChatMessage, type ChatResponse } from "../api/client";

const props = defineProps<{ token: string }>();

interface Message {
  id: number;
  content: string;
  isUser: boolean;
  suggestions?: string[];
  timestamp: Date;
}

const messages = ref<Message[]>([]);
const input = ref("");
const busy = ref(false);
const showChat = ref(false);
let messageId = 0;

// 初始欢迎消息
function initChat() {
  if (messages.value.length === 0) {
    messages.value.push({
      id: messageId++,
      content: "您好！我是智能客服助手，可以帮您解答关于彩票号码生成器的使用问题。请问有什么可以帮您的？",
      isUser: false,
      suggestions: ["功能介绍", "如何生成号码？", "常见问题"],
      timestamp: new Date(),
    });
  }
}

watch(showChat, (val) => {
  if (val) initChat();
});

async function send(text?: string) {
  const msg = text || input.value.trim();
  if (!msg || busy.value) return;

  // 添加用户消息
  messages.value.push({
    id: messageId++,
    content: msg,
    isUser: true,
    timestamp: new Date(),
  });
  input.value = "";
  busy.value = true;

  await nextTick();
  scrollToBottom();

  try {
    const res: ChatResponse = await sendChatMessage(props.token, msg);
    messages.value.push({
      id: messageId++,
      content: res.reply,
      isUser: false,
      suggestions: res.suggestions,
      timestamp: new Date(),
    });
  } catch (e) {
    messages.value.push({
      id: messageId++,
      content: "抱歉，系统繁忙，请稍后再试。",
      isUser: false,
      timestamp: new Date(),
    });
  } finally {
    busy.value = false;
    await nextTick();
    scrollToBottom();
  }
}

function scrollToBottom() {
  const container = document.querySelector(".chat-messages");
  if (container) {
    container.scrollTop = container.scrollHeight;
  }
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}
</script>

<template>
  <div class="chatbot-wrapper">
    <!-- 悬浮按钮 -->
    <button class="chat-toggle" @click="showChat = !showChat">
      <span v-if="!showChat">💬</span>
      <span v-else>✕</span>
    </button>

    <!-- 聊天窗口 -->
    <div v-if="showChat" class="chat-window">
      <div class="chat-header">
        <span>智能客服</span>
        <button class="close-btn" @click="showChat = false">✕</button>
      </div>

      <div class="chat-messages">
        <div
          v-for="msg in messages"
          :key="msg.id"
          :class="['message', msg.isUser ? 'user' : 'bot']"
        >
          <div class="bubble">{{ msg.content }}</div>
          <div class="time">{{ formatTime(msg.timestamp) }}</div>
          <!-- 建议按钮 -->
          <div v-if="msg.suggestions?.length" class="suggestions">
            <button
              v-for="s in msg.suggestions"
              :key="s"
              class="suggestion-btn"
              @click="send(s)"
            >
              {{ s }}
            </button>
          </div>
        </div>
        <div v-if="busy" class="message bot">
          <div class="bubble typing">正在输入...</div>
        </div>
      </div>

      <div class="chat-input">
        <input
          v-model="input"
          placeholder="输入您的问题..."
          @keyup.enter="send()"
          :disabled="busy"
        />
        <button @click="send()" :disabled="busy || !input.trim()">发送</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chatbot-wrapper {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 9999;
}

.chat-toggle {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: #1976D2;
  color: #fff;
  font-size: 24px;
  border: none;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s;
}

.chat-toggle:hover {
  transform: scale(1.1);
}

.chat-window {
  position: absolute;
  bottom: 70px;
  right: 0;
  width: 360px;
  height: 480px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  background: #1976D2;
  color: #fff;
  font-weight: 600;
}

.close-btn {
  background: transparent;
  border: none;
  color: #fff;
  font-size: 18px;
  cursor: pointer;
  padding: 4px;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message {
  display: flex;
  flex-direction: column;
  max-width: 85%;
}

.message.user {
  align-self: flex-end;
}

.message.bot {
  align-self: flex-start;
}

.bubble {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
}

.message.user .bubble {
  background: #1976D2;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message.bot .bubble {
  background: #f0f0f3;
  color: #333;
  border-bottom-left-radius: 4px;
}

.bubble.typing {
  color: #999;
  font-style: italic;
}

.time {
  font-size: 10px;
  color: #999;
  margin-top: 4px;
}

.message.user .time {
  text-align: right;
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.suggestion-btn {
  font-size: 11px;
  padding: 4px 10px;
  border: 1px solid #1976D2;
  background: #fff;
  color: #1976D2;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.suggestion-btn:hover {
  background: #e3f2fd;
}

.chat-input {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid #eee;
}

.chat-input input {
  flex: 1;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 20px;
  font-size: 13px;
  outline: none;
}

.chat-input input:focus {
  border-color: #1976D2;
}

.chat-input button {
  padding: 10px 16px;
  background: #1976D2;
  color: #fff;
  border: none;
  border-radius: 20px;
  cursor: pointer;
  font-size: 13px;
}

.chat-input button:disabled {
  background: #ccc;
}

@media (max-width: 480px) {
  .chat-window {
    width: calc(100vw - 40px);
    height: 60vh;
    right: -10px;
  }
}
</style>
