<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { store, toast } from '../store'
import { fmtBytes, fmtDate, relTime } from '../format'
import Icon from '../components/Icon.vue'

const data = ref(null)
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
}
const actionLabel = (a) => ACTION_LABEL[a] || a
const busy = ref(false)
const form = reactive({
  site_title: '',
  ttl: { portal: 6, link: 12, private: 0 },
  default_expire_action: 'block',
  public_portal: false,
  author: { name: '', bio: '', links: [] },
})
const authorTypes = ref([
  { key: 'github', label: 'GitHub' },
  { key: 'x', label: 'X' },
  { key: 'mail', label: '邮箱' },
  { key: 'blog', label: '博客' },
  { key: 'douyin', label: '抖音' },
  { key: 'wechat', label: '微信' },
  { key: 'bilibili', label: '哔哩哔哩' },
  { key: 'zhihu', label: '知乎' },
  { key: 'rss', label: 'RSS' },
  { key: 'link', label: '链接' },
])
const pw = reactive({ old_password: '', new_password: '' })

const VIS = [
  { key: 'portal', label: '门户可见', hint: '会出现在 /portal 列表里' },
  { key: 'link', label: '持链接可见', hint: '不公开列出，拿到链接即可打开' },
  { key: 'private', label: '仅自己可见', hint: '需登录且是本人或管理员' },
]

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
        // 邮箱在界面上只显示地址，保存时后端再补 mailto:
        url: l.type === 'mail' ? String(l.url || '').replace(/^mailto:/i, '') : l.url,
      })),
    }
  } catch (e) {
    toast(e.message || '读取失败', 'err')
  }
}

const typeLabel = (key) => authorTypes.value.find((t) => t.key === key)?.label || '链接'

function addLink() {
  if (form.author.links.length >= 12) return toast('最多 12 个链接', 'err')
  form.author.links.push({ type: 'github', label: '', url: '' })
}

function removeLink(i) {
  form.author.links.splice(i, 1)
}

function onTypeChange(link) {
  // 标签为空、或者还是某个类型的默认名时，跟着类型走
  const labels = authorTypes.value.map((t) => t.label)
  if (!link.label || labels.includes(link.label)) link.label = typeLabel(link.type)
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
    <button class="btn primary" :disabled="busy" @click="save">保存更改</button>
  </header>

  <div class="content" style="display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); gap: 16px; align-items: start">
    <div class="panel" style="grid-column: 1 / -1">
      <div class="panel-head">
        <h2>作者信息</h2>
        <span class="dim" style="font-size: 11.5px">填了就展示在访客门户 <span class="mono">/portal</span> 顶部</span>
      </div>
      <div class="panel-body">
        <div class="form">
          <div class="frow two">
            <div class="frow">
              <label>显示名</label>
              <input v-model="form.author.name" class="input" placeholder="例如：孟庆炜" maxlength="40" />
            </div>
            <div class="frow">
              <label>一句话介绍</label>
              <input v-model="form.author.bio" class="input" placeholder="例如：做点顺手的小工具" maxlength="120" />
            </div>
          </div>

          <div class="frow">
            <label>链接</label>
            <div class="linkrows">
              <div v-for="(l, i) in form.author.links" :key="i" class="linkrow">
                <select v-model="l.type" class="input type" @change="onTypeChange(l)">
                  <option v-for="t in authorTypes" :key="t.key" :value="t.key">{{ t.label }}</option>
                </select>
                <input v-model="l.label" class="input label" placeholder="显示文字" maxlength="20" />
                <input
                  v-model="l.url"
                  class="input url"
                  :placeholder="l.type === 'mail' ? 'hi@example.com' : 'https://…（可省略 https://）'"
                />
                <button class="btn sm ghost" title="删除" @click="removeLink(i)">
                  <Icon name="close" :size="12" />
                </button>
              </div>
              <div v-if="!form.author.links.length" class="dim" style="font-size: 12px">
                还没有链接。加几个，访客门户顶部就会出现对应图标。
              </div>
              <div>
                <button class="btn sm" @click="addLink"><Icon name="plus" :size="12" /> 添加链接</button>
              </div>
            </div>
            <span class="hint">
              类型决定图标；标签留空就按类型默认（GitHub / 邮箱 / 抖音 …）。邮箱直接填地址即可，会自动补 mailto:。
            </span>
          </div>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head"><h2>基础</h2></div>
      <div class="panel-body">
        <div class="form">
          <div class="frow">
            <label>站点标题</label>
            <input v-model="form.site_title" class="input" placeholder="临时预览站" />
            <span class="hint">显示在控制台侧栏与访客预览页的浏览器标题</span>
          </div>
          <div class="frow">
            <label>默认存活时长（小时）</label>
            <div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px">
              <div v-for="v in VIS" :key="v.key" class="frow" style="gap: 4px">
                <input
                  v-model.number="form.ttl[v.key]"
                  class="input"
                  type="number"
                  min="0"
                  step="1"
                  :aria-label="v.label + ' 默认时长'"
                />
                <span class="hint" style="margin: 0">{{ v.label }}<span v-if="!Number(form.ttl[v.key])"> · 永久</span></span>
              </div>
            </div>
            <span class="hint">填 0 表示永久；上传时未指定时长就按可见性取用这里的值</span>
          </div>
          <div class="frow">
            <label>到期后默认动作</label>
            <div class="seg" style="width: fit-content">
              <button :class="{ on: form.default_expire_action === 'block' }" @click="form.default_expire_action = 'block'">
                停止访问
              </button>
              <button :class="{ on: form.default_expire_action === 'delete' }" @click="form.default_expire_action = 'delete'">
                删除文件
              </button>
            </div>
            <span class="hint">
              新建项目时预选这个策略；单个项目仍可在上传对话框里改。停止访问会保留文件占磁盘，删除文件会连目录一起清掉。
            </span>
          </div>
          <label class="check">
            <input v-model="form.public_portal" type="checkbox" />
            允许未登录访客浏览门户列表（<span class="mono">/portal</span>）
          </label>
          <span class="hint" style="margin-top: -6px">
            关闭时门户需要登录才能看到列表，直链预览不受影响
          </span>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head"><h2>运行信息</h2></div>
      <div class="panel-body">
        <dl v-if="data" class="kv" style="grid-template-columns: 92px 1fr; gap: 9px 10px">
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
        <div v-else class="skel" style="height: 90px" />
      </div>
    </div>

    <div class="panel">
      <div class="panel-head"><h2>修改我的密码</h2></div>
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
    </div>

    <div class="panel">
      <div class="panel-head"><h2>最近操作</h2></div>
      <div class="panel-body" style="max-height: 260px; overflow-y: auto">
        <div v-if="data?.events?.length" class="filelist" style="margin: 0; max-height: none">
          <div v-for="(e, i) in data.events" :key="i">
            <span><span class="badge">{{ actionLabel(e.action) }}</span> <span class="muted">{{ e.detail || '—' }}</span></span>
            <span class="dim" style="white-space: nowrap">{{ relTime(e.at) }}</span>
          </div>
        </div>
        <p v-else class="dim" style="font-size: 12px">暂无记录</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
@media (max-width: 1080px) {
  .content { grid-template-columns: 1fr !important; }
}
.linkrows { display: flex; flex-direction: column; gap: 7px; }
.linkrow { display: flex; align-items: center; gap: 6px; }
.linkrow .input { height: 30px; }
.linkrow .type { flex: 0 0 120px; padding-right: 4px; }
.linkrow .label { flex: 0 0 120px; }
.linkrow .url { flex: 1 1 auto; min-width: 0; }
@media (max-width: 720px) {
  .linkrow {
    display: grid; grid-template-columns: 112px minmax(0, 1fr) auto;
    gap: 6px; padding-bottom: 9px; border-bottom: 1px dashed var(--line);
  }
  .linkrow .type { grid-area: 1 / 1; flex: none; }
  .linkrow .label { grid-area: 1 / 2; flex: none; }
  .linkrow .url { grid-area: 2 / 1 / 3 / 3; flex: none; }
  .linkrow .btn { grid-area: 1 / 3; align-self: center; }
}
</style>
