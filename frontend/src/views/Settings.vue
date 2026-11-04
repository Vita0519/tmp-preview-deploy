<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { api } from '../api'
import { confirmAction, store, toast } from '../store'
import { fmtBytes, relTime } from '../format'
import { applyPalette, applySiteIcon, neutralOf, normalize, palette, previewSeries, readable } from '../theme'
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
  collection: '收藏夹',
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

// 主题：整套配色系列（主色 + 中性色画布），选完即时预览，保存后才算数
const accent = ref('#0f766e')
const accentInput = ref('#0f766e')
const seriesList = ref([])   // 后端下发的 6 套系列（含每套的完整中性色）
const seriesKey = ref('classic')
const custom = ref(false)    // 主色被手改过，不属于任何一套系列
let savedBoard = null        // 进来时后端下发的整份色板，没保存就原样退回去

const currentSeries = computed(() => seriesList.value.find((s) => s.key === seriesKey.value) || null)
// 卡片上的配色条：画布 → 次级容器 → 主色，正好是 60-30-10 的读法
const stripOf = (s) => [s.neutral.bg, s.neutral['surface-2'], s.accent]

function pickSeries(s) {
  seriesKey.value = s.key
  custom.value = false
  accent.value = normalize(s.accent)
  accentInput.value = accent.value
  previewSeries(s)
}

function pickAccent(v) {
  const hex = normalize(v)
  accent.value = hex
  accentInput.value = hex
  // 改成和当前系列不一样的主色 → 记成「自定义」，中性色底保持不变
  const hit = seriesList.value.find((s) => normalize(s.accent) === hex)
  if (hit) {
    seriesKey.value = hit.key
    custom.value = false
    previewSeries(hit)
  } else {
    custom.value = true
    applyPalette({ ...palette(hex, currentSeries.value), neutral: neutralOf(currentSeries.value) })
  }
}

function resetTheme() {
  const s = seriesList.value.find((x) => x.key === 'classic') || seriesList.value[0]
  if (s) pickSeries(s)
}

// 主色被「可读性兜底」压深时，设置页要说清楚实际生效的是哪个色
const dimmed = computed(() => {
  const b = readable(accent.value)
  return b === normalize(accent.value) ? '' : b
})

const form = reactive({
  site_title: '',
  ttl: { portal: 6, link: 12, private: 0 },
  default_expire_action: 'block',
  public_portal: false,
  author: { name: '', bio: '', links: [] },
  tag_max: 6,
  tag_bar: 12,
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
  { key: 'portal', label: '门户可见', hint: '出现在 /portal 列表' },
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
    if (d.site_icon) siteIcon.value = d.site_icon
    form.tag_max = d.tags?.max_per_project ?? 6
    form.tag_bar = d.tags?.bar_limit ?? 12
    const th = d.theme || {}
    seriesList.value = Array.isArray(th.series_list) ? th.series_list : []
    seriesKey.value = th.series || 'classic'
    custom.value = !!th.custom
    // 记用户填的原值；palette 内部会为可读性压深，实际生效值在 th.accent
    const hex = normalize(th.raw || th.accent || '#0f766e')
    accent.value = hex
    accentInput.value = hex
    savedBoard = th.accent ? th : null
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
      // 系列决定中性色画布，主色可以在此基础上手改（custom）
      theme_series: seriesKey.value,
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


// ---------------- 备份与恢复 ----------------
const backupFile = ref(null)
const backupBusy = ref(false)
const backupInfo = ref(null)

function pickBackupFile(e) {
  backupFile.value = e.target.files?.[0] || null
  backupInfo.value = null
  e.target.value = ''
}

async function inspectBackup() {
  if (!backupFile.value) return toast('先选一个备份包（.zip）', 'err')
  backupBusy.value = true
  try {
    const fd = new FormData()
    fd.append('file', backupFile.value, backupFile.value.name)
    backupInfo.value = await api.postForm('/api/backup/inspect', fd)
    toast('读到了，确认下面内容后再恢复')
  } catch (e) {
    backupInfo.value = null
    toast(e.message || '读不了这个备份包', 'err')
  } finally {
    backupBusy.value = false
  }
}

async function doRestore() {
  if (!backupFile.value || !backupInfo.value) return
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
    const fd = new FormData()
    fd.append('file', backupFile.value, backupFile.value.name)
    const d = await api.postForm('/api/backup/restore', fd)
    toast(`已恢复：${d.counts?.projects ?? '?'} 个项目，${d.counts?.users ?? '?'} 个账号`)
    backupInfo.value = null
    backupFile.value = null
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
    ac: accent.value,
    se: seriesKey.value,
    au: form.author,
    tm: form.tag_max,
    tb: form.tag_bar,
  })
)
const dirty = computed(() => !!snap.value && state.value !== snap.value)

onMounted(load)
// 没保存就离开：把整套色板退回去，别留下一个「只在这次会话有效」的主题
onUnmounted(() => {
  if (savedBoard) applyPalette(savedBoard)
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
          <Icon :name="s.icon" :size="13" />
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
                <a class="linkbtn" href="/portal" target="_blank" rel="noopener">
                  打开门户 <Icon name="external" :size="11" />
                </a>
              </div>
              <span class="hint">关闭后 /portal 需要登录；已发出去的直链预览不受影响</span>
            </div>
          </div>
        </section>

        <!-- 外观 -->
        <section id="look" class="panel">
          <div class="panel-head">
            <h2>外观</h2>
            <span class="pdesc">控制台、门户、访客预览页共用同一套主色</span>
          </div>
          <div class="panel-body form">
            <div class="frow">
              <label>配色系列</label>
              <div v-if="seriesList.length" class="seriesgrid">
                <button
                  v-for="s in seriesList"
                  :key="s.key"
                  type="button"
                  class="scard"
                  :class="{ on: !custom && seriesKey === s.key }"
                  :style="{
                    background: s.neutral.bg,
                    color: s.neutral.ink,
                    borderColor: s.neutral.line,
                    '--chip': s.accent,
                  }"
                  @click="pickSeries(s)"
                >
                  <span class="stop">
                    <i :style="{ background: s.accent }">Aa</i>
                    <b>{{ s.name }}</b>
                    <svg v-if="!custom && seriesKey === s.key" class="sok" viewBox="0 0 16 16" aria-hidden="true">
                      <path d="M3.6 8.4 6.3 11 12.4 4.8" />
                    </svg>
                  </span>
                  <span class="sdesc" :style="{ color: s.neutral['ink-3'] }">{{ s.desc }}</span>
                  <span class="suse" :style="{ color: s.neutral['ink-4'] }">{{ s.use }}</span>
                </button>
              </div>
              <span v-else class="hint">配色系列没读到，刷新一下页面</span>
              <span class="hint">
                每套 = 画布底 + 两级文字色 + 主色，按 60-30-10 分配：底与留白占 60%、卡片占 30%、主色只占 10%。
                点一下即时预览，点「保存更改」才写进配置
              </span>
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
                <button type="button" class="btn ghost sm" @click="resetTheme()">回到经典墨绿</button>
              </div>
              <span class="hint">画布底留在所选系列上，只改强调色；改回系列自带的主色会自动归位</span>
              <span v-if="dimmed" class="hint warnhint">
                这个主色在白底上偏淡（对比度 < 3:1），实际会按 <code>{{ dimmed }}</code> 渲染，
                免得按钮和浅底文字糊成一片
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
              <span class="hint">hover、浅底、描边、渐变深色仍由主色自动派生，不用手调</span>
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
                  <Icon name="trash" :size="12" />
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
            <span class="pdesc">展示在访客门户 <span class="mono">/portal</span> 顶部</span>
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
                  <div v-for="(l, i) in form.author.links" :key="i" class="linkrow">
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
                    <button class="btn sm ghost del" title="删除这条" @click="removeLink(i)">
                      <Icon name="close" :size="12" />
                    </button>
                  </div>

                  <div v-if="!form.author.links.length" class="dim emptyhint">
                    还没有链接。加几个，访客门户顶部就会出现对应的图标。
                  </div>
                  <div>
                    <button class="btn sm" @click="addLink"><Icon name="plus" :size="12" /> 添加链接</button>
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
            <span class="pdesc">数据库 + 项目文件 + 下载包 + 站点图标，一个 zip 全带走</span>
          </div>
          <div class="panel-body form">
            <div class="frow">
              <label>下载备份</label>
              <div class="colorrow">
                <a class="btn" href="/api/backup" download>
                  <Icon name="download" :size="13" /> 打包下载
                </a>
                <span class="hint" style="margin: 0">
                  数据库用在线快照，正在写入也不会拷到半截
                </span>
              </div>
            </div>

            <div class="frow">
              <label>从备份恢复</label>
              <div class="colorrow" style="flex-wrap: wrap">
                <button class="btn" :disabled="backupBusy" @click="$refs.bk.click()">
                  {{ backupFile ? backupFile.name : '选择备份 zip' }}
                </button>
                <input ref="bk" type="file" accept=".zip,application/zip" style="display: none" @change="pickBackupFile" />
                <button class="btn" :disabled="backupBusy || !backupFile" @click="inspectBackup">
                  {{ backupBusy ? '处理中…' : '先看看里面有什么' }}
                </button>
                <button
                  class="btn danger"
                  :disabled="backupBusy || !backupInfo"
                  @click="doRestore"
                >
                  覆盖恢复
                </button>
              </div>
              <span class="hint">
                恢复会替换现网数据；旧数据保留在 data/.backup-before-restore-&lt;时间&gt;/，只留最近 3 份
              </span>
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
                  收藏夹 <b class="num">{{ backupInfo.manifest.counts.collections }}</b>
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
</template>

<style scoped>
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
  border: 1px solid rgba(180, 83, 9, 0.2);
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
.scard:hover { transform: translateY(-1px); box-shadow: 0 10px 22px -16px var(--ink); }
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
.scard .suse { margin-top: auto; font-size: 10.5px; font-weight: 600; letter-spacing: 0.01em; }
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
.optcard:hover { border-color: var(--line-3, #d6dad7); }
.optcard.on {
  border-color: var(--brand);
  background: var(--brand-soft);
  box-shadow: 0 0 0 3px rgba(var(--brand-rgb), 0.09);
}
.optcard.on b { color: var(--brand); }
.optcard.del.on {
  border-color: #e9a23b;
  background: #fff8ee;
  box-shadow: 0 0 0 3px rgba(180, 83, 9, 0.1);
}
.optcard.del.on b { color: #b45309; }

/* ---- 标签规则 ---- */
.rules { display: flex; flex-direction: column; gap: 7px; margin: 2px 0 0; padding: 0; list-style: none; }
.rule { display: flex; gap: 8px; align-items: flex-start; font-size: 12px; line-height: 1.55; color: var(--ink-3); }
.rule i { width: 4px; height: 4px; border-radius: 50%; background: var(--line-3, #cdd2d6); margin-top: 8px; flex: 0 0 auto; }
.rule b { font-weight: 650; color: var(--ink-2); }
.usage { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.meter {
  flex: 0 0 170px;
  height: 7px;
  border-radius: 99px;
  background: #e6e9e7;
  box-shadow: inset 0 0 0 1px rgba(20, 22, 26, 0.05);
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
.linkrow { display: flex; align-items: center; gap: 7px; }
.linkrow .input { height: 32px; }
.linkrow .lab { flex: 0 0 110px; }
.linkrow .url { flex: 1 1 auto; min-width: 0; }
.linkrow .del { flex: 0 0 auto; color: var(--ink-4); }
.linkrow .del:hover { color: var(--danger); }
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
  .linkrow {
    display: grid; grid-template-columns: 104px minmax(0, 1fr) auto;
    gap: 6px; padding-bottom: 10px; border-bottom: 1px dashed var(--line);
  }
  .typesel { grid-area: 1 / 1; flex: none; }
  .linkrow .lab { grid-area: 1 / 2; flex: none; }
  .linkrow .url { grid-area: 2 / 1 / 3 / 3; }
  .linkrow .del { grid-area: 1 / 3; align-self: center; }
  .meter { flex: 1 1 140px; }
  .seriesgrid { grid-template-columns: minmax(0, 1fr); }
}
</style>
