<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { store, toast } from '../store'

const ACTIONS = {
  upload: '上传', replace: '覆盖', link: '挂链接', patch: '修改', delete: '删除',
  expire_delete: '到期删除', expire_block: '到期下线', bulk: '批量', collection: '分组',
  agent_create: '新建成员', agent_patch: '修改成员', agent_delete: '删除成员',
  settings: '设置', backup: '备份', restore: '恢复',
}
const FIELDS = {
  title: '名称', description: '介绍', visibility: '可见性', expires_at: '到期',
  expire_action: '到期动作', collection_id: '分组', slug: 'slug', allow_download: '允许下载',
  status: '状态', tags: '标签',
}

const items = ref([])
const loading = ref(false)
const nextBefore = ref(null)
const slug = ref('')
const action = ref('')
const isAdmin = computed(() => store.user?.role === 'admin')

function fmtTime(ms) {
  const d = new Date(ms)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function fmtVal(k, v) {
  if (v === null || v === undefined || v === '') return '—'
  if (k === 'expires_at' && typeof v === 'number') return new Date(v).toLocaleString()
  return String(v)
}

async function load(more = false) {
  loading.value = true
  try {
    const q = new URLSearchParams({ limit: '50' })
    if (slug.value.trim()) q.set('slug', slug.value.trim())
    if (action.value) q.set('action', action.value)
    if (more && nextBefore.value) q.set('before', String(nextBefore.value))
    const d = await api.get('/api/events?' + q.toString())
    items.value = more ? items.value.concat(d.items) : d.items
    nextBefore.value = d.next_before
  } catch (e) {
    toast(e?.message || '加载日志失败', 'err')
  } finally {
    loading.value = false
  }
}
onMounted(() => load())
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>操作日志</h1>
        <p class="sub">{{ isAdmin ? '全站所有操作' : '你的账号和你的项目上的操作' }}，按设置里的保留天数自动清理。</p>
      </div>
    </header>

    <div class="filters">
      <input v-model="slug" placeholder="按 slug 过滤" @keyup.enter="load()" />
      <select v-model="action" @change="load()">
        <option value="">全部动作</option>
        <option v-for="(v, k) in ACTIONS" :key="k" :value="k">{{ v }}</option>
      </select>
      <button class="btn" :disabled="loading" @click="load()">刷新</button>
    </div>

    <div v-if="!items.length && !loading" class="empty">暂无记录</div>
    <ul class="evlist">
      <li v-for="e in items" :key="e.id">
        <div class="row1">
          <span class="t">{{ fmtTime(e.at) }}</span>
          <span class="act">{{ ACTIONS[e.action] || e.action }}</span>
          <span class="who">{{ e.actor }}<template v-if="e.actor_label && e.actor_label !== e.actor"> · {{ e.actor_label }}</template></span>
          <span v-if="e.slug" class="proj">
            <a :href="'/' + e.slug + '/'" target="_blank" rel="noopener">{{ e.title || e.slug }}</a>
            <code>{{ e.slug }}</code>
          </span>
          <span v-else-if="e.detail" class="detail">{{ e.detail }}</span>
        </div>
        <div v-if="e.diff" class="diff">
          <div v-for="(pair, k) in e.diff" :key="k">
            <b>{{ FIELDS[k] || k }}</b>
            <span class="old">{{ fmtVal(k, pair[0]) }}</span> →
            <span class="new">{{ fmtVal(k, pair[1]) }}</span>
          </div>
        </div>
      </li>
    </ul>
    <div v-if="nextBefore" class="more">
      <button class="btn" :disabled="loading" @click="load(true)">加载更多</button>
    </div>
  </div>
</template>

<style scoped>
.page { padding: 24px; max-width: 1000px; }
.page-head h1 { margin: 0 0 4px; font-size: 20px; }
.sub { margin: 0; color: var(--ink-3, #888); font-size: 13px; }
.filters { display: flex; gap: 8px; margin: 16px 0; flex-wrap: wrap; }
.filters input, .filters select { padding: 6px 10px; border: 1px solid var(--line, #ddd); border-radius: 6px; background: transparent; color: inherit; }
.empty { color: var(--ink-4, #aaa); padding: 24px 0; }
.evlist { list-style: none; margin: 0; padding: 0; }
.evlist li { padding: 10px 0; border-bottom: 1px solid var(--line, #eee); font-size: 13px; }
.row1 { display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; }
.t { color: var(--ink-4, #aaa); font-variant-numeric: tabular-nums; min-width: 84px; }
.act { font-weight: 600; color: var(--brand, #4a7); min-width: 56px; }
.who { color: var(--ink-3, #888); }
.proj a { color: inherit; font-weight: 500; }
.proj code { margin-left: 6px; color: var(--ink-4, #aaa); font-size: 12px; }
.detail { color: var(--ink-3, #888); word-break: break-all; }
.diff { margin: 6px 0 0 94px; display: grid; gap: 2px; color: var(--ink-3, #888); }
.diff b { display: inline-block; min-width: 64px; color: inherit; font-weight: 500; }
.old { text-decoration: line-through; opacity: .7; }
.new { color: var(--ink-1, inherit); }
.more { padding: 16px 0; text-align: center; }
@media (max-width: 640px) { .page { padding: 16px; } .diff { margin-left: 0; } }
</style>
