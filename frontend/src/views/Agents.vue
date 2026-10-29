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
const form = reactive({ username: '', display_name: '', password: '', role: 'agent' })
const busy = ref(false)

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
    <div class="panel">
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
              <span class="badge" :class="{ brand: a.role === 'admin' }">{{ a.role === 'admin' ? '管理员' : '成员' }}</span>
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
          <select v-model="form.role" class="input">
            <option value="agent">成员（只看自己的项目）</option>
            <option value="admin">管理员（看全部）</option>
          </select>
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
