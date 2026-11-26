<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '../api'
import { store, toast } from '../store'

const ACTIONS = {
  upload: '上传项目', replace: '覆盖上传', link: '登记外链', patch: '修改属性', delete: '删除项目',
  expire_delete: '到期删除', expire_block: '到期停访', bulk: '批量操作', collection: '分组',
  agent_create: '新建成员', agent_patch: '修改成员', agent_delete: '删除成员',
  settings: '修改设置', backup: '下载备份', restore: '恢复备份', import: '导入书签',
}
// 动作 → 色调（只用主题语义色，深浅主题自动适配）
const TONE = {
  upload: 'ok', replace: 'ok', link: 'ok', import: 'ok',
  patch: 'info', bulk: 'info', collection: 'info', settings: 'info',
  delete: 'danger', expire_delete: 'danger', agent_delete: 'danger',
  expire_block: 'warn', restore: 'warn', backup: 'warn',
  agent_create: 'brand', agent_patch: 'brand',
}
const FIELDS = {
  title: '名称', description: '介绍', visibility: '可见性', expires_at: '到期时间',
  expire_action: '到期动作', collection_id: '分组', slug: 'slug', allow_download: '允许下载',
  status: '状态', tags: '项目标签',
}
const RANGES = [
  { v: '', l: '全部时间' }, { v: 'today', l: '今天' }, { v: '7d', l: '近 7 天' }, { v: '30d', l: '近 30 天' },
]

const isAdmin = computed(() => store.user?.role === 'admin')
const items = ref([])
const total = ref(0)
const stats = ref({ today: 0, actors_today: 0, risky_today: 0 })
const actors = ref([])
const loading = ref(false)
const open = ref(new Set())

const q = ref('')
const action = ref('')
const actor = ref('')
const range = ref('')
const page = ref(1)
const pageSize = ref(Number(localStorage.getItem('pv_log_ps')) || 20)
const auto = ref(false)

const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const pageList = computed(() => {
  const n = pages.value, c = page.value, out = []
  for (let i = 1; i <= n; i++) {
    if (i === 1 || i === n || Math.abs(i - c) <= 1) out.push(i)
    else if (out[out.length - 1] !== '…') out.push('…')
  }
  return out
})
const dirtyFilter = computed(() => q.value || action.value || actor.value || range.value)

function rangeSince() {
  if (!range.value) return null
  const d = new Date()
  if (range.value === 'today') { d.setHours(0, 0, 0, 0); return d.getTime() }
  return Date.now() - (range.value === '7d' ? 7 : 30) * 864e5
}

async function load() {
  loading.value = true
  try {
    const p = new URLSearchParams({ page: String(page.value), page_size: String(pageSize.value) })
    if (q.value.trim()) p.set('q', q.value.trim())
    if (action.value) p.set('action', action.value)
    if (actor.value) p.set('actor', actor.value)
    const s = rangeSince()
    if (s) p.set('since', String(s))
    const d = await api.get('/api/events?' + p.toString())
    items.value = d.items || []
    total.value = d.total || 0
    if (d.stats) stats.value = d.stats
    if (d.actors) actors.value = d.actors
    if (page.value > pages.value) { page.value = pages.value; return load() }
  } catch (e) {
    toast(e?.message || '加载日志失败', 'err')
  } finally {
    loading.value = false
  }
}

let qTimer = null
watch(q, () => { clearTimeout(qTimer); qTimer = setTimeout(() => { page.value = 1; load() }, 300) })
watch([action, actor, range], () => { page.value = 1; load() })
watch(pageSize, (v) => { try { localStorage.setItem('pv_log_ps', String(v)) } catch {} page.value = 1; load() })

function go(n) { if (n < 1 || n > pages.value || n === page.value) return; page.value = n; open.value = new Set(); load() }
function reset() { q.value = ''; action.value = ''; actor.value = ''; range.value = '' }
function toggle(id) { const s = new Set(open.value); s.has(id) ? s.delete(id) : s.add(id); open.value = s }
const hasMore = (e) => !!(e.diff || e.detail)

let autoTimer = null
watch(auto, (v) => { clearInterval(autoTimer); if (v) autoTimer = setInterval(() => { if (!loading.value) load() }, 15000) })
onMounted(load)
onUnmounted(() => { clearInterval(autoTimer); clearTimeout(qTimer) })

const pad = (n) => String(n).padStart(2, '0')
function hms(ms) { const d = new Date(ms); return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}` }
function dayLabel(ms) {
  const d = new Date(ms), t = new Date(); t.setHours(0, 0, 0, 0)
  const diff = Math.round((new Date(d).setHours(0, 0, 0, 0) - t) / 864e5)
  const md = `${d.getMonth() + 1} 月 ${d.getDate()} 日`
  return diff === 0 ? `今天 · ${md}` : diff === -1 ? `昨天 · ${md}` : `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
function fmtVal(k, v) {
  if (v === null || v === undefined || v === '') return '（空）'
  if (k === 'expires_at' && typeof v === 'number') {
    const d = new Date(v); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  }
  if (typeof v === 'boolean') return v ? '是' : '否'
  if (Array.isArray(v)) return v.join(', ') || '（空）'
  return String(v)
}
function summary(e) {
  if (e.diff) return '修改 ' + Object.keys(e.diff).map((k) => FIELDS[k] || k).join('、')
  return e.detail || ''
}
const initial = (s) => (s || '?').slice(0, 1).toUpperCase()

/* 项目预览地址是 /v/<slug>（外壳页：管权限、到期、外链跳转）。
   以前这里拼的是 /<slug>/，会落到前端路由的 404，看着像「项目不存在」。
   slug 优先用后端联查出来的当前值 live_slug：改过名的项目，老日志也能点对。
   项目已删（有 project_id 但没有 live_slug）就不再给死链，改显示「项目已删除」。 */
const GONE_ACTIONS = new Set(['delete', 'expire_delete'])
function objHref(e) {
  if (GONE_ACTIONS.has(e.action)) return ''
  if (e.project_id) return e.live_slug ? `/v/${e.live_slug}` : ''
  return e.slug ? `/v/${e.slug}` : '' // v2.5 之前的老事件没有 project_id，只能退回快照
}
const objGone = (e) => !GONE_ACTIONS.has(e.action) && !!e.project_id && !e.live_slug

async function copy(e) {
  const txt = JSON.stringify(e, null, 2)
  try { await navigator.clipboard.writeText(txt); toast('已复制详情') } catch { toast('复制失败', 'err') }
}

// 导出：按当前筛选拉全量（每页 100，最多 50 页），生成 CSV
async function exportCsv() {
  const rows = [['时间', '动作', '操作人', '凭据', 'slug', '名称', '摘要']]
  try {
    for (let pg = 1; pg <= 50; pg++) {
      const p = new URLSearchParams({ page: String(pg), page_size: '100' })
      if (q.value.trim()) p.set('q', q.value.trim())
      if (action.value) p.set('action', action.value)
      if (actor.value) p.set('actor', actor.value)
      const s = rangeSince(); if (s) p.set('since', String(s))
      const d = await api.get('/api/events?' + p.toString())
      for (const e of d.items) {
        rows.push([new Date(e.at).toLocaleString(), ACTIONS[e.action] || e.action, e.actor, e.actor_label, e.slug || '', e.title || '',
          e.diff ? Object.entries(e.diff).map(([k, v]) => `${FIELDS[k] || k}: ${fmtVal(k, v[0])} → ${fmtVal(k, v[1])}`).join('; ') : e.detail || ''])
      }
      if (pg * 100 >= d.total) break
    }
  } catch (e) { toast(e?.message || '导出失败', 'err'); return }
  const csv = '\ufeff' + rows.map((r) => r.map((c) => `"${String(c ?? '').replace(/"/g, '""')}"`).join(',')).join('\r\n')
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  a.download = `操作日志-${new Date().toISOString().slice(0, 10)}.csv`
  a.click(); URL.revokeObjectURL(a.href)
  toast(`已导出 ${rows.length - 1} 条`)
}
</script>

<template>
  <div class="logs">
    <header class="head">
      <div>
        <h1>操作日志</h1>
        <p>{{ isAdmin ? '追踪项目、成员与站点设置的每一次变更' : '你的账号和你的项目上的操作' }}，按设置里的保留天数自动清理。</p>
      </div>
      <div class="acts">
        <button class="btn" @click="exportCsv">
          <svg viewBox="0 0 24 24"><path d="M12 4v11m0 0-4-4m4 4 4-4M5 19h14" /></svg>导出日志
        </button>
        <button class="btn primary" :disabled="loading" @click="load">
          <svg viewBox="0 0 24 24" :class="{ spin: loading }"><path d="M20 11a8 8 0 0 0-14.9-3M4 13a8 8 0 0 0 14.9 3M4 4v4h4M20 20v-4h-4" /></svg>刷新
        </button>
      </div>
    </header>

    <div class="stats">
      <div class="stat">
        <span class="si t-brand"><svg viewBox="0 0 24 24"><path d="M3 12h4l3-7 4 14 3-7h4" /></svg></span>
        <div><b>{{ stats.today }}</b><small>今日操作</small></div>
      </div>
      <div class="stat">
        <span class="si t-info"><svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M21.5 20a6.5 6.5 0 0 0-4-6" /></svg></span>
        <div><b>{{ stats.actors_today }}</b><small>今日活跃成员</small></div>
      </div>
      <div class="stat">
        <span class="si t-warn"><svg viewBox="0 0 24 24"><path d="M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6z" /><path d="m9 12 2 2 4-4" /></svg></span>
        <div><b>{{ stats.risky_today }}</b><small>今日删除 / 到期 / 恢复</small></div>
      </div>
    </div>

    <section class="card">
      <div class="lg-bar">
        <label class="lg-search">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
          <input v-model="q" placeholder="搜索项目、slug、操作人或详情…" />
        </label>
        <select v-model="action">
          <option value="">全部动作</option>
          <option v-for="(v, k) in ACTIONS" :key="k" :value="k">{{ v }}</option>
        </select>
        <select v-if="isAdmin" v-model="actor">
          <option value="">全部成员</option>
          <option value="系统">系统</option>
          <option v-for="a in actors" :key="a" :value="a">{{ a }}</option>
        </select>
        <select v-model="range">
          <option v-for="r in RANGES" :key="r.v" :value="r.v">{{ r.l }}</option>
        </select>
        <button class="btn ghost" :disabled="!dirtyFilter" @click="reset">重置</button>
      </div>

      <div class="meta">
        <span>当前显示 {{ items.length }} 条，共 {{ total }} 条记录</span>
        <label class="sw-wrap">
          <span class="sw" :class="{ on: auto }" @click="auto = !auto" />自动刷新
        </label>
      </div>

      <div class="table">
        <div class="tr th">
          <span>时间</span><span>动作</span><span>操作人</span><span>对象与摘要</span><span />
        </div>
        <div v-if="loading && !items.length" class="empty">加载中…</div>
        <div v-else-if="!items.length" class="empty">{{ dirtyFilter ? '没有符合条件的记录' : '暂无记录' }}</div>
        <template v-for="e in items" :key="e.id">
          <div class="tr" :class="{ open: open.has(e.id), click: hasMore(e) }" @click="hasMore(e) && toggle(e.id)">
            <span class="time"><b>{{ hms(e.at) }}</b><small>{{ dayLabel(e.at) }}</small></span>
            <span><i class="pill" :class="'t-' + (TONE[e.action] || 'muted')">{{ ACTIONS[e.action] || e.action }}</i></span>
            <span class="who">
              <i class="ava" :class="{ sys: e.actor === '系统' }">{{ initial(e.actor) }}</i>
              <span><b>{{ e.actor }}</b><small v-if="e.actor_label">{{ e.actor_label }}</small></span>
            </span>
            <span class="obj">
              <b v-if="e.title || e.slug">{{ e.title || e.slug }}</b>
              <small class="mono">
                <template v-if="e.slug">{{ e.slug }}<template v-if="summary(e)"> · </template></template>{{ summary(e) }}
              </small>
            </span>
            <span class="chev"><svg v-if="hasMore(e)" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6" /></svg></span>
          </div>
          <div v-if="open.has(e.id)" class="detail">
            <div class="dbox">
              <div class="dmeta">
                <span>事件 ID <b class="mono">#{{ e.id }}</b></span>
                <span>时间 <b class="mono">{{ new Date(e.at).toLocaleString() }}</b></span>
              </div>
              <div v-if="e.diff" class="diff">
                <template v-for="(pair, k) in e.diff" :key="k">
                  <span class="k">{{ FIELDS[k] || k }}</span>
                  <span class="old">{{ fmtVal(k, pair[0]) }}</span>
                  <span class="arr">→</span>
                  <span class="new">{{ fmtVal(k, pair[1]) }}</span>
                </template>
              </div>
              <p v-if="e.detail && !e.diff" class="raw mono">{{ e.detail }}</p>
              <div class="dacts">
                <button class="lnk" @click.stop="copy(e)">复制详情</button>
                <a v-if="objHref(e)" class="lnk" :href="objHref(e)" target="_blank" rel="noopener" @click.stop>查看相关对象 ↗</a>
                <span v-else-if="objGone(e)" class="lnk off" @click.stop>项目已删除</span>
              </div>
            </div>
          </div>
        </template>
      </div>

      <footer v-if="total" class="pager">
        <label>每页
          <select v-model.number="pageSize"><option :value="10">10</option><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option></select>
        </label>
        <span class="grow" />
        <button class="pg" :disabled="page <= 1" @click="go(page - 1)">‹</button>
        <template v-for="(n, i) in pageList" :key="i">
          <span v-if="n === '…'" class="gap">…</span>
          <button v-else class="pg" :class="{ on: n === page }" @click="go(n)">{{ n }}</button>
        </template>
        <button class="pg" :disabled="page >= pages" @click="go(page + 1)">›</button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.logs { padding: 26px 28px 40px; max-width: 1180px; }
svg { width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; flex: 0 0 auto; }
.spin { animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.head { display: flex; align-items: flex-end; gap: 16px; margin-bottom: 18px; flex-wrap: wrap; }
.head h1 { font-size: 22px; }
.head p { margin-top: 4px; color: var(--ink-3); font-size: 12.5px; }
.acts { margin-left: auto; display: flex; gap: 8px; }
.btn { display: inline-flex; align-items: center; gap: 6px; height: 34px; padding: 0 14px; border-radius: var(--radius-sm);
  border: 1px solid var(--line-2); background: var(--surface); color: var(--ink); font-weight: 550; font-size: 12.5px; cursor: pointer;
  transition: border-color .15s var(--ease), background .15s var(--ease); }
.btn:hover:not(:disabled) { border-color: var(--brand-line); }
.btn:disabled { opacity: .5; cursor: default; }
.btn.primary { background: var(--brand); border-color: var(--brand); color: #fff; }
.btn.primary:hover:not(:disabled) { background: var(--brand-hover); }
.btn.ghost { background: transparent; border-color: transparent; color: var(--ink-2); }

/* 色调：全部从主题语义色派生 */
.t-brand { --c: var(--brand); }
.t-ok { --c: var(--ok, var(--brand)); }
.t-info { --c: var(--info, #5b8def); }
.t-warn { --c: var(--warn); }
.t-danger { --c: var(--danger); }
.t-muted { --c: var(--ink-3); }

.stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-bottom: 16px; }
.stat { display: flex; align-items: center; gap: 13px; padding: 15px 16px; border-radius: var(--radius);
  background: var(--surface); border: 1px solid var(--line); box-shadow: var(--shadow-panel); }
.si { width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center; color: var(--c);
  background: color-mix(in srgb, var(--c) 13%, transparent); }
.stat b { display: block; font-size: 20px; font-weight: 650; font-variant-numeric: tabular-nums; line-height: 1.2; }
.stat small { color: var(--ink-3); font-size: 11.5px; }

.card { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow-panel); overflow: hidden; }
.lg-bar { display: flex; align-items: center; gap: 8px; padding: 12px; flex-wrap: wrap; }
.lg-search { flex: 1 1 260px; display: flex; align-items: center; gap: 8px; height: 34px; padding: 0 11px; border-radius: var(--radius-sm);
  border: 1px solid var(--line-2); background: var(--surface-2); color: var(--ink-4); }
.lg-search:focus-within { border-color: var(--brand); box-shadow: 0 0 0 3px var(--brand-soft); }
.lg-search input { flex: 1; min-width: 0; height: 100%; padding: 0; margin: 0; border: 0 !important; outline: 0; box-shadow: none !important; background: transparent !important; color: var(--ink); }
.lg-search input::placeholder { color: var(--ink-4); }
.lg-bar select, .pager select { height: 34px; padding: 0 28px 0 11px; border-radius: var(--radius-sm); border: 1px solid var(--line-2);
  background: var(--surface-2) var(--select-arrow) no-repeat right 10px center; appearance: none; color: var(--ink); cursor: pointer; min-width: 116px; }
.pager select { height: 28px; min-width: 64px; }

.meta { display: flex; align-items: center; justify-content: space-between; padding: 8px 16px; font-size: 12px; color: var(--ink-3);
  border-top: 1px solid var(--line); background: rgba(var(--ink-rgb), 0.02); }
.sw-wrap { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; }
.sw { width: 32px; height: 18px; border-radius: 99px; background: var(--surface-3); border: 1px solid var(--line-2); position: relative; transition: .18s; }
.sw::after { content: ""; position: absolute; top: 2px; left: 2px; width: 12px; height: 12px; border-radius: 50%; background: var(--ink-3); transition: .18s; }
.sw.on { background: var(--brand); border-color: var(--brand); }
.sw.on::after { left: 16px; background: #fff; }

.tr { display: grid; grid-template-columns: 130px 110px 200px minmax(0, 1fr) 28px; gap: 12px; align-items: center;
  padding: 11px 16px; border-top: 1px solid var(--line); }
.tr.th { padding: 9px 16px; font-size: 11.5px; font-weight: 600; color: var(--ink-3); background: rgba(var(--ink-rgb), 0.02); }
.tr.click { cursor: pointer; }
.tr.click:hover, .tr.open { background: rgba(var(--ink-rgb), 0.03); }
.tr small { display: block; color: var(--ink-4); font-size: 11px; margin-top: 1px; }
.time b { font-weight: 600; font-variant-numeric: tabular-nums; }
.pill { font-style: normal; display: inline-flex; height: 22px; align-items: center; padding: 0 8px; border-radius: 6px; font-size: 11.5px; font-weight: 600;
  color: var(--c); background: color-mix(in srgb, var(--c) 12%, transparent); border: 1px solid color-mix(in srgb, var(--c) 26%, transparent); }
.who { display: flex; align-items: center; gap: 9px; min-width: 0; }
.who > span { min-width: 0; }
.who b { font-weight: 600; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ava { font-style: normal; width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; flex: 0 0 auto; font-size: 11.5px; font-weight: 700;
  background: var(--brand-soft); color: var(--brand); border: 1px solid var(--brand-line); }
.ava.sys { background: var(--surface-3); color: var(--ink-3); border-color: var(--line-2); }
.obj { min-width: 0; }
.obj b { font-weight: 600; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.obj small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chev { color: var(--ink-4); display: grid; place-items: center; }
.chev svg { transition: transform .18s var(--ease); }
.tr.open .chev svg { transform: rotate(180deg); }
.empty { padding: 40px 16px; text-align: center; color: var(--ink-4); border-top: 1px solid var(--line); }

.detail { padding: 0 16px 14px 158px; background: rgba(var(--ink-rgb), 0.03); }
.dbox { border: 1px solid var(--line); border-radius: 10px; background: var(--surface); padding: 12px 14px; }
.dmeta { display: flex; gap: 18px; flex-wrap: wrap; font-size: 11.5px; color: var(--ink-3); margin-bottom: 10px; }
.dmeta b { color: var(--ink-2); font-weight: 600; margin-left: 4px; }
.diff { display: grid; grid-template-columns: 72px minmax(0, 1fr) 20px minmax(0, 1fr); gap: 6px 8px; align-items: center; font-size: 12px; }
.diff .k { color: var(--ink-3); }
.diff .old, .diff .new { padding: 4px 9px; border-radius: 6px; word-break: break-all; }
.diff .old { color: var(--danger); background: var(--danger-soft); text-decoration: line-through; text-decoration-color: color-mix(in srgb, var(--danger) 50%, transparent); }
.diff .new { color: var(--brand); background: var(--brand-soft); }
.diff .arr { color: var(--ink-4); text-align: center; }
.raw { color: var(--ink-2); word-break: break-all; }
.dacts { display: flex; gap: 16px; margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--line); }
.lnk { border: 0; background: none; padding: 0; color: var(--ink-2); font-size: 12px; cursor: pointer; }
.lnk:hover { color: var(--brand); }
/* 项目已经不在了：只留一句说明，不要再给能点的死链 */
.lnk.off { color: var(--ink-4); cursor: default; }
.lnk.off:hover { color: var(--ink-4); }

.pager { display: flex; align-items: center; gap: 4px; padding: 10px 16px; border-top: 1px solid var(--line); font-size: 12px; color: var(--ink-3); }
.pager label { display: inline-flex; align-items: center; gap: 8px; }
.pager .grow { flex: 1; }
.pg { min-width: 28px; height: 28px; padding: 0 6px; border-radius: 7px; border: 1px solid transparent; background: none; color: var(--ink-2); cursor: pointer; font-variant-numeric: tabular-nums; }
.pg:hover:not(:disabled) { background: var(--surface-2); color: var(--ink); }
.pg.on { background: var(--brand-soft); border-color: var(--brand-line); color: var(--brand); font-weight: 650; }
.pg:disabled { opacity: .35; cursor: default; }
.gap { padding: 0 4px; color: var(--ink-4); }

@media (max-width: 860px) {
  /* 这个页面不用 .topbar，汉堡按钮是 fixed 的，得自己把标题让开 */
  .logs { padding: 58px 14px 80px; }
  .head h1 { font-size: 19px; }
  .stats { grid-template-columns: 1fr; gap: 8px; }
  .tr { grid-template-columns: 84px minmax(0, 1fr) 20px; }
  .tr > span:nth-child(3), .tr > span:nth-child(4) { grid-column: 1 / 3; }
  .tr.th { display: none; }
  .detail { padding-left: 16px; }
  .diff { grid-template-columns: 1fr; }
  .diff .arr { display: none; }
}

@media (max-width: 700px) {
  .lg-bar { padding: 10px; }
  .lg-search { flex: 1 1 100%; }
  .lg-bar select { flex: 1 1 calc(50% - 4px); min-width: 0; }
}
</style>
