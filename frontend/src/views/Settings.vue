<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { api } from '../api'
import { applyTagRules, confirmAction, store, toast } from '../store'
import { fmtBytes, relTime } from '../format'
import { applyPalette, applySiteIcon, normalize, previewAccent, readable } from '../theme'
import Icon from '../components/Icon.vue'

const data = ref(null)
const busy = ref(false)
const pw = reactive({ old_password: '', new_password: '' })

const ACTION_LABEL = {
  upload: '上传',
  replace: '覆盖上传',
  patch: '修改属性',
  delete: '删除项目',
  link: '登记外链',
  bulk: '批量操作',
  import: '导入书签',
  backup: '下载备份',
  restore: '恢复备份',
  collection: '分组',
  agent_create: '创建成员',
  agent_patch: '修改成员',
  agent_delete: '删除成员',
  expire_block: '到期停访',
  expire_delete: '到期删除',
  settings: '修改设置',
}
const actionLabel = (a) => ACTION_LABEL[a] || a

// 站点图标：上传即生效（不需要点保存）
const siteIcon = ref({ custom: false, url: '', ext: '', size: 0, max_kb: 512 })
const ver = ref(null)
const verBusy = ref(false)
// 模板里一直调用 checkVersion，但函数从没定义过——点了直接报错，所以"没任何提示"
async function checkVersion(manual = false) {
  verBusy.value = true
  try {
    const d = await api.get('/api/settings/version' + (manual ? '?force=true' : ''))
    ver.value = d
    store.update = d?.ok && d.has_update ? d : null
    if (manual) {
      if (!d.ok) toast(`检查失败：${d.error || '网络不通'}`, 'err')
      else if (d.has_update) toast(`发现新版本 v${d.latest}`)
      else toast(`已是最新（v${d.current}）`)
    }
  } catch (e) {
    ver.value = { ok: false, error: e.message || '请求失败' }
    if (manual) toast(e.message || '检查失败', 'err')
  } finally {
    verBusy.value = false
  }
}
onMounted(() => checkVersion(false))
const iconFile = ref(null)
const iconBusy = ref(false)
const iconPreview = computed(() => (siteIcon.value.custom ? siteIcon.value.url : '/favicon.svg'))

function pickIcon() {
  iconFile.value?.click()
}

async function onIconPicked(e) {
  const f = e.target.files && e.target.files[0]
  if (!f) return
  const fd = new FormData()
  fd.append('file', f)
  iconBusy.value = true
  try {
    const d = await api.post('/api/settings/icon', fd)
    siteIcon.value = d.site_icon
    applySiteIcon(d.site_icon)
    toast('站点图标已更新')
  } catch (err) {
    toast(err.message || '图标上传失败', 'err')
  } finally {
    iconBusy.value = false
    e.target.value = ''
  }
}

async function resetIcon() {
  iconBusy.value = true
  try {
    const d = await api.del('/api/settings/icon')
    siteIcon.value = d.site_icon
    applySiteIcon(d.site_icon)
    toast('已恢复内置图标')
  } catch (err) {
    toast(err.message || '操作失败', 'err')
  } finally {
    iconBusy.value = false
  }
}

// 主题：插件清单（内置 + 商店安装）+ 当前插件 + 主色。点卡片即时预览，保存后才落库
const accent = ref('#2563eb')
const accentInput = ref('#2563eb')
const plugins = ref([])        // [{id,name,version,author,desc,mode,builtin,default_accent,preview,vars}]
const pluginKey = ref('noir')
const themeVars = ref({})      // 当前预览基座：正在看的这套插件的完整语义令牌
const themeMode = ref('dark')
const custom = ref(false)      // 主色被手改过，不等于当前主题的默认主色
let savedBoard = null          // 进来时后端下发的整份主题载荷，没保存就原样退回去

const activePlugin = computed(() => plugins.value.find((p) => p.id === pluginKey.value) || null)

// 主色被「可读性兜底」校正时，设置页要说清楚实际生效的是哪个色
const dimmed = computed(() => {
  const b = readable(accent.value, themeMode.value)
  return b === normalize(accent.value) ? '' : b
})

function applyBoard(board) {
  // 本地预览一套主题：{vars, accent, mode}
  themeVars.value = board.vars || {}
  themeMode.value = board.mode === 'light' ? 'light' : 'dark'
  applyPalette({ vars: themeVars.value, accent: board.accent, mode: themeMode.value })
}

function pickPlugin(p) {
  pluginKey.value = p.id
  custom.value = false
  accent.value = normalize(p.default_accent)
  accentInput.value = accent.value
  applyBoard({ vars: p.vars, accent: accent.value, mode: p.mode })
}

function pickAccent(v) {
  const hex = normalize(v)
  accent.value = hex
  accentInput.value = hex
  // 和当前主题的默认主色不一样 → 记成「自定义」，主题令牌底保持不变
  custom.value = !!activePlugin.value && hex !== normalize(activePlugin.value.default_accent)
  previewAccent(hex, { vars: themeVars.value, mode: themeMode.value })
}

function resetTheme() {
  const p = activePlugin.value
  // 插件清单还没拉到：退回内置默认色，但好歹让按钮有反应
  if (!p) {
    pickAccent('#2563eb')
    toast('已回到默认主色 #2563eb · 记得点右上角保存')
    return
  }
  const def = normalize(p.default_accent)
  // 本来就是默认色 → 之前点了看着「没反应」，这里说清楚
  if (normalize(accent.value) === def && !custom.value) {
    toast(`当前已经是「${p.name}」的默认主色 ${def}`)
    return
  }
  // 不只是换色值：把这套主题的令牌一起重放，等于重新点一次它的卡片
  pickPlugin(p)
  toast(`已回到「${p.name}」默认主色 ${def} · 记得点右上角保存`)
}

// ---------------- 主题商店 ----------------
const shop = reactive({ open: false, repo: '', busy: false, items: [], error: '', installing: '' })

async function storeFetch() {
  if (!shop.repo.trim()) return
  shop.busy = true
  shop.error = ''
  shop.items = []
  try {
    const d = await api.post('/api/settings/themes/preview', { repo: shop.repo.trim() })
    shop.items = d.items || []
    if (!d.ok) shop.error = d.error || '拉取失败'
  } catch (e) {
    shop.error = e.message || '拉取失败'
  } finally {
    shop.busy = false
  }
}

async function storeInstall(item) {
  shop.installing = item.path
  try {
    const d = await api.post('/api/settings/themes/install', {
      repo: item.repo,
      ref: item.ref || '',
      path: item.path,
    })
    plugins.value = d.theme.plugins || []
    toast(`已安装「${d.plugin.name}」，点卡片启用`)
  } catch (e) {
    toast(e.message || '安装失败', 'err')
  } finally {
    shop.installing = ''
  }
}

async function installExample() {
  shop.installing = 'example'
  try {
    const d = await api.post('/api/settings/themes/install', { source: 'example' })
    plugins.value = d.theme.plugins || []
    toast(`已安装示例主题「${d.plugin.name}」`)
  } catch (e) {
    toast(e.message || '安装失败', 'err')
  } finally {
    shop.installing = ''
  }
}

async function uninstallTheme(p) {
  const ok = await confirmAction({
    title: `卸载「${p.name}」`,
    message: '使用该主题的站点会回到默认主题，插件文件将从服务器删除。',
    confirmText: '卸载',
    danger: true,
  })
  if (!ok) return
  try {
    const d = await api.del(`/api/settings/themes/${p.id}`)
    plugins.value = d.theme.plugins || []
    if (d.theme.plugin !== pluginKey.value) {
      // 正在预览的就是被卸的那套：退回服务端现在的状态
      pluginKey.value = d.theme.plugin
      accent.value = normalize(d.theme.accent)
      accentInput.value = accent.value
      custom.value = !!d.theme.custom
      applyBoard({ vars: d.theme.vars, accent: accent.value, mode: d.theme.mode })
    }
    toast('已卸载')
  } catch (e) {
    toast(e.message || '卸载失败', 'err')
  }
}

/** 商店条目的配色条：画布 → 容器 → 主色（部分覆盖的清单按明暗基底兜底） */
function stripOf(m) {
  const dark = m.mode === 'dark'
  return [
    (m.vars && m.vars['--bg']) || (dark ? '#0b0d10' : '#f6f7f5'),
    (m.vars && m.vars['--surface']) || (dark ? '#14171d' : '#ffffff'),
    m.default_accent,
  ]
}

const form = reactive({
  site_title: '',
  ttl: { portal: 6, link: 12, private: 0 },
  default_expire_action: 'block',
  public_portal: false,
  author: { name: '', bio: '', links: [] },
  tag_max: 6,
  tag_bar: 12,
  portal_max: 500,
  portal_cols: 0,
})

const authorTypes = ref([
  { key: 'github', label: 'GitHub', paths: '' },
  { key: 'x', label: 'X', paths: '' },
  { key: 'mail', label: '邮箱', paths: '' },
  { key: 'blog', label: '博客', paths: '' },
  { key: 'douyin', label: '抖音', paths: '' },
  { key: 'wechat', label: '微信', paths: '' },
  { key: 'bilibili', label: '哔哩哔哩', paths: '' },
  { key: 'zhihu', label: '知乎', paths: '' },
  { key: 'rss', label: 'RSS', paths: '' },
  { key: 'link', label: '链接', paths: '' },
])

const VIS = [
  { key: 'portal', label: '门户可见', hint: '出现在门户首页（/）' },
  { key: 'link', label: '持链接可见', hint: '不列出，有链接就能开' },
  { key: 'private', label: '仅自己可见', hint: '需登录且为本人' },
]

const typeMeta = (key) => authorTypes.value.find((t) => t.key === key) || authorTypes.value[0]
const typeLabel = (key) => typeMeta(key).label
const typeIcon = (key) => typeMeta(key).paths

const previewLinks = computed(() =>
  form.author.links.filter((l) => l.url.trim()).map((l) => ({ ...l, label: l.label || typeLabel(l.type) }))
)

// ---------------- 类型下拉（自绘 + Teleport，避免被卡片裁切） ----------------
const openType = ref(-1)
const popStyle = ref({})
const POP_H = 324

function toggleType(i, ev) {
  if (openType.value === i) {
    openType.value = -1
    return
  }
  const r = ev.currentTarget.getBoundingClientRect()
  const below = window.innerHeight - r.bottom
  const up = below < POP_H + 14 && r.top > below
  popStyle.value = {
    left: `${Math.round(r.left)}px`,
    width: `${Math.round(r.width)}px`,
    ...(up
      ? { bottom: `${Math.round(window.innerHeight - r.top + 6)}px` }
      : { top: `${Math.round(r.bottom + 6)}px` }),
  }
  openType.value = i
}

function pickType(link, key) {
  const labels = authorTypes.value.map((t) => t.label)
  link.type = key
  if (!link.label || labels.includes(link.label)) link.label = typeLabel(key)
  openType.value = -1
}
function closePop() {
  openType.value = -1
}
onMounted(() => {
  document.addEventListener('click', closePop)
  // 浮层是 fixed 定位，滚动/缩放后位置会飘，直接关掉最省事
  window.addEventListener('scroll', closePop, true)
  window.addEventListener('resize', closePop)
})
onUnmounted(() => {
  document.removeEventListener('click', closePop)
  window.removeEventListener('scroll', closePop, true)
  window.removeEventListener('resize', closePop)
})

// ---------------- 数据 ----------------
async function load() {
  try {
    const d = await api.get('/api/settings')
    data.value = d
    form.site_title = d.site_title
    form.ttl = { ...form.ttl, ...(d.ttl_defaults || {}) }
    form.default_expire_action = d.default_expire_action || 'block'
    form.public_portal = d.public_portal
    form.portal_max = d.portal_max ?? 500
    form.portal_cols = d.portal_cols ?? 0
    if (d.site_icon) siteIcon.value = d.site_icon
    form.tag_max = d.tags?.max_per_project ?? 6
    form.tag_bar = d.tags?.bar_limit ?? 12
    const th = d.theme || {}
    plugins.value = Array.isArray(th.plugins) ? th.plugins : []
    pluginKey.value = th.plugin || 'noir'
    custom.value = !!th.custom
    // 记用户填的原值；palette 内部会为可读性校正，实际生效值在 th.accent
    const hex = normalize(th.raw || th.accent || '#2563eb')
    accent.value = hex
    accentInput.value = hex
    savedBoard = th.accent ? th : null
    applyBoard({ vars: th.vars, accent: th.accent, mode: th.mode })
    if (Array.isArray(d.author_types) && d.author_types.length) authorTypes.value = d.author_types
    const a = d.author || {}
    form.author = {
      name: a.name || '',
      bio: a.bio || '',
      links: (a.links || []).map((l) => ({
        ...l,
        url: l.type === 'mail' ? String(l.url || '').replace(/^mailto:/i, '') : l.url,
      })),
    }
    snap.value = state.value
  } catch (e) {
    toast(e.message || '读取失败', 'err')
  }
}

function addLink() {
  if (form.author.links.length >= 12) return toast('最多 12 个链接', 'err')
  form.author.links.push({ type: 'github', label: '', url: '' })
}
function removeLink(i) {
  form.author.links.splice(i, 1)
}
// 链接排序：拖拽 + 上下按钮
const dragFrom = ref(-1)
const dragOver = ref(-1)
function dragStart(i, e) {
  dragFrom.value = i
  if (e?.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    try { e.dataTransfer.setData('text/plain', String(i)) } catch {}
  }
}
function moveLinkTo(from, to) {
  const arr = form.author.links
  if (from < 0 || to < 0 || from >= arr.length || to >= arr.length || from === to) return
  const [it] = arr.splice(from, 1)
  arr.splice(to, 0, it)
}
function dropLink(i) {
  moveLinkTo(dragFrom.value, i)
  dragFrom.value = dragOver.value = -1
}
function moveLink(i, d) {
  moveLinkTo(i, i + d)
}

async function save() {
  busy.value = true
  try {
    const d = await api.patch('/api/settings', {
      site_title: form.site_title,
      ttl_defaults: {
        portal: Number(form.ttl.portal) || 0,
        link: Number(form.ttl.link) || 0,
        private: Number(form.ttl.private) || 0,
      },
      default_expire_action: form.default_expire_action,
      public_portal: form.public_portal,
      portal_max: Number(form.portal_max) || 500,
      portal_cols: Number(form.portal_cols) || 0,
      // 主题插件定整套画布令牌，主色可以在此基础上手改（custom）
      theme_plugin: pluginKey.value,
      theme_accent: accent.value,
      tag_max_per_project: Number(form.tag_max) || 6,
      tag_bar_limit: Number(form.tag_bar) || 0,
      author: {
        name: form.author.name,
        bio: form.author.bio,
        links: form.author.links.filter((l) => l.url.trim()),
      },
    })
    store.siteTitle = d.site_title || store.siteTitle
    // 标签上限刚被改过，前端那份运行时规则得跟着变，不然别处还按旧数字提示
    applyTagRules(d.tags)
    toast('设置已保存')
    load()
  } catch (e) {
    toast(e.message || '保存失败', 'err')
  } finally {
    busy.value = false
  }
}

async function changePassword() {
  if (pw.new_password.length < 6) return toast('新密码至少 6 位', 'err')
  try {
    await api.post('/api/auth/password', { ...pw })
    toast('密码已更新')
    pw.old_password = ''
    pw.new_password = ''
  } catch (e) {
    toast(e.message || '修改失败', 'err')
  }
}


// ---------------- 自动备份 ----------------
const auto = reactive({})
const autoBusy = ref(false)
async function loadAuto() {
  try { Object.assign(auto, await api.get('/api/backup/auto')) } catch (e) { /* 老后端没有这个接口 */ }
}
async function saveAuto(patch) {
  try {
    Object.assign(auto, await api.patch('/api/backup/auto', patch))
    toast('自动备份设置已保存')
  } catch (e) { toast(e.message || '保存失败', 'err') }
}
async function runAuto() {
  autoBusy.value = true
  try {
    Object.assign(auto, await api.post('/api/backup/auto/run', {}))
    toast('备份完成')
  } catch (e) { toast(e.message || '备份失败', 'err') } finally { autoBusy.value = false }
}
async function delAuto(f) {
  const ok = await confirmAction({ title: '删除这份自动备份？', message: f.name, confirmText: '删除', danger: true })
  if (!ok) return
  try { Object.assign(auto, await api.del('/api/backup/auto/' + f.name)) } catch (e) { toast(e.message || '删除失败', 'err') }
}
onMounted(loadAuto)

// ---------------- 备份与恢复 ----------------
// 恢复来源二选一：服务器上的备份（backupSrc = 文件名）或本地上传（backupFile）
const backupFile = ref(null)
const backupSrc = ref('')
const backupBusy = ref(false)
const backupInfo = ref(null)
const backupLabel = computed(() => backupSrc.value || backupFile.value?.name || '')

function fmtAutoName(n) {
  const m = /^auto-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})\.zip$/.exec(n || '')
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}` : n
}

function pickBackupFile(e) {
  backupFile.value = e.target.files?.[0] || null
  backupSrc.value = ''
  backupInfo.value = null
  e.target.value = ''
  if (backupFile.value) inspectBackup()
}

function pickServerBackup(f) {
  backupSrc.value = f.name
  backupFile.value = null
  backupInfo.value = null
  inspectBackup()
}

function clearBackupPick() {
  backupSrc.value = ''
  backupFile.value = null
  backupInfo.value = null
}

async function inspectBackup() {
  if (!backupSrc.value && !backupFile.value) return toast('先选一个备份', 'err')
  backupBusy.value = true
  try {
    if (backupSrc.value) {
      backupInfo.value = await api.get(`/api/backup/auto/${backupSrc.value}/inspect`)
    } else {
      const fd = new FormData()
      fd.append('file', backupFile.value, backupFile.value.name)
      backupInfo.value = await api.postForm('/api/backup/inspect', fd)
    }
  } catch (e) {
    backupInfo.value = null
    toast(e.message || '读不了这个备份包', 'err')
  } finally {
    backupBusy.value = false
  }
}

async function doRestore() {
  if ((!backupFile.value && !backupSrc.value) || !backupInfo.value) return
  const ok = await confirmAction({
    title: '用这个备份覆盖现网数据？',
    message:
      '当前数据库、项目文件、下载包和站点图标都会被替换成备份里的内容。' +
      '旧数据会保留在 data/.backup-before-restore-<时间>/ 目录，可以手工挪回来。' +
      '恢复后正在预览的页面需要刷新。',
    confirmText: '确认恢复',
    danger: true,
  })
  if (!ok) return
  backupBusy.value = true
  try {
    let d
    if (backupSrc.value) {
      d = await api.post(`/api/backup/auto/${backupSrc.value}/restore`, {})
    } else {
      const fd = new FormData()
      fd.append('file', backupFile.value, backupFile.value.name)
      d = await api.postForm('/api/backup/restore', fd)
    }
    toast(`已恢复：${d.counts?.projects ?? '?'} 个项目，${d.counts?.users ?? '?'} 个账号`)
    clearBackupPick()
    setTimeout(() => location.reload(), 1200)
  } catch (e) {
    toast(e.message || '恢复失败', 'err')
  } finally {
    backupBusy.value = false
  }
}


// ---------------- 分区导航 ----------------
const SECTIONS = [
  { id: 'site', label: '站点', icon: 'sliders' },
  { id: 'look', label: '外观', icon: 'eye' },
  { id: 'defaults', label: '项目默认值', icon: 'clock' },
  { id: 'tags', label: '标签规则', icon: 'folder' },
  { id: 'author', label: '作者名片', icon: 'users' },
  { id: 'account', label: '账号', icon: 'key' },
  { id: 'backup', label: '备份恢复', icon: 'download' },
  { id: 'runtime', label: '运行信息', icon: 'layers' },
  { id: 'about', label: '关于 / 许可', icon: 'check' },
  { id: 'events', label: '最近操作', icon: 'refresh' },
]
const active = ref('site')

function jump(id) {
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  active.value = id
}

let spy = null
onMounted(() => {
  spy = new IntersectionObserver(
    (rows) => {
      const hit = rows
        .filter((r) => r.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0]
      if (hit) active.value = hit.target.id
    },
    { rootMargin: '-72px 0px -55% 0px' }
  )
  SECTIONS.forEach((s) => {
    const el = document.getElementById(s.id)
    if (el) spy.observe(el)
  })
})
onUnmounted(() => spy && spy.disconnect())

// ---------------- 标签规则展示 ----------------
const tagInfo = computed(
  () =>
    data.value?.tags || {
      max_per_project: 6,
      max_per_project_cap: 6,
      max_len: 12,
      pool_max: 300,
      bar_limit: 12,
      bar_limit_max: 40,
      used: 0,
      orphans: 0,
      tagged_projects: 0,
      allowed: '中英文、数字和 + # . - _',
      separators: ', ， 、 ; ； 和空格',
    }
)
// 标签条显示数量：0 = 全部（服务端还会按 bar_limit_max 封顶）
const BAR_OPTS = [8, 12, 16, 24, 0]
const tagPct = computed(() =>
  Math.min(100, Math.round((tagInfo.value.used / Math.max(1, tagInfo.value.pool_max)) * 100))
)

async function pruneTags() {
  try {
    const d = await api.post('/api/settings/tags/prune', {})
    if (data.value) data.value.tags = d.tags
    toast(d.removed ? `已清理 ${d.removed} 个没人用的标签` : '没有可清理的标签')
  } catch (e) {
    toast(e.message || '清理失败', 'err')
  }
}

// ---------------- 未保存提醒 ----------------
const snap = ref('')
const state = computed(() =>
  JSON.stringify({
    t: form.site_title,
    ttl: form.ttl,
    ea: form.default_expire_action,
    pp: form.public_portal,
    pm: form.portal_max,
    pc: form.portal_cols,
    ac: accent.value,
    tp: pluginKey.value,
    au: form.author,
    tm: form.tag_max,
    tb: form.tag_bar,
  })
)
const dirty = computed(() => !!snap.value && state.value !== snap.value)

onMounted(load)
// 没保存就离开：把整套主题退回去，别留下一个「只在这次会话有效」的主题
onUnmounted(() => {
  if (savedBoard) applyPalette({ vars: savedBoard.vars, accent: savedBoard.accent, mode: savedBoard.mode })
})
</script>

<template>
  <header class="topbar">
    <h1>设置</h1>
    <span class="sub">站点级配置</span>
    <div class="grow" />
    <span v-if="dirty" class="dirt" title="有改动还没保存">未保存</span>
    <button class="btn primary" :disabled="busy" @click="save">
      {{ busy ? '保存中…' : '保存更改' }}
    </button>
  </header>

  <div class="content">
    <div class="setwrap">
      <!-- 左侧分区导航：页面长，靠它跳，滚动时自动高亮 -->
      <nav class="setnav" aria-label="设置分区">
        <a
          v-for="s in SECTIONS"
          :key="s.id"
          :href="`#${s.id}`"
          :class="{ on: active === s.id }"
          @click.prevent="jump(s.id)"
        >
          <Icon :name="s.icon" :size="16" />
          <span>{{ s.label }}</span>
        </a>
      </nav>

      <div class="setmain">
        <!-- 站点 -->
        <section id="site" class="panel">
          <div class="panel-head">
            <h2>站点</h2>
            <span class="pdesc">访客看到的标题、图标与门户开关</span>
          </div>
          <div class="panel-body form">
            <div class="frow">
              <label>站点标题</label>
              <input v-model="form.site_title" class="input" placeholder="临时预览站" maxlength="40" />
              <span class="hint">控制台侧栏、门户与访客页的浏览器标题</span>
            </div>

            <div class="frow">
              <label>站点图标</label>
              <div class="iconrow">
                <span class="iconprev" :class="{ def: !siteIcon.custom }">
                  <img :src="iconPreview" alt="站点图标预览" />
                </span>
                <div class="iconacts">
                  <button type="button" class="btn ghost sm" :disabled="iconBusy" @click="pickIcon">
                    {{ iconBusy ? '处理中…' : siteIcon.custom ? '更换图标' : '上传图标' }}
                  </button>
                  <button
                    v-if="siteIcon.custom"
                    type="button"
                    class="btn ghost sm"
                    :disabled="iconBusy"
                    @click="resetIcon"
                  >
                    恢复默认
                  </button>
                  <!-- 真正的选择框：藏起来由上面的按钮代点，少了它 pickIcon 就是空操作 -->
                  <input
                    ref="iconFile"
                    type="file"
                    class="srfile"
                    accept="image/png,image/jpeg,image/webp,image/svg+xml,image/x-icon,.png,.jpg,.jpeg,.webp,.svg,.ico"
                    @change="onIconPicked"
                  />
                </div>
              </div>
              <span class="hint">
                png / svg / ico / jpg / webp，≤{{ siteIcon.max_kb }}KB，建议正方形 512×512 以上；标签页与手机主屏都用它
              </span>
            </div>

            <div class="frow">
              <label>访客门户</label>
              <div class="inlinerow">
                <label class="check">
                  <input v-model="form.public_portal" type="checkbox" />
                  允许未登录访客浏览门户列表
                </label>
                <a class="linkbtn" href="/" target="_blank" rel="noopener">
                  打开门户 <Icon name="external" :size="14" />
                </a>
              </div>
              <span class="hint">关闭后门户首页（/）需要登录；已发出去的直链预览不受影响</span>
            </div>
            <div class="frow">
              <label>每行卡片</label>
              <div class="inlinerow">
                <div class="segs">
                  <button v-for="o in [{v:0,t:'自动'},{v:3,t:'3'},{v:4,t:'4'},{v:5,t:'5'}]" :key="o.v" type="button"
                    class="btn sm" :class="{ primary: form.portal_cols === o.v }" @click="form.portal_cols = o.v">{{ o.t }}</button>
                </div>
              </div>
              <span class="hint">门户卡片视图每行最多几张。自动＝按屏幕宽度铺满；卡片最小 260px，屏幕不够宽时自动减列，不会出现半张</span>
            </div>
            <div class="frow">
              <label>门户上限</label>
              <div class="inlinerow">
                <label style="display: flex; align-items: center; gap: 7px; font-size: 13px">
                  门户与 RSS 最多列出
                  <input
                    v-model.number="form.portal_max"
                    type="number"
                    class="field"
                    style="width: 96px"
                    min="50"
                    max="5000"
                    step="50"
                  />
                  个项目
                </label>
              </div>
              <span class="hint">
                按创建时间取最新的 N 个，超出的不在门户和 RSS 里显示，但直链照常可用。
                门户整页渲染，每个项目约 1–2 KB，数值越大首页越重（范围 50–5000，默认 500）
              </span>
            </div>
          </div>
        </section>

        <!-- 外观 -->
        <section id="look" class="panel">
          <div class="panel-head">
            <h2>外观</h2>
            <span class="pdesc">主题插件定整套画布令牌，控制台、门户、访客页共用</span>
          </div>
          <div class="panel-body form">
            <div class="frow">
              <label>主题</label>
              <div v-if="plugins.length" class="seriesgrid">
                <button
                  v-for="p in plugins"
                  :key="p.id"
                  type="button"
                  class="scard"
                  :class="{ on: pluginKey === p.id }"
                  :style="{
                    background: p.preview.bg,
                    color: p.preview.ink,
                    borderColor: p.mode === 'dark' ? 'rgba(255,255,255,.14)' : 'rgba(20,22,26,.12)',
                    '--chip': p.preview.accent,
                    '--sdim': p.mode === 'dark' ? 'rgba(255,255,255,.6)' : 'rgba(20,22,26,.6)',
                    '--sfaint': p.mode === 'dark' ? 'rgba(255,255,255,.4)' : 'rgba(20,22,26,.42)',
                  }"
                  @click="pickPlugin(p)"
                >
                  <span class="stop">
                    <i :style="{ background: p.preview.accent }">Aa</i>
                    <b>{{ p.name }}</b>
                    <span class="smode" :class="p.mode">{{ p.mode === 'dark' ? '深色' : '浅色' }}</span>
                    <svg v-if="pluginKey === p.id" class="sok" viewBox="0 0 16 16" aria-hidden="true">
                      <path d="M3.6 8.4 6.3 11 12.4 4.8" />
                    </svg>
                  </span>
                  <span class="sdesc">{{ p.desc }}</span>
                  <span class="suse">
                    {{ p.builtin ? '内置' : '插件' }} · v{{ p.version }}<template v-if="p.author"> · {{ p.author }}</template>
                  </span>
                  <span
                    v-if="!p.builtin"
                    class="sdel"
                    role="button"
                    tabindex="-1"
                    title="卸载这个主题插件"
                    @click.stop="uninstallTheme(p)"
                  >卸载</span>
                </button>
              </div>
              <span v-else class="hint">主题清单没读到，刷新一下页面</span>
              <span class="hint">
                每套主题是一份 theme.json 语义令牌清单（画布、容器、文字、描边、阴影）。
                内置「玄夜」（深）与「象牙」（浅）；点一下即时预览，「保存更改」后才对访客生效
              </span>
            </div>

            <div class="frow">
              <label>主题商店</label>
              <div class="colorrow">
                <button type="button" class="btn" @click="shop.open = true">
                  <Icon name="external" :size="16" /> 打开主题商店
                </button>
                <span class="hint" style="margin-left: 2px">
                  填一个 GitHub 仓库（owner/repo、仓库链接均可），枚举里面的 theme.json 一键安装
                </span>
              </div>
            </div>

            <div class="frow">
              <label>主色微调</label>
              <div class="colorrow">
                <input
                  type="color"
                  class="colorpick"
                  :value="accent"
                  aria-label="取色器"
                  @input="pickAccent($event.target.value)"
                />
                <input
                  v-model="accentInput"
                  class="input mono"
                  style="max-width: 132px"
                  maxlength="7"
                  spellcheck="false"
                  @blur="pickAccent(accentInput)"
                  @keyup.enter="pickAccent(accentInput)"
                />
                <span v-if="custom" class="ctag">已自定义</span>
                <button type="button" class="btn ghost sm" @click="resetTheme()">回到主题默认</button>
              </div>
              <span class="hint">主题画布不动，只改强调色；按钮、胶囊、圆环等仍由主色自动派生</span>
              <span v-if="dimmed" class="hint warnhint">
                这个主色在当前画布上对比度不足（&lt; 3:1），实际会按 <code>{{ dimmed }}</code> 渲染
              </span>
            </div>

            <div class="frow">
              <label>效果</label>
              <div class="themepre">
                <span class="tp-pill">门户可见</span>
                <span class="tp-link">示例链接</span>
                <button type="button" class="tp-btn">主按钮</button>
                <span class="tp-ring"><i></i></span>
              </div>
              <span class="hint">hover、软底、描边、渐变深浅仍由主色按明暗模式自动派生，不用手调</span>
            </div>
          </div>
        </section>

        <!-- 项目默认值 -->
        <section id="defaults" class="panel">
          <div class="panel-head">
            <h2>项目默认值</h2>
            <span class="pdesc">新建项目时预填的存活时长与到期动作</span>
          </div>
          <div class="panel-body form">
            <div class="frow">
              <label>默认时长</label>
              <div class="ttlgrid">
                <div v-for="v in VIS" :key="v.key" class="ttlcell">
                  <input v-model.number="form.ttl[v.key]" class="input" type="number" min="0" step="1" />
                  <b>{{ v.label }}</b>
                  <span>{{ v.hint }}</span>
                </div>
              </div>
              <span class="hint">单位小时，填 0 表示永久；按可见性分三档，上传时可以不填、自动套用</span>
            </div>

            <div class="frow">
              <label>到期后</label>
              <div class="optcards">
                <button
                  type="button"
                  class="optcard"
                  :class="{ on: form.default_expire_action === 'block' }"
                  @click="form.default_expire_action = 'block'"
                >
                  <b>停止访问</b>
                  <span>文件留在磁盘，续期后立刻恢复；门户卡片到点变灰</span>
                </button>
                <button
                  type="button"
                  class="optcard del"
                  :class="{ on: form.default_expire_action === 'delete' }"
                  @click="form.default_expire_action = 'delete'"
                >
                  <b>删除文件</b>
                  <span>连目录一起清掉，不可恢复；这类项目在门户上带琥珀色标记</span>
                </button>
              </div>
              <span class="hint">只是新建时的预选，单个项目仍可在详情里改</span>
            </div>
          </div>
        </section>

        <!-- 标签规则 -->
        <section id="tags" class="panel">
          <div class="panel-head">
            <h2>标签规则</h2>
            <span class="pdesc">标签用来筛选和归类，定死上限才不会被填成一团乱麻</span>
          </div>
          <div class="panel-body form">
            <div class="frow">
              <label>规则</label>
              <ul class="rules">
                <li class="rule">
                  <i></i><span>每个项目最多 <b>{{ tagInfo.max_per_project }} 个</b>标签，单个最长
                    <b>{{ tagInfo.max_len }} 字</b></span>
                </li>
                <li class="rule">
                  <i></i><span>只能用<b>{{ tagInfo.allowed }}</b>；不许空格，全角自动转半角</span>
                </li>
                <li class="rule">
                  <i></i><span>英文统一小写、重名自动合并：<b>Vue / VUE / vue</b> 是同一个标签</span>
                </li>
                <li class="rule">
                  <i></i><span>分隔符支持 <b>{{ tagInfo.separators }}</b>，超额或非法字符会直接提示，不会静默截断</span>
                </li>
              </ul>
            </div>

            <div class="frow">
              <label>限制</label>
              <div style="display: flex; flex-wrap: wrap; gap: 16px 20px; align-items: center">
                <label style="display: flex; align-items: center; gap: 7px; font-size: 13px">
                  每个项目最多
                  <select v-model.number="form.tag_max" class="field" style="width: 74px">
                    <option v-for="n in tagInfo.max_per_project_cap || 6" :key="n" :value="n">
                      {{ n }}
                    </option>
                  </select>
                  个标签
                </label>
                <label style="display: flex; align-items: center; gap: 7px; font-size: 13px">
                  门户标签条最多显示
                  <select v-model.number="form.tag_bar" class="field" style="width: 96px">
                    <option v-for="n in BAR_OPTS" :key="n" :value="n">
                      {{ n === 0 ? '全部' : n + ' 个' }}
                    </option>
                  </select>
                </label>
              </div>
              <span class="hint">
                标签条按被引用的次数从多到少排，只放常用的前几个，剩下的折成「还有 N 个」；
                选「全部」则不限制（最多 {{ tagInfo.bar_limit_max || 40 }} 个）。调小后新建项目时超出直接提示，不会静默截断
              </span>
            </div>

            <div class="frow">
              <label>池子占用</label>
              <div class="usage">
                <div class="meter" :class="{ hot: tagPct >= 85 }">
                  <i :style="{ width: tagPct + '%' }" />
                </div>
                <span class="usagetext">
                  全站 <b>{{ tagInfo.used }}</b> / {{ tagInfo.pool_max }} 个（{{ tagPct }}%）·
                  {{ tagInfo.tagged_projects }} 个项目有标签
                </span>
                <button type="button" class="btn ghost sm" :disabled="!tagInfo.orphans" @click="pruneTags">
                  <Icon name="trash" :size="14" />
                  清理没人用的{{ tagInfo.orphans ? `（${tagInfo.orphans}）` : '' }}
                </button>
              </div>
              <span class="hint">
                改标签或删项目时会自动回收没人引用的标签；池子满了只能复用已有标签，不能再造新的
              </span>
            </div>
          </div>
        </section>

        <!-- 作者名片 -->
        <section id="author" class="panel">
          <div class="panel-head">
            <h2>作者名片</h2>
            <span class="pdesc">展示在门户首页（<span class="mono">/</span>）顶部</span>
          </div>
          <div class="panel-body author-grid">
            <div class="form">
              <div class="frow">
                <label>显示名</label>
                <input v-model="form.author.name" class="input" placeholder="vita" maxlength="40" />
                <span class="hint">默认 vita；不用写真实姓名</span>
              </div>
              <div class="frow">
                <label>一句话介绍</label>
                <input v-model="form.author.bio" class="input" placeholder="互联网混子" maxlength="120" />
                <span class="hint">默认「互联网混子」，随时可改</span>
              </div>

              <div class="frow">
                <label>链接</label>
                <div class="linkrows">
                  <div
                    v-for="(l, i) in form.author.links"
                    :key="i"
                    class="linkrow"
                    :class="{ dragging: dragFrom === i, dropover: dragOver === i && dragFrom !== i }"
                    @dragover.prevent="dragOver = i"
                    @drop.prevent="dropLink(i)"
                  >
                    <span
                      class="grip"
                      draggable="true"
                      title="拖动调整顺序"
                      @dragstart="dragStart(i, $event)"
                      @dragend="dragFrom = dragOver = -1"
                    >⋮⋮</span>
                    <div class="typesel" :class="{ open: openType === i }">
                      <button type="button" class="ts-btn" @click.stop="toggleType(i, $event)">
                        <svg class="ts-ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"
                             stroke-linecap="round" stroke-linejoin="round" v-html="typeIcon(l.type)" />
                        <span class="ts-lbl">{{ typeLabel(l.type) }}</span>
                        <svg class="ts-caret" width="10" height="10" viewBox="0 0 16 16" fill="none"
                             stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                          <path d="M4 6.5 8 10.5 12 6.5" />
                        </svg>
                      </button>
                    </div>

                    <input v-model="l.label" class="input lab" placeholder="显示文字" maxlength="20" />
                    <input
                      v-model="l.url"
                      class="input url"
                      :placeholder="l.type === 'mail' ? 'hi@example.com' : 'https://…（可省略 https://）'"
                    />
                    <span class="mv">
                      <button type="button" class="btn sm ghost" title="上移" :disabled="i === 0" @click="moveLink(i, -1)">↑</button>
                      <button type="button" class="btn sm ghost" title="下移" :disabled="i === form.author.links.length - 1" @click="moveLink(i, 1)">↓</button>
                    </span>
                    <button class="btn sm ghost del" title="删除这条" @click="removeLink(i)">
                      <Icon name="close" :size="14" />
                    </button>
                  </div>

                  <div v-if="!form.author.links.length" class="dim emptyhint">
                    还没有链接。加几个，访客门户顶部就会出现对应的图标。
                  </div>
                  <div>
                    <button class="btn sm" @click="addLink"><Icon name="plus" :size="14" /> 添加链接</button>
                  </div>
                </div>
                <span class="hint">
                  类型决定图标，标签留空就用类型默认名；邮箱只填地址即可，其他地址可省略 https://
                </span>
              </div>
            </div>

            <aside class="pvwrap">
              <div class="pvlabel">门户预览</div>
              <div class="pvcard">
                <div class="pvava">{{ (form.author.name || '·').slice(0, 1).toUpperCase() }}</div>
                <div class="pvmeta">
                  <b>{{ form.author.name || '未填写显示名' }}</b>
                  <span>{{ form.author.bio || '一句话介绍会显示在这里' }}</span>
                </div>
                <div v-if="previewLinks.length" class="pvlinks">
                  <span v-for="(l, i) in previewLinks" :key="i" class="pvlink" :title="l.url">
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"
                         stroke-linecap="round" stroke-linejoin="round" v-html="typeIcon(l.type)" />
                    <span>{{ l.label }}</span>
                  </span>
                </div>
              </div>
              <div class="hint" style="margin-top: 8px">
                门户窄屏下只留图标，标签自动隐藏。最多 12 个链接。
              </div>
            </aside>
          </div>
        </section>

        <!-- 账号 -->
        <section id="account" class="panel">
          <div class="panel-head">
            <h2>账号</h2>
            <span class="pdesc">当前登录：{{ store.user?.display_name || store.user?.username || '—' }}</span>
          </div>
          <div class="panel-body form">
            <div class="frow">
              <label>当前密码</label>
              <input
                v-model="pw.old_password"
                class="input"
                type="password"
                autocomplete="current-password"
                style="max-width: 280px"
              />
            </div>
            <div class="frow">
              <label>新密码</label>
              <div class="colorrow">
                <input
                  v-model="pw.new_password"
                  class="input"
                  type="password"
                  autocomplete="new-password"
                  style="max-width: 280px"
                />
                <button class="btn" @click="changePassword">更新密码</button>
              </div>
              <span class="hint">至少 6 位；改完其他设备上的登录态会失效</span>
            </div>
          </div>
        </section>

        <!-- 备份与恢复 -->
        <section id="backup" class="panel">
          <div class="panel-head">
            <h2>备份与恢复</h2>
            <span class="pdesc">数据库 + 项目文件 + 下载包 + 站点图标 + 主题插件，一个 zip 全带走</span>
          </div>
          <div class="panel-body form">
            <div class="frow">
              <label>下载备份</label>
              <div class="colorrow">
                <a class="btn" href="/api/backup" download>
                  <Icon name="download" :size="16" /> 打包下载
                </a>
                <span class="hint" style="margin: 0">
                  边打包边下载，不占服务器临时空间；数据库用在线快照，正在写入也不会拷到半截
                </span>
              </div>
            </div>

            <div class="frow">
              <label>自动备份</label>
              <div class="colorrow" style="flex-wrap: wrap; gap: 8px">
                <button type="button" class="btn sm" :class="{ primary: auto.enabled }" @click="saveAuto({ enabled: !auto.enabled })">
                  {{ auto.enabled ? '已开启' : '已关闭' }}
                </button>
                <span class="hint" style="margin: 0">每天</span>
                <select class="input" style="width: 84px" :value="auto.hour" @change="saveAuto({ hour: +$event.target.value })">
                  <option v-for="h in 24" :key="h" :value="h - 1">{{ String(h - 1).padStart(2, '0') }}:00</option>
                </select>
                <span class="hint" style="margin: 0">保留最近</span>
                <input class="input" type="number" min="1" max="60" style="width: 70px" :value="auto.keep" @change="saveAuto({ keep: +$event.target.value })" />
                <span class="hint" style="margin: 0">份</span>
                <button type="button" class="btn sm" :disabled="autoBusy" @click="runAuto">{{ autoBusy ? '备份中…' : '立即备份一次' }}</button>
              </div>
              <span class="hint">
                存在服务器 data/backups/，按服务器时区（{{ auto.server_time || '—' }}）。
                已有 {{ auto.files?.length || 0 }} 份，共 {{ fmtBytes(auto.total_size || 0) }}，磁盘剩余 {{ fmtBytes(auto.disk_free || 0) }}。
                <template v-if="auto.last_at">上次成功 {{ relTime(auto.last_at) }}。</template>
                <b v-if="auto.last_error" style="color: var(--danger)">上次失败：{{ auto.last_error }}</b>
              </span>
            </div>

            <div class="frow">
              <label>备份列表</label>
              <div class="bklist">
                <div v-if="!auto.files?.length" class="bkempty">服务器上还没有备份，点上面「立即备份一次」生成第一份</div>
                <div
                  v-for="(f, i) in auto.files"
                  :key="f.name"
                  class="bkrow"
                  :class="{ on: backupSrc === f.name }"
                >
                  <Icon name="clock" :size="16" class="bkicon" />
                  <div class="bkmain">
                    <div class="bktime">
                      {{ fmtAutoName(f.name) }}
                      <span v-if="i === 0" class="badge">最新</span>
                    </div>
                    <div class="bkmeta">{{ fmtBytes(f.size) }} · {{ relTime(f.at) }}</div>
                  </div>
                  <div class="bkacts">
                    <button type="button" class="btn sm" :class="{ primary: backupSrc === f.name }" :disabled="backupBusy" @click="pickServerBackup(f)">
                      {{ backupSrc === f.name ? '已选中' : '用它恢复' }}
                    </button>
                    <a class="btn sm ghost" title="下载" :href="'/api/backup/auto/' + f.name" download><Icon name="download" :size="16" /></a>
                    <button type="button" class="btn sm ghost" title="删除" style="color: var(--danger)" @click="delAuto(f)"><Icon name="trash" :size="16" /></button>
                  </div>
                </div>
              </div>
            </div>

            <div class="frow">
              <label>从备份恢复</label>
              <div style="flex: 1; min-width: 0">
                <div class="colorrow" style="flex-wrap: wrap; gap: 8px">
                  <button class="btn" :disabled="backupBusy" @click="$refs.bk.click()">
                    <Icon name="upload" :size="16" /> 上传外部备份 zip
                  </button>
                  <input ref="bk" type="file" accept=".zip,application/zip" style="display: none" @change="pickBackupFile" />
                  <span class="hint" style="margin: 0">或在上面的列表里点「用它恢复」</span>
                </div>

                <div v-if="backupLabel" class="bkpick">
                  <div class="bkpick-head">
                    <span>
                      {{ backupSrc ? '服务器备份' : '本地文件' }}：<b class="mono">{{ backupSrc ? fmtAutoName(backupSrc) : backupLabel }}</b>
                    </span>
                    <button type="button" class="btn sm ghost" :disabled="backupBusy" @click="clearBackupPick">取消</button>
                  </div>
                  <div v-if="backupBusy && !backupInfo" class="hint" style="margin: 6px 0 0">正在读取备份内容…</div>
                  <template v-else-if="backupInfo">
                    <div class="bkstats">
                      <span><b>{{ backupInfo.manifest?.counts?.projects ?? '?' }}</b> 个项目</span>
                      <span><b>{{ backupInfo.manifest?.counts?.users ?? '?' }}</b> 个账号</span>
                      <span><b>{{ backupInfo.files }}</b> 个文件</span>
                      <span><b>{{ backupInfo.zips }}</b> 个下载包</span>
                      <span><b>{{ backupInfo.themes }}</b> 个主题插件</span>
                    </div>
                    <div v-if="backupInfo.manifest?.created_at" class="hint" style="margin: 4px 0 0">
                      备份于 {{ new Date(backupInfo.manifest.created_at).toLocaleString() }}
                      <template v-if="backupInfo.manifest.site_title"> · {{ backupInfo.manifest.site_title }}</template>
                    </div>
                    <div v-else class="hint" style="margin: 4px 0 0">老格式备份：没有清单信息，恢复后会自动迁移数据库</div>
                    <button class="btn danger" style="margin-top: 10px" :disabled="backupBusy" @click="doRestore">
                      {{ backupBusy ? '恢复中…' : '覆盖恢复' }}
                    </button>
                  </template>
                </div>

                <span class="hint">
                  恢复会替换现网数据；旧数据保留在 data/.backup-before-restore-&lt;时间&gt;/，只留最近 3 份。服务器上的备份列表不受恢复影响。
                </span>
              </div>
            </div>

            <div v-if="backupInfo" class="panel" style="padding: 10px 12px; background: var(--surface-2); box-shadow: none">
              <div style="display: flex; gap: 14px; flex-wrap: wrap; font-size: 12px">
                <span v-if="backupInfo.manifest?.counts">
                  项目 <b class="num">{{ backupInfo.manifest.counts.projects }}</b>
                </span>
                <span v-if="backupInfo.manifest?.counts">
                  账号 <b class="num">{{ backupInfo.manifest.counts.users }}</b>
                </span>
                <span v-if="backupInfo.manifest?.counts">
                  分组 <b class="num">{{ backupInfo.manifest.counts.collections }}</b>
                </span>
                <span class="dim">文件 {{ backupInfo.files }} 个</span>
                <span v-if="backupInfo.manifest?.created_at" class="dim">
                  备份于 {{ new Date(backupInfo.manifest.created_at).toLocaleString() }}
                </span>
              </div>
              <div class="hint" style="margin-top: 6px; color: var(--danger)">
                确认无误再点「覆盖恢复」，这是不可撤销操作（旧数据另存一份）。
              </div>
            </div>
          </div>
        </section>

        <!-- 运行信息 -->
        <section id="runtime" class="panel">
          <div class="panel-head">
            <h2>运行信息</h2>
            <span class="pdesc">只读，方便排查磁盘和配额</span>
          </div>
          <div class="panel-body">
            <dl v-if="data" class="kv runtime">
              <dt>数据目录</dt>
              <dd class="mono">{{ data.runtime.data_dir }}</dd>
              <dt>项目 / 占用</dt>
              <dd>{{ data.runtime.projects }} 个 · {{ fmtBytes(data.runtime.size_bytes) }}</dd>
              <dt>账号</dt>
              <dd>{{ data.runtime.agents }} 个</dd>
              <dt>上传上限</dt>
              <dd>{{ data.runtime.max_upload_mb }} MB / 项目</dd>
              <dt>会话时长</dt>
              <dd>{{ data.runtime.session_days }} 天 · 时区 {{ data.runtime.tz }}</dd>
            </dl>
            <div v-else class="skel" style="height: 96px" />
          </div>
        </section>

        <!-- 关于 / 许可：AGPL-3.0 §7(b) 要求保留出处与署名，别把这块删了 -->
        <section id="about" class="panel">
          <div class="panel-head">
            <h2>关于 / 许可</h2>
            <span class="pdesc">开源信息与出处，请勿删除</span>
          </div>
          <div class="panel-body">
            <dl class="kv runtime">
              <dt>项目</dt>
              <dd>
                <a :href="store.project.url" target="_blank" rel="noopener">{{ store.project.name }}</a>
              </dd>
              <dt>作者</dt>
              <dd>{{ store.project.author }}</dd>
              <dt>许可</dt>
              <dd>
                {{ store.project.license }} ·
                <a href="https://www.gnu.org/licenses/agpl-3.0.txt" target="_blank" rel="noopener">许可证全文</a>
              </dd>
              <dt>源码</dt>
              <dd class="mono">{{ store.project.url }}</dd>
            </dl>

            <div class="verbox">
              <div class="verline">
                <b>当前版本</b>
                <span class="mono">{{ store.version || '—' }}</span>
                <button class="btn ghost sm" :disabled="verBusy" @click="checkVersion(true)">
                  {{ verBusy ? '检查中…' : '检查更新' }}
                </button>
                <span v-if="ver" class="hint" style="margin: 0">
                  <template v-if="!ver.ok">检查失败（{{ ver.error }}）</template>
                  <template v-else-if="ver.has_update">
                    有新版本 <b>{{ ver.latest }}</b> ·
                    <a :href="ver.url" target="_blank" rel="noopener">查看更新</a>
                  </template>
                  <template v-else>已是最新</template>
                </span>
              </div>
              <details v-if="ver?.has_update && ver.notes" class="upd">
                <summary>更新内容（{{ ver.latest }}）</summary>
                <pre>{{ ver.notes }}</pre>
              </details>
            </div>
            <dl class="kv runtime" style="margin-top: 14px">
              <dt>GitHub</dt>
              <dd>
                <a href="https://github.com/Vita0519" target="_blank" rel="noopener">github.com/Vita0519</a>
              </dd>
              <dt>反馈邮箱</dt>
              <dd class="mono">admin@allfather.de5.net</dd>
              <dt>交流群</dt>
              <dd class="mono">QQ 154578485</dd>
            </dl>

            <div class="qrgrid">
              <figure class="qrbox">
                <b>微信赞赏</b>
                <img src="/qr-wechat.png" alt="微信赞赏码" class="qrimg" />
                <span class="hint" style="margin: 0">扫码支持作者</span>
              </figure>
              <figure class="qrbox">
                <b>支付宝赞赏</b>
                <img src="/qr-alipay.png" alt="支付宝赞赏码" class="qrimg" />
                <span class="hint" style="margin: 0">扫码支持作者</span>
              </figure>
            </div>

            <p class="muted" style="margin: 10px 0 0; font-size: 12px; line-height: 1.7">
              本程序以 {{ store.project.license }} 发布：修改后分发、或把它作为网络服务对外提供，
              都必须按 AGPL 第 13 条向使用者提供完整源码，并保留此处的出处与署名。
              如果你是被交付的一方，可以直接向部署者索要对应源码。
            </p>
          </div>
        </section>

        <!-- 最近操作 -->
        <section id="events" class="panel">
          <div class="panel-head">
            <h2>最近操作</h2>
            <span class="pdesc">最近 20 条</span>
          </div>
          <div class="panel-body">
            <div v-if="data?.events?.length" class="events">
              <div v-for="(e, i) in data.events" :key="i" class="evrow">
                <span class="badge">{{ actionLabel(e.action) }}</span>
                <span class="muted truncate">{{ e.detail || '—' }}</span>
                <span class="dim">{{ relTime(e.at) }}</span>
              </div>
            </div>
            <p v-else class="dim" style="font-size: 12px">暂无记录</p>
          </div>
        </section>
      </div>
    </div>
  </div>

  <!-- 类型浮层挂到 body：卡片是 overflow:hidden，放里面底部会被吃掉 -->
  <Teleport to="body">
    <div
      v-if="openType >= 0 && form.author.links[openType]"
      class="ts-pop"
      :style="popStyle"
      @click.stop
    >
      <button
        v-for="t in authorTypes"
        :key="t.key"
        type="button"
        :class="{ on: t.key === form.author.links[openType].type }"
        @click="pickType(form.author.links[openType], t.key)"
      >
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"
             stroke-linecap="round" stroke-linejoin="round" v-html="t.paths" />
        {{ t.label }}
      </button>
    </div>
  </Teleport>

  <!-- 主题商店：拉取 GitHub 仓库里的 theme.json 并安装 -->
  <Teleport to="body">
    <template v-if="shop.open">
      <div class="scrim" @click="shop.open = false" />
      <div class="modal storemodal">
        <div class="modal-head">
          <h2>主题商店</h2>
          <span class="pdesc">从 GitHub 仓库安装主题插件</span>
          <div class="grow" style="flex: 1" />
          <button class="btn ghost icon" title="关闭" @click="shop.open = false">
            <Icon name="close" :size="16" />
          </button>
        </div>
        <div class="modal-body">
          <div class="storerepo">
            <input
              v-model="shop.repo"
              class="input mono"
              placeholder="owner/repo 或 https://github.com/owner/repo"
              spellcheck="false"
              @keyup.enter="storeFetch"
            />
            <button class="btn" type="button" :disabled="shop.busy || !shop.repo.trim()" @click="storeFetch">
              {{ shop.busy ? '拉取中…' : '拉取' }}
            </button>
            <button
              class="btn ghost sm"
              type="button"
              :disabled="shop.installing === 'example'"
              title="安装仓库自带的示例主题插件（examples/theme-plugin）"
              @click="installExample"
            >
              {{ shop.installing === 'example' ? '安装中…' : '装示例插件' }}
            </button>
          </div>
          <p class="hint" style="margin-top: 6px">
            仓库里任意位置的 <code>theme.json</code> 都会被枚举出来；也可以直接填到文件或目录的 GitHub 链接。
            清单格式见仓库 <code>examples/theme-plugin/README.md</code>
          </p>
          <div v-if="shop.error" class="storeerr">{{ shop.error }}</div>

          <div v-if="shop.items.length" class="storelist">
            <div v-for="it in shop.items" :key="it.repo + it.path" class="storeitem">
              <template v-if="it.manifest">
                <div class="shead">
                  <span class="sname">{{ it.manifest.name }}</span>
                  <span class="sver">v{{ it.manifest.version }}</span>
                  <span class="smode" :class="it.manifest.mode">{{ it.manifest.mode === 'dark' ? '深色' : '浅色' }}</span>
                  <div class="grow" style="flex: 1" />
                  <button
                    class="btn sm primary"
                    type="button"
                    :disabled="shop.installing === it.path"
                    @click="storeInstall(it)"
                  >
                    {{ shop.installing === it.path ? '安装中…' : '安装' }}
                  </button>
                </div>
                <div class="sdesc2">{{ it.manifest.desc || '（没有描述）' }}</div>
                <div class="smeta">
                  <span class="mono">{{ it.path }}</span>
                  <span v-if="it.manifest.author"> · {{ it.manifest.author }}</span>
                </div>
                <div class="sstrip">
                  <i
                    v-for="(v, k) in stripOf(it.manifest)"
                    :key="k"
                    :style="{ background: v }"
                  />
                </div>
              </template>
              <template v-else>
                <div class="shead">
                  <span class="mono">{{ it.path }}</span>
                </div>
                <div class="storeerr" style="margin-top: 6px">{{ it.error }}</div>
              </template>
            </div>
          </div>
        </div>
        <div class="modal-foot">
          <button class="btn" type="button" @click="shop.open = false">关闭</button>
        </div>
      </div>
    </template>
  </Teleport>
</template>

<style scoped>
.bklist { flex: 1; min-width: 0; display: flex; flex-direction: column; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; max-height: 300px; overflow-y: auto; }
.bkempty { padding: 14px; font-size: 12.5px; color: var(--ink-3, var(--ink-4)); }
.bkrow { display: flex; align-items: center; gap: 10px; padding: 9px 12px; border-top: 1px solid var(--line); transition: background .15s; }
.bkrow:first-child { border-top: 0; }
.bkrow:hover { background: rgba(var(--ink-rgb, 255,255,255), .03); }
.bkrow.on { background: color-mix(in srgb, var(--brand) 10%, transparent); }
.bkicon { color: var(--ink-3, var(--ink-4)); flex: none; }
.bkmain { flex: 1; min-width: 0; }
.bktime { font-size: 13px; font-variant-numeric: tabular-nums; display: flex; align-items: center; gap: 6px; }
.bkmeta { font-size: 11.5px; color: var(--ink-3, var(--ink-4)); margin-top: 1px; }
.bkacts { display: flex; align-items: center; gap: 4px; flex: none; }
.bkpick { margin-top: 10px; padding: 12px 14px; border: 1px solid var(--line-2, var(--line)); border-radius: 10px; background: var(--surface); }
.bkpick-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 13px; }
.bkpick-head b { word-break: break-all; }
.bkstats { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-top: 8px; font-size: 12.5px; color: var(--ink-3, var(--ink-4)); }
.bkstats b { color: var(--ink, inherit); font-variant-numeric: tabular-nums; }
@media (max-width: 640px) {
  .bkrow { flex-wrap: wrap; }
  .bkacts { width: 100%; justify-content: flex-end; }
}
.segs { display: inline-flex; gap: 4px; flex-wrap: wrap; }
.segs .btn { min-width: 44px; }
/* ---------------- 布局：左导航 + 右单列 ----------------
   原来是一堆面板挤在双列网格里，左右高度不一样就到处是空洞；
   现在统一成「左侧分区导航 + 右侧单列纵向」，阅读顺序和滚动方向一致。 */
.setwrap {
  display: grid;
  grid-template-columns: 158px minmax(0, 860px);
  gap: 28px;
  align-items: start;
}
.setnav {
  position: sticky;
  top: 76px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-top: 2px;
}
.setnav a {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 30px;
  padding: 0 9px;
  border-radius: 7px;
  border: 1px solid transparent;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink-3);
  text-decoration: none;
  transition: background 0.16s var(--ease), color 0.16s var(--ease);
}
.setnav a:hover { background: var(--surface-2); color: var(--ink); }
.setnav a.on {
  background: var(--brand-soft);
  color: var(--brand);
  border-color: var(--brand-line);
}
.setnav svg { flex: 0 0 auto; opacity: 0.9; }

.setmain { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.setmain .panel { scroll-margin-top: 78px; }
.pdesc {
  min-width: 0;
  font-size: 11.5px;
  color: var(--ink-4);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dirt {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  color: var(--warn);
  background: var(--warn-soft);
  border: 1px solid rgba(245, 158, 11, 0.3);
}

/* 字段统一「左边标签 + 右边控件」，一行一个，眼睛不用来回找 */
.setmain .form .frow {
  grid-template-columns: 104px minmax(0, 1fr);
  gap: 2px 16px;
  align-items: start;
}
.setmain .form .frow > label {
  padding-top: 8px;
  font-size: 12px;
  color: var(--ink-2);
  white-space: nowrap;
}
.setmain .form .frow > .hint { grid-column: 2; margin-top: 1px; }
.inlinerow { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.linkbtn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--brand);
  text-decoration: none;
}
.linkbtn:hover { text-decoration: underline; text-underline-offset: 2px; }

/* ---- 站点图标 ---- */
.iconrow { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.iconprev {
  width: 46px;
  height: 46px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border-radius: 12px;
  border: 1px solid var(--line-2, var(--line));
  background: var(--surface-2);
  overflow: hidden;
}
.iconprev img { width: 30px; height: 30px; object-fit: contain; display: block; }
.iconprev.def { background: var(--surface-3); }
.iconacts { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; position: relative; }
/* 选择框藏起来但保留可点击性（display:none 在部分浏览器上 programmatic click 会失效） */
.srfile {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  border: 0;
  overflow: hidden;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  white-space: nowrap;
}

/* ---- 配色系列：卡片本身就是一张缩略预览（底色/文字色/主色都是该系列的真值） ---- */
.seriesgrid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  padding-top: 4px;
  width: 100%;
}
.scard {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 11px 12px 10px;
  border-radius: 11px;
  border: 1px solid;
  text-align: left;
  font: inherit;
  cursor: pointer;
  min-height: 98px;
  transition: transform 0.16s var(--ease), box-shadow 0.16s var(--ease);
}
.scard:hover { transform: translateY(-1px); box-shadow: 0 10px 22px -14px rgba(0, 0, 0, 0.55); }
.scard.on { box-shadow: 0 0 0 2px var(--chip); }
.scard .stop { display: flex; align-items: center; gap: 7px; min-width: 0; }
.scard .stop i {
  flex: 0 0 auto;
  width: 24px;
  height: 24px;
  border-radius: 7px;
  display: grid;
  place-items: center;
  color: #fff;
  font-style: normal;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: -0.02em;
}
.scard .stop b { font-size: 13px; font-weight: 650; letter-spacing: -0.01em; }
.scard .sok {
  margin-left: auto;
  width: 13px;
  height: 13px;
  flex: 0 0 auto;
  fill: none;
  stroke: var(--chip);
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.scard .sdesc {
  font-size: 11.5px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.scard .suse { margin-top: auto; font-size: 10.5px; font-weight: 600; letter-spacing: 0.01em; color: var(--sfaint, var(--ink-4)); }
.scard .sdesc { color: var(--sdim, var(--ink-3)); }
/* 明暗模式徽章 + 卸载按钮（只在非内置卡片上出现） */
.scard .smode {
  margin-left: auto;
  flex: 0 0 auto;
  font-size: 9.5px;
  font-weight: 650;
  padding: 1px 6px;
  border-radius: 999px;
  letter-spacing: 0.02em;
}
.scard .smode.dark { background: rgba(255, 255, 255, 0.12); color: rgba(255, 255, 255, 0.75); }
.scard .smode.light { background: rgba(20, 22, 26, 0.08); color: rgba(20, 22, 26, 0.65); }
.scard .sdel {
  position: absolute;
  right: 10px;
  bottom: 8px;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--sfaint, var(--ink-4));
  cursor: pointer;
  border-radius: 4px;
  padding: 1px 5px;
}
.scard .sdel:hover { color: var(--danger); background: var(--danger-soft); }
.scard { position: relative; }

/* ---------------- 主题商店弹窗 ---------------- */
.storemodal { width: 640px; }
.storerepo { display: flex; gap: 8px; flex-wrap: wrap; }
.storerepo .input { flex: 1 1 240px; min-width: 0; }
.storeerr {
  margin-top: 10px;
  background: var(--danger-soft);
  color: var(--danger);
  border: 1px solid var(--danger-line);
  border-radius: var(--radius-xs);
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.5;
  word-break: break-all;
}
.storelist { display: flex; flex-direction: column; gap: 10px; margin-top: 14px; }
.storeitem {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 11px 12px;
  background: var(--surface-2);
}
.shead { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.sname { font-size: 13px; font-weight: 650; letter-spacing: -0.01em; }
.sver { font-size: 11px; color: var(--ink-4); font-family: var(--mono); }
.sdesc2 { margin-top: 5px; font-size: 12px; color: var(--ink-2); line-height: 1.5; }
.smeta { margin-top: 4px; font-size: 11px; color: var(--ink-4); word-break: break-all; }
.sstrip { display: flex; height: 14px; border-radius: 5px; overflow: hidden; margin-top: 9px; border: 1px solid var(--line-2); }
.sstrip i { flex: 1 1 0; }
.ctag {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 7px;
  border-radius: 5px;
  font-size: 11px;
  font-weight: 650;
  color: var(--brand);
  background: var(--brand-soft);
  border: 1px solid var(--brand-line);
}
.colorrow { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.warnhint { color: var(--warn); }
.warnhint code {
  font-family: var(--mono);
  font-size: 11px;
  background: var(--warn-soft);
  padding: 1px 4px;
  border-radius: 4px;
}
.colorpick {
  width: 42px;
  height: 32px;
  padding: 2px;
  border-radius: var(--radius-xs);
  border: 1px solid var(--line-2, var(--line));
  background: var(--surface);
  cursor: pointer;
}
.colorpick::-webkit-color-swatch-wrapper { padding: 0; }
.colorpick::-webkit-color-swatch { border: 0; border-radius: 5px; }
.themepre {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--line);
  background: var(--surface-2);
}
.tp-pill {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 650;
  color: var(--brand);
  background: var(--brand-soft);
  border: 1px solid var(--brand-line);
}
.tp-link {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--brand);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.tp-btn {
  height: 28px;
  padding: 0 12px;
  border-radius: 7px;
  border: 1px solid var(--brand);
  background: var(--brand);
  color: #fff;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}
.tp-ring {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: conic-gradient(var(--brand) 62%, var(--surface-3) 0);
}
.tp-ring i { width: 22px; height: 22px; border-radius: 50%; background: var(--surface); }

/* ---- 三档时长 ---- */
.ttlgrid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; max-width: 460px; }
.ttlcell { display: flex; flex-direction: column; gap: 4px; }
.ttlcell b { font-size: 11.5px; font-weight: 600; color: var(--ink-2); }
.ttlcell span { font-size: 10.5px; color: var(--ink-4); }

/* ---- 到期动作：两张大一点的单选卡，把后果写在脸上 ---- */
.optcards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; max-width: 560px; }
.optcard {
  text-align: left;
  padding: 11px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--line-2, var(--line));
  background: var(--surface);
  cursor: pointer;
  transition: border-color 0.16s var(--ease), background 0.16s var(--ease), box-shadow 0.16s var(--ease);
}
.optcard b { display: block; font-size: 12.5px; font-weight: 650; color: var(--ink); }
.optcard span { display: block; margin-top: 4px; font-size: 11px; line-height: 1.5; color: var(--ink-4); }
.optcard:hover { border-color: var(--line-2); }
.optcard.on {
  border-color: var(--brand);
  background: var(--brand-soft);
  box-shadow: 0 0 0 3px rgba(var(--brand-rgb), 0.12);
}
.optcard.on b { color: var(--brand); }
.optcard.del.on {
  border-color: rgba(245, 158, 11, 0.55);
  background: var(--warn-soft);
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.12);
}
.optcard.del.on b { color: var(--warn); }

/* ---- 标签规则 ---- */
.rules { display: flex; flex-direction: column; gap: 7px; margin: 2px 0 0; padding: 0; list-style: none; }
.rule { display: flex; gap: 8px; align-items: flex-start; font-size: 12px; line-height: 1.55; color: var(--ink-3); }
.rule i { width: 4px; height: 4px; border-radius: 50%; background: var(--line-2); margin-top: 8px; flex: 0 0 auto; }
.rule b { font-weight: 650; color: var(--ink-2); }
.usage { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.meter {
  flex: 0 0 170px;
  height: 7px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.08);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.06);
  overflow: hidden;
}
.meter i {
  display: block;
  height: 100%;
  min-width: 4px;
  border-radius: 99px;
  background: var(--brand);
  transition: width 0.3s var(--ease);
}
.meter.hot i { background: var(--warn); }
.usagetext { font-size: 12px; color: var(--ink-3); }
.usagetext b { color: var(--ink); }

/* ---- 作者名片 ---- */
.author-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(0, 1fr);
  gap: 22px;
}
.author-grid .frow { grid-template-columns: 76px minmax(0, 1fr); }

/* ---- 链接行 ---- */
.linkrows { display: flex; flex-direction: column; gap: 8px; }
/* 两行布局：第一行 拖柄/类型/显示文字/排序/删除，第二行 地址占满——窄栏里地址框也不会被挤没 */
.linkrow {
  display: grid; grid-template-columns: 14px 118px minmax(0, 1fr) auto auto;
  gap: 6px 7px; align-items: center; padding: 8px 8px 8px 4px;
  border: 1px solid var(--line); background: rgba(var(--ink-rgb, 0, 0, 0), 0.02);
}
.linkrow .grip { grid-area: 1 / 1 / 3 / 2; align-self: center; }
.linkrow .typesel { grid-area: 1 / 2; min-width: 0; }
.linkrow .lab { grid-area: 1 / 3; min-width: 0; }
.linkrow .mv { grid-area: 1 / 4; }
.linkrow .del { grid-area: 1 / 5; }
.linkrow .url { grid-area: 2 / 2 / 3 / 6; min-width: 0; }
.linkrow .input { height: 32px; width: 100%; }
.linkrow .del { color: var(--ink-4); }
.linkrow .del:hover { color: var(--danger); }
.linkrow { border-radius: 8px; transition: background .15s, box-shadow .15s, opacity .15s; }
.linkrow.dragging { opacity: .45; }
.linkrow.dropover { box-shadow: 0 -2px 0 0 var(--brand) inset, 0 2px 0 0 var(--brand); }
.linkrow .grip {
  flex: 0 0 auto; width: 16px; text-align: center; cursor: grab; user-select: none;
  color: var(--ink-4); letter-spacing: -2px; font-size: 13px; line-height: 32px;
}
.linkrow .grip:hover { color: var(--ink-2, var(--ink-4)); }
.linkrow .grip:active { cursor: grabbing; }
.linkrow .mv { display: inline-flex; gap: 2px; flex: 0 0 auto; }
.linkrow .mv .btn { padding: 0 6px; color: var(--ink-4); }
.linkrow .mv .btn:disabled { opacity: .3; cursor: default; }
.emptyhint { font-size: 12px; padding: 2px 0 4px; }

/* ---- 自绘类型下拉 ---- */
.typesel { position: relative; flex: 0 0 112px; }
.ts-btn {
  width: 100%; height: 32px; display: flex; align-items: center; gap: 6px;
  padding: 0 8px; border-radius: var(--radius-xs);
  border: 1px solid var(--line-2, var(--line)); background: var(--surface);
  font-size: 12.5px; color: var(--ink); cursor: pointer;
  transition: border-color 0.16s, box-shadow 0.16s;
}
.ts-btn:hover { border-color: var(--line-3, #d6dad7); }
.typesel.open .ts-btn {
  border-color: rgba(var(--brand-rgb), 0.55);
  box-shadow: 0 0 0 3px rgba(var(--brand-rgb), 0.1);
}
.ts-ico { width: 13px; height: 13px; flex: 0 0 auto; color: var(--ink-3); }
.ts-lbl { flex: 1 1 auto; text-align: left; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ts-caret { flex: 0 0 auto; color: var(--ink-4); transition: transform 0.16s; }
.typesel.open .ts-caret { transform: rotate(180deg); }

.ts-pop {
  /* Teleport 到 body，坐标由 JS 按触发按钮的 rect 算，left/width 内联覆盖 */
  position: fixed; z-index: 90;
  min-width: 152px; padding: 4px; border-radius: 10px;
  background: var(--surface); border: 1px solid var(--line);
  box-shadow: var(--shadow-pop); animation: pop 0.14s var(--ease);
  max-height: 324px; overflow-y: auto; overscroll-behavior: contain;
}
.ts-pop button {
  width: 100%; display: flex; align-items: center; gap: 8px;
  height: 30px; padding: 0 8px; border: 0; border-radius: 7px;
  background: transparent; color: var(--ink-2); font-size: 12.5px; cursor: pointer; text-align: left;
}
.ts-pop button:hover { background: var(--surface-2); color: var(--ink); }
.ts-pop button.on { background: var(--brand-soft); color: var(--brand); font-weight: 600; }
.ts-pop svg { width: 13px; height: 13px; flex: 0 0 auto; }

/* ---- 预览卡片 ---- */
.pvwrap { min-width: 0; }
.pvlabel { font-size: 11px; font-weight: 600; color: var(--ink-4); letter-spacing: 0.06em; margin-bottom: 7px; }
.pvcard {
  display: flex; align-items: center; gap: 11px; flex-wrap: wrap;
  padding: 12px 13px; border-radius: 12px; background: var(--surface-2);
  border: 1px dashed var(--line-2, var(--line));
}
.pvava {
  width: 34px; height: 34px; border-radius: 50%; flex: 0 0 auto;
  display: grid; place-items: center; font-weight: 650; font-size: 14px;
  background: var(--brand-soft); color: var(--brand); border: 1px solid var(--brand-line);
}
.pvmeta { min-width: 0; flex: 1 1 120px; }
.pvmeta b { display: block; font-size: 13.5px; letter-spacing: -0.01em; }
.pvmeta span {
  display: block; margin-top: 2px; font-size: 11.5px; color: var(--ink-4);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.pvlinks { display: flex; gap: 6px; flex-wrap: wrap; width: 100%; }
.pvlink {
  display: inline-flex; align-items: center; gap: 5px; height: 26px; padding: 0 9px;
  border-radius: 8px; border: 1px solid var(--line); background: var(--surface);
  font-size: 11.5px; font-weight: 600; color: var(--ink-3);
}
.pvlink svg { width: 12px; height: 12px; }

/* ---- 运行信息 ---- */
.kv.runtime { grid-template-columns: 96px minmax(0, 1fr); gap: 9px 12px; }
.kv.runtime dd.mono { word-break: break-all; }

/* ---- 最近操作 ---- */
.events { display: flex; flex-direction: column; }
.evrow {
  display: flex; align-items: center; gap: 10px; padding: 7px 0;
  border-bottom: 1px solid var(--line); font-size: 12px;
}
.evrow:last-child { border-bottom: 0; }
.evrow .muted { flex: 1 1 auto; min-width: 0; }
.evrow .dim { flex: 0 0 auto; font-size: 11.5px; }

/* ---------------- 响应式：导航转成横条 ---------------- */
@media (max-width: 1080px) {
  .setwrap { grid-template-columns: minmax(0, 1fr); gap: 12px; }
  .setnav {
    position: sticky; top: 56px; z-index: 6;
    flex-direction: row; gap: 6px; padding: 8px 0;
    overflow-x: auto; scrollbar-width: none;
    background: var(--bg);
    border-bottom: 1px solid var(--line);
    -webkit-mask-image: linear-gradient(90deg, #000 88%, transparent);
    mask-image: linear-gradient(90deg, #000 88%, transparent);
  }
  .setnav::-webkit-scrollbar { display: none; }
  .setnav a { flex: 0 0 auto; height: 28px; }
  .setmain .panel { scroll-margin-top: 108px; }
  .author-grid { grid-template-columns: minmax(0, 1fr); gap: 16px; }
  .seriesgrid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 720px) {
  .setmain .form .frow { grid-template-columns: minmax(0, 1fr); gap: 6px; }
  .setmain .form .frow > label { padding-top: 0; }
  .setmain .form .frow > .hint { grid-column: auto; }
  .author-grid .frow { grid-template-columns: minmax(0, 1fr); }
  .optcards { grid-template-columns: minmax(0, 1fr); }
  .ttlgrid { grid-template-columns: minmax(0, 1fr); max-width: none; }
  .linkrow { grid-template-columns: 104px minmax(0, 1fr) auto; padding: 8px; }
  .linkrow .typesel { grid-area: 1 / 1; }
  .linkrow .lab { grid-area: 1 / 2; }
  .linkrow .del { grid-area: 1 / 3; }
  .linkrow .url { grid-area: 2 / 1 / 3 / 3; }
  .linkrow .grip { display: none; }
  .linkrow .mv { grid-area: 2 / 3; }
  .linkrow .mv .btn { width: 36px; height: 36px; }
  .meter { flex: 1 1 140px; }
  .seriesgrid { grid-template-columns: minmax(0, 1fr); }
}
</style>
