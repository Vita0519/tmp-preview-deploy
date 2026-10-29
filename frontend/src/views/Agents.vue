<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { confirmAction, store, toast } from '../store'
import { fmtDate, fmtNum, relTime } from '../format'
import Icon from '../components/Icon.vue'

const items = ref([])
const loading = ref(true)
const createOpen = ref(false)
const created = ref(null)
const form = reactive({ username: '', display_name: '', password: '', role: 'publisher' })
const busy = ref(false)

const ROLES = [
  { key: 'viewer', label: '仅门户', short: '访客', desc: '只能浏览访客门户，不能看项目' },
  { key: 'publisher', label: '可发布', short: '发布者', desc: '能上传并管理自己的项目' },
  { key: 'admin', label: '管理员', short: '管理员', desc: '可管理全部成员、项目与设置' },
]
const roleOf = (k) => ROLES.find((r) => r.key === k) || ROLES[0]

async function setRole(item, role) {
  if (role === item.role) return
  try {
    await api.patch(`/api/agents/${item.id}`, { role })
    toast(`已改为「${roleOf(role).label}」`)
    load()
  } catch (e) {
    toast(e.message || '修改失败', 'err')
    load()
  }
}

async function load() {
  loading.value = true
  try {
    const d = await api.get('/api/agents')
    items.value = d.items
  } catch (e) {
    toast(e.message || '读取失败', 'err')
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!form.username.trim()) return toast('请填写账号', 'err')
  busy.value = true
  try {
    const d = await api.post('/api/agents', { ...form })
    created.value = d
    createOpen.value = false
    form.username = ''
    form.display_name = ''
    form.password = ''
    load()
    toast('成员已创建')
  } catch (e) {
    toast(e.message || '创建失败', 'err')
  } finally {
    busy.value = false
  }
}

async function act(item, body, msg) {
  try {
    const d = await api.patch(`/api/agents/${item.id}`, body)
    if (d.password || d.api_key) {
      created.value = { username: item.username, password: d.password, api_key: d.api_key }
    }
    toast(msg)
    load()
  } catch (e) {
    toast(e.message || '操作失败', 'err')
  }
}

async function resetPassword(item) {
  const ok = await confirmAction({
    title: '重置密码',
    message: `将为「${item.display_name}」生成新的随机密码，旧密码立即失效。`,
    confirmText: '重置',
    danger: true,
  })
  if (ok) act(item, { password: crypto.randomUUID().replace(/-/g, '').slice(0, 12) }, '密码已重置')
}

async function rotateKey(item) {
  const ok = await confirmAction({
    title: '轮换 API Key',
    message: `「${item.display_name}」旧的 Key 会立即失效，正在跑的脚本需要更新。`,
    confirmText: '轮换',
    danger: true,
  })
  if (ok) act(item, { rotate_key: true }, 'API Key 已轮换')
}

async function toggleActive(item) {
  act(item, { active: !item.active }, item.active ? '已停用' : '已启用')
}

async function remove(item) {
  const ok = await confirmAction({
    title: '删除成员',
    message: `将删除「${item.display_name}」及其名下 ${item.projects} 个项目（含全部文件），不可恢复。`,
    confirmText: '删除',
    danger: true,
  })
  if (!ok) return
  try {
    await api.del(`/api/agents/${item.id}`)
    toast('成员已删除')
    load()
  } catch (e) {
    toast(e.message || '删除失败', 'err')
  }
}

function copy(text) {
  navigator.clipboard?.writeText(text).then(
    () => toast('已复制'),
    () => toast('复制失败', 'err')
  )
}

onMounted(load)
</script>

<template>
  <header class="topbar">
    <h1>成员</h1>
    <span class="sub">{{ items.length }} 个账号</span>
    <div class="grow" />
    <span class="dim hide-sm" style="font-size: 12px">每个成员用自己的 API Key 上传，互不可见</span>
    <button class="btn primary" @click="createOpen = true"><Icon name="plus" :size="13" /> 添加成员</button>
  </header>

  <div class="content">
    <div class="panel only-wide">
      <table>
        <thead>
          <tr>
            <th>成员</th>
            <th>角色</th>
            <th class="cell-num">项目 / 在线</th>
            <th class="cell-num">访问</th>
            <th class="hide-sm">Key</th>
            <th>最近登录</th>
            <th class="cell-num">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in items" :key="a.id" style="cursor: default">
            <td>
              <div class="pcell">
                <div class="avatar" style="width: 28px; height: 28px">{{ (a.display_name || a.username).slice(0, 1) }}</div>
                <div class="pmeta">
                  <div class="pname">
                    {{ a.display_name }}
                    <span v-if="!a.active" class="badge">已停用</span>
                  </div>
                  <div class="pslug">@{{ a.username }}</div>
                </div>
              </div>
            </td>
            <td>
              <select
                class="rolesel"
                :class="'r-' + a.role"
                :value="a.role"
                :disabled="a.id === store.user?.id"
                :title="a.id === store.user?.id ? '不能修改自己的角色' : roleOf(a.role).desc"
                @change="setRole(a, $event.target.value)"
              >
                <option v-for="r in ROLES" :key="r.key" :value="r.key">{{ r.label }}</option>
              </select>
            </td>
            <td class="cell-num tabular">{{ a.projects }} <span class="dim">/ {{ a.online }}</span></td>
            <td class="cell-num tabular">{{ fmtNum(a.views) }}</td>
            <td class="hide-sm">
              <span class="mono dim">…{{ a.api_key_tail }}</span>
            </td>
            <td>
              <span class="tabular" style="font-size: 12px">{{ a.last_login_at ? relTime(a.last_login_at) : '从未' }}</span>
            </td>
            <td class="cell-num">
              <div style="display: flex; gap: 4px; justify-content: flex-end">
                <button class="btn sm" title="重置密码" @click="resetPassword(a)">重置密码</button>
                <button class="btn sm" title="轮换 Key" @click="rotateKey(a)"><Icon name="key" :size="12" /></button>
                <button v-if="a.id !== store.user?.id" class="btn sm" @click="toggleActive(a)">
                  {{ a.active ? '停用' : '启用' }}
                </button>
                <button v-if="a.id !== store.user?.id" class="btn sm ghost" style="color: var(--danger)" title="删除成员" @click="remove(a)">
                  <Icon name="trash" :size="12" />
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="loading && !items.length">
            <td colspan="7"><div class="skel" style="height: 14px; width: 40%; margin: 14px 0" /></td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 窄屏：表格换成卡片，避免列被压成竖排文字 -->
    <div class="only-narrow">
      <div v-if="items.length" class="acards">
        <div v-for="a in items" :key="a.id" class="acard">
          <div class="acard-top">
            <div class="avatar" style="width: 30px; height: 30px">{{ (a.display_name || a.username).slice(0, 1) }}</div>
            <div class="who">
              <b class="truncate">{{ a.display_name }}</b>
              <span class="truncate">@{{ a.username }}</span>
            </div>
            <span v-if="!a.active" class="badge">停用</span>
          </div>
          <div class="acard-role">
            <span class="rl-lab">角色</span>
            <select
              class="rolesel wide"
              :class="'r-' + a.role"
              :value="a.role"
              :disabled="a.id === store.user?.id"
              :title="a.id === store.user?.id ? '不能修改自己的角色' : roleOf(a.role).desc"
              @change="setRole(a, $event.target.value)"
            >
              <option v-for="r in ROLES" :key="r.key" :value="r.key">{{ r.label }}</option>
            </select>
            <span class="rl-hint">{{ roleOf(a.role).desc }}</span>
          </div>
          <div class="acard-stats">
            <span><b>{{ a.projects }}</b> 项目</span>
            <span><b>{{ a.online }}</b> 在线</span>
            <span><b>{{ fmtNum(a.views) }}</b> 访问</span>
            <span>登录 <b>{{ a.last_login_at ? relTime(a.last_login_at) : '从未' }}</b></span>
          </div>
          <div class="acard-ops">
            <button class="btn sm" @click="resetPassword(a)">重置密码</button>
            <button class="btn sm" @click="rotateKey(a)"><Icon name="key" :size="12" /> 轮换 Key</button>
            <button v-if="a.id !== store.user?.id" class="btn sm" @click="toggleActive(a)">
              {{ a.active ? '停用' : '启用' }}
            </button>
            <button
              v-if="a.id !== store.user?.id"
              class="btn sm ghost"
              style="color: var(--danger)"
              @click="remove(a)"
            >
              <Icon name="trash" :size="12" /> 删除
            </button>
          </div>
        </div>
      </div>
      <div v-else-if="loading" class="acard"><div class="skel" style="height: 40px" /></div>
    </div>

    <p class="dim" style="font-size: 12px; margin-top: 12px">
      成员在自己的机器上执行 <span class="mono">agentctl login --url &lt;站点地址&gt;</span> 保存 Key，之后
      <span class="mono">agentctl deploy ./dist --ttl 24 --tags v2</span> 即可上传。
    </p>
  </div>

  <div v-if="createOpen" class="scrim" @click="createOpen = false" />
  <div v-if="createOpen" class="modal" style="width: 420px">
    <div class="modal-head">
      <h2>添加成员</h2>
      <div style="flex: 1" />
      <button class="btn ghost icon" @click="createOpen = false"><Icon name="close" :size="14" /></button>
    </div>
    <div class="modal-body">
      <div class="form">
        <div class="frow">
          <label>账号</label>
          <input v-model="form.username" class="input" placeholder="小写字母/数字，如 alice" />
        </div>
        <div class="frow">
          <label>显示名</label>
          <input v-model="form.display_name" class="input" placeholder="用于列表展示" />
        </div>
        <div class="frow">
          <label>初始密码</label>
          <input v-model="form.password" class="input" placeholder="留空自动生成" />
        </div>
        <div class="frow">
          <label>角色</label>
          <div class="rolepick">
            <button
              v-for="r in ROLES"
              :key="r.key"
              type="button"
              class="rp"
              :class="{ on: form.role === r.key }"
              @click="form.role = r.key"
            >
              <span class="rp-dot" />
              <span class="rp-txt">
                <b>{{ r.label }}</b>
                <em>{{ r.desc }}</em>
              </span>
            </button>
          </div>
          <span class="hint">创建后仍可在列表里随时改。</span>
        </div>
      </div>
    </div>
    <div class="modal-foot">
      <button class="btn" @click="createOpen = false">取消</button>
      <button class="btn primary" :disabled="busy" @click="submit">创建</button>
    </div>
  </div>

  <div v-if="created" class="scrim" @click="created = null" />
  <div v-if="created" class="modal" style="width: 440px">
    <div class="modal-head"><h2>凭据（只显示一次）</h2></div>
    <div class="modal-body">
      <p class="muted" style="font-size: 12.5px; margin-bottom: 12px">
        关闭后密码不可再查看，API Key 可通过「轮换」重新生成。
      </p>
      <dl class="kv">
        <dt>账号</dt>
        <dd class="mono">{{ created.username }}</dd>
        <dt v-if="created.password">密码</dt>
        <dd v-if="created.password" class="mono">{{ created.password }}</dd>
        <dt v-if="created.api_key">API Key</dt>
        <dd v-if="created.api_key" class="mono" style="word-break: break-all">{{ created.api_key }}</dd>
      </dl>
      <div style="display: flex; gap: 6px; margin-top: 14px">
        <button v-if="created.api_key" class="btn sm" @click="copy(created.api_key)">复制 Key</button>
        <button
          v-if="created.password"
          class="btn sm"
          @click="copy(`agentctl login --url ${location.origin} --username ${created.username} --password '${created.password}'`)"
        >
          复制登录命令
        </button>
      </div>
    </div>
    <div class="modal-foot">
      <button class="btn primary" @click="created = null">我已保存</button>
    </div>
  </div>
</template>

<style scoped>
/* ---------- 角色切换下拉：三档，按角色着色 ---------- */
.rolesel {
  appearance: none;
  -webkit-appearance: none;
  width: auto;
  max-width: 124px;
  padding: 2px 22px 2px 10px;
  border: 1px solid var(--line-2);
  border-radius: 999px;
  background-color: var(--surface-3);
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='%237b8189' stroke-width='2.6' stroke-linecap='round' stroke-linejoin='round'><path d='M6 9l6 6 6-6'/></svg>");
  background-repeat: no-repeat;
  background-position: right 7px center;
  color: var(--ink-2);
  font-family: inherit;
  font-size: 11.5px;
  font-weight: 600;
  line-height: 1.6;
  cursor: pointer;
  text-overflow: ellipsis;
  transition: border-color 0.16s var(--ease), box-shadow 0.16s var(--ease), background-color 0.16s var(--ease);
}
.rolesel:hover:not(:disabled) { border-color: var(--ink-4); }
.rolesel:focus-visible {
  outline: none;
  border-color: var(--brand);
  box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.12);
}
.rolesel:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.rolesel.r-viewer { color: var(--ink-3); background-color: var(--surface-3); border-color: var(--line); }
.rolesel.r-publisher { color: var(--brand); background-color: var(--brand-soft); border-color: var(--brand-line); }
.rolesel.r-admin {
  color: #fff;
  background-color: var(--brand);
  border-color: transparent;
  font-weight: 650;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='%23ffffff' stroke-width='2.6' stroke-linecap='round' stroke-linejoin='round'><path d='M6 9l6 6 6-6'/></svg>");
}

/* 窄屏卡片里的角色行 */
.acard-role {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
}
.rl-lab { flex: 0 0 auto; font-size: 11.5px; color: var(--ink-4); }
.rolesel.wide { flex: 1 1 84px; min-width: 0; max-width: none; padding-top: 3px; padding-bottom: 3px; }
.rl-hint { flex: 1 1 100%; font-size: 11px; color: var(--ink-4); line-height: 1.45; }

/* ---------- 创建对话框的角色单选 ---------- */
.rolepick { display: flex; flex-direction: column; gap: 6px; }
.rp {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  width: 100%;
  padding: 8px 11px;
  border: 1px solid var(--line-2);
  border-radius: var(--radius-sm);
  background: var(--surface);
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.16s var(--ease), background-color 0.16s var(--ease);
}
.rp:hover { border-color: var(--ink-4); background: var(--surface-2); }
.rp.on { border-color: var(--brand); background: var(--brand-soft); }
.rp-dot {
  position: relative;
  flex: 0 0 auto;
  width: 13px;
  height: 13px;
  margin-top: 3px;
  border: 1.5px solid var(--line-2);
  border-radius: 50%;
  transition: border-color 0.16s var(--ease);
}
.rp.on .rp-dot { border-color: var(--brand); }
.rp.on .rp-dot::after {
  content: '';
  position: absolute;
  inset: 2.5px;
  border-radius: 50%;
  background: var(--brand);
}
.rp-txt { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.rp-txt b { font-size: 12.5px; font-weight: 650; color: var(--ink); }
.rp-txt em { font-style: normal; font-size: 11.5px; color: var(--ink-4); }
</style>
