<script setup>
/**
 * 站点标记：沙漏 = 限时可用，是「临时预览」最直接的图形。
 * 与 /favicon.svg 同一份路径数据，改一处记得两边一起改（tools/gen_icons.py 会检查）。
 */
import { computed, useId } from 'vue'

const props = defineProps({
  size: { type: Number, default: 30 },
  // 纯白版：放在深色背景或需要单色时用
  mono: { type: Boolean, default: false },
})

const uid = useId()
const tileId = computed(() => `pvTile-${uid}`)
const shineId = computed(() => `pvShine-${uid}`)
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 32 32"
    class="brandmark"
    role="img"
    aria-label="临时预览站"
  >
    <defs v-if="!mono">
      <linearGradient :id="tileId" x1="2" y1="0" x2="30" y2="32" gradientUnits="userSpaceOnUse">
        <stop offset="0" stop-color="#17bca9" />
        <stop offset=".48" stop-color="#0f766e" />
        <stop offset="1" stop-color="#095651" />
      </linearGradient>
      <linearGradient :id="shineId" x1="16" y1="0" x2="16" y2="19" gradientUnits="userSpaceOnUse">
        <stop offset="0" stop-color="#ffffff" stop-opacity=".2" />
        <stop offset="1" stop-color="#ffffff" stop-opacity="0" />
      </linearGradient>
    </defs>
    <template v-if="mono">
      <path
        fill="currentColor"
        d="M12.1 7.4H19.9C21 7.4 21.7 8 21.7 8.9V9.2L17.2 15.2V16.8L21.7 22.8V23.1C21.7 24 21 24.6 19.9 24.6H12.1C11 24.6 10.3 24 10.3 23.1V22.8L14.8 16.8V15.2L10.3 9.2V8.9C10.3 8 11 7.4 12.1 7.4Z"
      />
    </template>
    <template v-else>
      <rect width="32" height="32" rx="7.6" :fill="`url(#${tileId})`" />
      <rect width="32" height="32" rx="7.6" :fill="`url(#${shineId})`" />
      <path
        fill="#ffffff"
        d="M12.1 7.4H19.9C21 7.4 21.7 8 21.7 8.9V9.2L17.2 15.2V16.8L21.7 22.8V23.1C21.7 24 21 24.6 19.9 24.6H12.1C11 24.6 10.3 24 10.3 23.1V22.8L14.8 16.8V15.2L10.3 9.2V8.9C10.3 8 11 7.4 12.1 7.4Z"
      />
    </template>
  </svg>
</template>

<style scoped>
.brandmark {
  display: block;
  flex: 0 0 auto;
  border-radius: 23.75%;
  box-shadow: 0 6px 14px -8px rgba(15, 118, 110, 0.7);
}
</style>
