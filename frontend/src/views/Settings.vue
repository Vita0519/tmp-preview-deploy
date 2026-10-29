<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { api } from '../api'
import { store, toast } from '../store'
import { fmtBytes, relTime } from '../format'
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
  agent_create: '创建成员',
  agent_patch: '修改成员',
  agent_delete: '删除成员',
  expire_block: '到期停访',
  expire_delete: '到期删除',
  settings: '修改设置',
}
const actionLabel = (a) => ACTION_LABEL[a] || a

const form = reactive({
  site_title: '',
  ttl: { portal: 6, link: 12, private: 0 },
  default_expire_action: 'block',
  public_portal: false,
  author: { name: '', bio: '', links: [] },
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

onMounted(load)
</script>

<template>
  <header class="topbar">
    <h1>设置</h1>
    <span class="sub">站点级配置</span>
    <div class="grow" />
    <button class="btn primary" :disabled="busy" @click="save">
      {{ busy ? '保存中…' : '保存更改' }}
    </button>
  </header>

  <div class="content setgrid">
    <!-- 作者名片 -->
    <section class="panel span2">
      <div class="panel-head">
        <h2>作者名片</h2>
        <span class="dim" style="font-size: 11.5px">展示在访客门户 <span class="mono">/portal</span> 顶部</span>
      </div>
      <div class="panel-body author-grid">
        <div class="form">
          <div class="frow two">
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
              类型决定图标；标签留空就用类型默认名。邮箱只填地址即可，其他地址可省略 https://。
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

    <!-- 站点 -->
    <section class="panel">
      <div class="panel-head"><h2>站点</h2></div>
      <div class="panel-body">
        <div class="form">
          <div class="frow">
            <label>站点标题</label>
            <input v-model="form.site_title" class="input" placeholder="临时预览站" />
            <span class="hint">控制台侧栏与访客页的浏览器标题</span>
          </div>
          <label class="check" style="margin-top: 4px">
            <input v-model="form.public_portal" type="checkbox" />
            允许未登录访客浏览门户列表
          </label>
          <span class="hint" style="margin-top: -4px">关闭时 /portal 需要登录，直链预览不受影响</span>
        </div>
      </div>
    </section>

    <!-- 项目默认值 -->
    <section class="panel">
      <div class="panel-head"><h2>项目默认值</h2></div>
      <div class="panel-body">
        <div class="form">
          <div class="frow">
            <label>按可见性的默认存活时长（小时，0 = 永久）</label>
            <div class="ttlgrid">
              <div v-for="v in VIS" :key="v.key" class="ttlcell">
                <input v-model.number="form.ttl[v.key]" class="input" type="number" min="0" step="1" />
                <b>{{ v.label }}</b>
                <span>{{ v.hint }}</span>
              </div>
            </div>
          </div>
          <div class="frow">
            <label>到期后默认动作</label>
            <div class="seg" style="width: fit-content">
              <button
                :class="{ on: form.default_expire_action === 'block' }"
                @click="form.default_expire_action = 'block'"
              >
                停止访问
              </button>
              <button
                :class="{ on: form.default_expire_action === 'delete' }"
                @click="form.default_expire_action = 'delete'"
              >
                删除文件
              </button>
            </div>
            <span class="hint">停止访问保留文件占磁盘；删除文件会连目录一起清掉</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 账号 -->
    <section class="panel">
      <div class="panel-head"><h2>我的账号</h2></div>
      <div class="panel-body">
        <div class="form">
          <div class="frow two">
            <div class="frow">
              <label>当前密码</label>
              <input v-model="pw.old_password" class="input" type="password" autocomplete="current-password" />
            </div>
            <div class="frow">
              <label>新密码</label>
              <input v-model="pw.new_password" class="input" type="password" autocomplete="new-password" />
            </div>
          </div>
          <div><button class="btn" @click="changePassword">更新密码</button></div>
        </div>
      </div>
    </section>

    <!-- 运行信息 -->
    <section class="panel">
      <div class="panel-head"><h2>运行信息</h2></div>
      <div class="panel-body">
        <dl v-if="data" class="kv" style="grid-template-columns: 82px 1fr; gap: 9px 10px">
          <dt>数据目录</dt>
          <dd class="mono" style="word-break: break-all">{{ data.runtime.data_dir }}</dd>
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
    <section class="panel span2">
      <div class="panel-head">
        <h2>最近操作</h2>
        <span class="dim" style="font-size: 11.5px">最近 20 条</span>
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
.setgrid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  align-items: start;
}
.span2 { grid-column: span 2; }
@media (max-width: 1080px) {
  .setgrid { grid-template-columns: 1fr; }
  .span2 { grid-column: auto; }
}

.author-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
  gap: 20px;
}
@media (max-width: 1180px) {
  .author-grid { grid-template-columns: 1fr; }
}

/* ---- 链接行 ---- */
.linkrows { display: flex; flex-direction: column; gap: 8px; }
.linkrow { display: flex; align-items: center; gap: 7px; }
.linkrow .input { height: 32px; }
.linkrow .lab { flex: 0 0 116px; }
.linkrow .url { flex: 1 1 auto; min-width: 0; }
.linkrow .del { flex: 0 0 auto; color: var(--ink-4); }
.linkrow .del:hover { color: var(--danger); }
.emptyhint { font-size: 12px; padding: 2px 0 4px; }

/* ---- 自绘类型下拉 ---- */
.typesel { position: relative; flex: 0 0 118px; }
.ts-btn {
  width: 100%; height: 32px; display: flex; align-items: center; gap: 6px;
  padding: 0 8px; border-radius: var(--radius-xs);
  border: 1px solid var(--line-2, var(--line)); background: var(--surface);
  font-size: 12.5px; color: var(--ink); cursor: pointer;
  transition: border-color 0.16s, box-shadow 0.16s;
}
.ts-btn:hover { border-color: var(--line-3, #d6dad7); }
.typesel.open .ts-btn {
  border-color: rgba(15, 118, 110, 0.55);
  box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.1);
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

/* ---- 三档时长 ---- */
.ttlgrid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.ttlcell { display: flex; flex-direction: column; gap: 4px; }
.ttlcell b { font-size: 11.5px; font-weight: 600; color: var(--ink-2); }
.ttlcell span { font-size: 10.5px; color: var(--ink-4); }

/* ---- 最近操作 ---- */
.events { display: flex; flex-direction: column; }
.evrow {
  display: flex; align-items: center; gap: 10px; padding: 7px 0;
  border-bottom: 1px solid var(--line); font-size: 12px;
}
.evrow:last-child { border-bottom: 0; }
.evrow .muted { flex: 1 1 auto; min-width: 0; }
.evrow .dim { flex: 0 0 auto; font-size: 11.5px; }

@media (max-width: 720px) {
  .author-grid { gap: 16px; }
  .linkrow {
    display: grid; grid-template-columns: 112px minmax(0, 1fr) auto;
    gap: 6px; padding-bottom: 10px; border-bottom: 1px dashed var(--line);
  }
  .typesel { grid-area: 1 / 1; flex: none; }
  .linkrow .lab { grid-area: 1 / 2; flex: none; }
  .linkrow .url { grid-area: 2 / 1 / 3 / 3; }
  .linkrow .del { grid-area: 1 / 3; align-self: center; }
  .ttlgrid { grid-template-columns: 1fr; }
}
</style>
