<script setup>
/**
 * 站点标记：沙漏 = 限时可用，是「临时预览」最直接的图形。
 * 平涂单色，直角几何，不用渐变/高光/彩色投影——三样都是模板味的来源。
 * 与 /favicon.svg 同一份路径数据，改一处记得两边一起改（tools/gen_icons.py 会检查）。
 */
import { computed } from 'vue'

const props = defineProps({
  size: { type: Number, default: 30 },
  // 纯色版：放在深色背景或需要单色时用
  mono: { type: Boolean, default: false },
})

// 瓦片取主色，由主题实时派生；沙漏本身用近白，两种主题下都够对比
const tile = computed(() => 'var(--brand, #2563eb)')
const glyph = computed(() => (props.mono ? 'currentColor' : '#f4f7ff'))
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
    <rect v-if="!mono" width="32" height="32" rx="8" :fill="tile" />
    <path :fill="glyph" d="M10.4 8.2H21.6L17.4 15.3H14.6Z" />
    <path :fill="glyph" d="M14.6 16.7H17.4L21.6 23.8H10.4Z" />
  </svg>
</template>

<style scoped>
.brandmark {
  display: block;
  flex: 0 0 auto;
  border-radius: 25%;
}
</style>
