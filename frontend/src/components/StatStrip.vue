<script setup>
import { computed } from 'vue'
import Sparkline from './Sparkline.vue'
import { fmtBytes, fmtNum } from '../format'

const props = defineProps({
  stats: { type: Object, default: () => ({}) },
  trend: { type: Array, default: () => [] },
})

const spark = computed(() => props.trend.map((d) => d.count))
const trendText = computed(() => {
  if (props.trend.length < 2) return ''
  const last = props.trend[props.trend.length - 1]?.count || 0
  const prev = props.trend[props.trend.length - 2]?.count || 0
  if (!prev) return last ? `昨日 ${prev} → 今日 ${last}` : ''
  const delta = Math.round(((last - prev) / prev) * 100)
  return `${delta >= 0 ? '+' : ''}${delta}% vs 昨日`
})
</script>

<template>
  <div class="stats">
    <div class="stat">
      <div class="k">在线项目</div>
      <div class="v">
        {{ fmtNum(stats.online || 0) }}<small>/ {{ fmtNum(stats.total || 0) }}</small>
      </div>
      <div class="delta">
        {{ (stats.total || 0) - (stats.online || 0) > 0 ? `${(stats.total || 0) - (stats.online || 0)} 个已到期` : '全部有效' }}
      </div>
    </div>

    <div class="stat">
      <div class="k">今日访问</div>
      <div class="v">{{ fmtNum(stats.views_today || 0) }}</div>
      <div class="delta">{{ trendText || '按上海时区统计' }}</div>
    </div>

    <div class="stat" style="display: flex; align-items: center; justify-content: space-between">
      <div>
        <div class="k">累计访问</div>
        <div class="v">{{ fmtNum(stats.views || 0) }}</div>
        <div class="delta">下载 {{ fmtNum(stats.downloads || 0) }} 次</div>
      </div>
      <Sparkline :values="spark" :width="52" :height="26" />
    </div>

    <div class="stat">
      <div class="k">24 小时内到期</div>
      <div class="v">{{ fmtNum(stats.expiring_24h || 0) }}</div>
      <div class="delta" :class="{ warn: (stats.expiring_24h || 0) > 0 }">
        {{ (stats.expiring_24h || 0) > 0 ? '记得延长或备份' : '暂无压力' }} · 占用 {{ fmtBytes(stats.size_bytes) }}
      </div>
    </div>
  </div>
</template>
