<script setup lang="ts">
import { setLocale, getLocale, type Locale } from "../i18n/index";
import { ref } from "vue";

const currentLocale = ref<Locale>(getLocale());

function changeLocale(locale: Locale) {
  currentLocale.value = locale;
  setLocale(locale);
  // 触发页面刷新以应用翻译
  window.location.reload();
}
</script>

<template>
  <div class="language-switcher">
    <button
      :class="['lang-btn', { active: currentLocale === 'zh-CN' }]"
      @click="changeLocale('zh-CN')"
    >
      中文
    </button>
    <button
      :class="['lang-btn', { active: currentLocale === 'en-US' }]"
      @click="changeLocale('en-US')"
    >
      EN
    </button>
  </div>
</template>

<style scoped>
.language-switcher {
  display: flex;
  gap: 4px;
  align-items: center;
}

.lang-btn {
  padding: 4px 8px;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.lang-btn:hover {
  background: #f5f5f5;
}

.lang-btn.active {
  background: #1976D2;
  color: #fff;
  border-color: #1976D2;
}
</style>
