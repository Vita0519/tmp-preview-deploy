<script setup>
import { computed } from 'vue'
import Icon from './Icon.vue'
import { fmtBytes, fmtDate, fmtRemain, initial, relTime, typeLabel, visHint, visLabel } from '../format'

const props = defineProps({
  items: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  sort: { type: String, default: 'updated_at' },
  order: { type: String, default: 'desc' },
  now: { type: Number, default: Date.now() },
  selected: { type: Array, default: () => [] },
})

const emit = defineEmits(['sort', 'open', 'toggle', 'toggle-all', 'action'])

const allOn = computed(
  () => props.items.length > 0 && props.items.every((i) => props.selected.includes(i.slug))
)
const maxViews = computed(() => Math.max(...props.items.map((i) => i.views || 0), 1))

const cols = [
  { key: 'title', label: '项目', sortable: true },
  { key: 'kind', label: '类型', sortable: false, cls: 'col-kind' },
  { key: 'visibility', label: '可见性', sortable: false, cls: 'col-vis' },
  { key: 'owner', label: '归属', sortable: false, cls: 'col-owner' },
  { key: 'views', label: '访问', sortable: true, num: true, cls: 'col-views' },
  { key: 'size_bytes', label: '体积', sortable: true, num: true, cls: 'col-size' },
  { key: 'expires_at', label: '剩余', sortable: true, cls: 'col-ttl' },
  { key: 'updated_at', label: '更新', sortable: true, cls: 'col-updated' },
  { key: 'ops', label: '', sortable: false, num: true, cls: 'col-ops' },
]

function ariaSort(key) {
  if (props.sort !== key) return 'none'
  return props.order === 'asc' ? 'ascending' : 'descending'
}

function remainOf(p) {
  if (p.permanent) return { text: '永久', cls: 'perm', pct: 100, warn: false }
  const ms = (p.expires_at || 0) - props.now
  if (p.expired || ms <= 0) return { text: '已到期', cls: 'dead', pct: 0, warn: false }
  const total = (p.expires_at || 0) - (p.created_at || 0)
  const pct = Math.max(2, Math.min(100, total > 0 ? (ms / total) * 100 : 0))
  const warn = ms < 6 * 3600e3
  return { text: fmtRemain(ms), cls: warn ? 'warn' : '', pct, warn }
}

function viewPct(p) {
  return Math.max(2, Math.round(((p.views || 0) / maxViews.value) * 100))
}

// 一律复制 /v/<slug> 短链：外链项目点开时先记一次访问再 302 到源站，
// 转发出去也能统计；直接复制源站地址就统计不到了。
function shareUrl(p) {
  return p.urls?.preview || `${location.origin}/v/${p.slug}`
}

function copyLink(p) {
  const url = shareUrl(p)
  navigator.clipboard?.writeText(url).then(
    () => emit('action', { type: 'copied', item: p }),
    () => emit('action', { type: 'copy-failed', item: p })
  )
}
</script>

<template>
  <div class="tablewrap">
    <table>
      <thead>
        <tr>
          <th class="cell-check">
            <input
              type="checkbox"
              :checked="allOn"
              aria-label="全选"
              style="accent-color: var(--brand); width: 14px; height: 14px"
              @change="emit('toggle-all', !allOn)"
            />
          </th>
          <th
            v-for="c in cols"
            :key="c.key"
            :class="[c.cls, c.num ? 'cell-num' : '', c.sortable ? 'sortable' : '', sort === c.key ? 'active' : '']"
            :aria-sort="c.sortable ? ariaSort(c.key) : null"
            @click="c.sortable && emit('sort', c.key)"
          >
            {{ c.label }}
            <span v-if="c.sortable" class="arrow">{{ sort === c.key ? (order === 'asc' ? '▲' : '▼') : '▾' }}</span>
          </th>
        </tr>
      </thead>

      <tbody v-if="loading && !items.length">
        <tr v-for="i in 6" :key="i" style="cursor: default">
          <td class="cell-check" />
          <td>
            <div class="skel" style="height: 12px; width: 62%" />
            <div class="skel" style="height: 9px; width: 34%; margin-top: 6px" />
          </td>
          <td class="col-kind" />
          <td class="col-vis"><div class="skel" style="height: 10px; width: 46px" /></td>
          <td class="col-owner" />
          <td class="cell-num col-views"><div class="skel" style="height: 10px; width: 54px; margin-left: auto" /></td>
          <td class="cell-num col-size"><div class="skel" style="height: 10px; width: 54px; margin-left: auto" /></td>
          <td class="col-ttl"><div class="skel" style="height: 10px; width: 40px" /></td>
          <td class="col-updated"><div class="skel" style="height: 10px; width: 40px" /></td>
          <td class="cell-num col-ops" />
        </tr>
      </tbody>

      <tbody v-else>
        <tr
          v-for="p in items"
          :key="p.slug"
          :class="{ 'is-expired': p.expired, selected: selected.includes(p.slug) }"
          @click="emit('open', p)"
        >
          <td class="cell-check" @click.stop>
            <input
              type="checkbox"
              :checked="selected.includes(p.slug)"
              :aria-label="`选择 ${p.title}`"
              style="accent-color: var(--brand); width: 14px; height: 14px"
              @change="emit('toggle', p.slug)"
            />
          </td>

          <td>
            <div class="pcell">
              <div class="pthumb" :class="{ link: p.kind === 'link' }">
                {{ p.kind === 'link' ? '↗' : initial(p.title) }}
              </div>
              <div class="pmeta">
                <div class="pname">
                  <span class="truncate" style="max-width: 260px">{{ p.title }}</span>
                  <span v-if="!p.permanent && p.expired" class="badge danger">已到期</span>
                </div>
                <div class="pslug truncate">
                  /{{ p.slug }}/<span v-if="p.tags?.length" class="dim"> · {{ p.tags.join(' · ') }}</span>
                </div>
              </div>
            </div>
          </td>

          <td class="col-kind">
            <span class="badge" :class="{ brand: p.kind === 'link' }">{{ typeLabel(p.kind) }}</span>
          </td>

          <td class="col-vis">
            <span
              class="badge"
              :class="{ brand: p.visibility === 'portal', warn: p.visibility === 'private' }"
              :title="visHint(p.visibility)"
            >{{ visLabel(p.visibility) }}</span>
          </td>

          <td class="col-owner">
            <span class="truncate" style="max-width: 100px; display: inline-block">
              {{ p.owner?.display_name || '—' }}
            </span>
          </td>

          <td class="cell-num col-views">
            <div class="tabular" style="font-weight: 600">{{ p.views || 0 }}</div>
            <div class="bar" style="margin-left: auto">
              <i :style="{ width: viewPct(p) + '%', opacity: p.views ? 1 : 0.25 }" />
            </div>
          </td>

          <td class="cell-num col-size">
            <div class="tabular">{{ p.kind === 'link' ? '—' : fmtBytes(p.size_bytes) }}</div>
            <div class="dim" style="font-size: 10.5px">
              {{ p.kind === 'link' ? '外部站点' : `${p.file_count} 文件` }}
            </div>
          </td>

          <td class="col-ttl">
            <div class="ttl num" :class="remainOf(p).cls">{{ remainOf(p).text }}</div>
            <div v-if="!p.permanent" class="bar" :class="{ warn: remainOf(p).warn }">
              <i :style="{ width: remainOf(p).pct + '%' }" />
            </div>
          </td>

          <td class="col-updated">
            <div class="tabular" style="font-size: 12px" :title="new Date(p.updated_at).toLocaleString()">
              {{ relTime(p.updated_at) }}
            </div>
            <div class="dim" style="font-size: 10.5px; white-space: nowrap" :title="p.permanent ? '永久有效' : fmtDate(p.expires_at) + ' 到期'">
              {{ p.permanent ? '永久' : fmtDate(p.expires_at).slice(5, 10) + ' 止' }}
            </div>
          </td>

          <td class="cell-num col-ops" @click.stop>
            <div class="rowactions">
              <button class="btn sm icon" title="复制链接" @click="copyLink(p)">
                <Icon name="copy" :size="13" />
              </button>
              <a
                class="btn sm icon"
                :href="p.kind === 'link' ? p.link_url : p.urls?.preview"
                target="_blank"
                rel="noopener"
                title="打开预览"
              >
                <Icon name="external" :size="13" />
              </a>
            </div>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="!loading && !items.length" class="empty">
      <div class="ico"><Icon name="inbox" :size="18" /></div>
      <h3>没有匹配的项目</h3>
      <p>换个筛选条件，或者上传一个新项目试试。</p>
    </div>
  </div>
</template>
