<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { api } from '../api'
import { confirmAction, store, toast } from '../store'
import Icon from './Icon.vue'

const props = defineProps({
  tree: { type: Object, default: () => ({ items: [], unassigned: 0, total: 0 }) },
  active: { type: String, default: '' }, // '' 全部 | 'none' 未归类 | '12' 分组 id
  visibility: { type: String, default: '' }, // '' | portal | link | private；只有分组为空时才归三档高亮
  owners: { type: Array, default: () => [] }, // 管理员的归属汇总 [{id, display_name, count, total}]
  ownerFilter: { type: String, default: '' },
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['select', 'changed', 'filter-owner'])

const items = computed(() => props.tree.items || [])
const loose = computed(() => props.tree.unassigned || 0)
const grandTotal = computed(() => props.tree.total || 0)
const vis = computed(() => props.tree.visibility || { portal: 0, link: 0, private: 0 })

const selfId = computed(() => String(store.user?.id ?? ''))
// 服务端给的 id 是数字，store 里也未必同型，统一转字符串再比，别指望 === 能对上
const isSelf = (id) => String(id) === selfId.value
// 只有管理员、且不止一个人有分组时才按成员分段——只有一堆自己的分组时多一层标题纯属噪音
const showGroups = computed(() => (props.owners || []).length > 1)

// 分组色点：按成员 id 取一个固定色，纯装饰，跟品牌色无关（深色画布下取亮色系）
const DOTS = ['#e07b6f', '#5cb88a', '#6aa2e0', '#d9a45c', '#a37fd0', '#54b3bc', '#dd8a52']
const dotColor = (id) => DOTS[Math.abs(Number(id) || 0) % DOTS.length]

const ownerPick = ref(props.ownerFilter || '')
watch(
  () => props.ownerFilter,
  (v) => {
    ownerPick.value = v || ''
  }
)
function emitFilter() {
  emit('filter-owner', ownerPick.value)
}

const groups = computed(() => {
  if (!showGroups.value) {
    // 平铺：普通成员视角，或者站上只有一个人建过分组
    return [{ key: '_all', id: null, flat: true, nodes: items.value }]
  }
  const list = [...(props.owners || [])]
  // 管理员自己还没建分组时也要有一组，否则「新建分组」的输入框没地方落
  if (store.user && !list.some((o) => String(o.id) === selfId.value)) {
    list.unshift({
      id: store.user.id,
      username: store.user.username,
      display_name: store.user.display_name || store.user.username,
      count: 0,
      total: 0,
    })
  }
  const pick = ownerPick.value ? list.filter((o) => String(o.id) === ownerPick.value) : list
  return pick.map((o) => ({
    ...o,
    key: String(o.id),
    flat: false,
    nodes: items.value.filter((n) => String(n.owner_id) === String(o.id)),
  }))
})

// 折叠状态记在 localStorage，刷新后保持
const loadFold = (k) => {
  try { return JSON.parse(localStorage.getItem(k) || '{}') || {} } catch { return {} }
}
const saveFold = (k, v) => {
  try { localStorage.setItem(k, JSON.stringify(v)) } catch {}
}
const gopen = ref(loadFold('pv_rail_groups'))
const groupOpen = (key) => gopen.value[key] !== false // 默认展开
function toggleGroup(key) {
  gopen.value = { ...gopen.value, [key]: !groupOpen(key) }
  saveFold('pv_rail_groups', gopen.value)
}

// 空状态要按「筛完之后还剩几个分组」判断，不能看 items.length
const visibleCount = computed(() => groups.value.reduce((s, g) => s + g.nodes.length, 0))

// 三档可见性是「跳全站」的导航，跟分组抢同一个当前选中；
// 工具栏那个下拉是「在当前分组里快筛」，两者不是一回事，所以这里高亮要排除 active 非空的情况
const VIS_ROWS = [
  { key: 'portal', label: '门户可见', icon: 'eye' },
  { key: 'link', label: '持链接', icon: 'external' },
  { key: 'private', label: '仅自己', icon: 'key' },
]

const open = ref(loadFold('pv_rail_nodes'))
const menu = ref('')
// {mode:'new'|'rename', id, parentId, value}
const edit = ref(null)
const busy = ref(false)

// 只可能有一个编辑框存在，用普通变量承接 DOM，避免 v-for 里 ref 变成数组
let editorEl = null
function bindEditor(el) {
  if (el) editorEl = el
}
function focusEditor() {
  nextTick(() => {
    editorEl?.focus()
    editorEl?.select?.()
  })
}

/** 唯一标识当前编辑行，模板里用字符串比较，避免同一 v-for 多处重复渲染 */
const editKey = computed(() => {
  const e = edit.value
  if (!e) return ''
  return e.mode === 'rename' ? `r${e.id}` : `n${e.parentId || 0}`
})

function toggle(id) {
  open.value = { ...open.value, [id]: !open.value[id] }
  saveFold('pv_rail_nodes', open.value)
}

function pick(key) {
  menu.value = ''
  emit('select', String(key))
}

function startNew(parentId = null) {
  menu.value = ''
  // 根级新建的输入框只挂在「我的」分组里，若当前正筛着别人的分组就先放开筛选，否则框没处落
  if (!parentId && ownerPick.value && ownerPick.value !== selfId.value) {
    ownerPick.value = ''
    emitFilter()
  }
  edit.value = { mode: 'new', parentId, value: '' }
  if (parentId) open.value = { ...open.value, [parentId]: true }
  focusEditor()
}

function startRename(node) {
  menu.value = ''
  edit.value = { mode: 'rename', id: node.id, value: node.name }
  focusEditor()
}

function cancelEdit() {
  edit.value = null
}

async function submitEdit() {
  const e = edit.value
  // Enter 与 blur 可能挤在一起触发，busy 期间不再重复提交（否则第二次必然撞 409 重名）
  if (!e || busy.value) return
  const name = String(e.value || '').trim()
  if (!name) return cancelEdit()
  busy.value = true
  try {
    if (e.mode === 'new') {
      const d = await api.post('/api/collections', { name, parent_id: e.parentId })
      toast(`分组「${d.collection.name}」已创建`)
      emit('select', String(d.collection.id))
    } else {
      await api.patch(`/api/collections/${e.id}`, { name })
      toast('已改名')
    }
    edit.value = null
    emit('changed')
  } catch (err) {
    toast(err.message || '保存失败', 'err')
  } finally {
    busy.value = false
  }
}

async function remove(node) {
  menu.value = ''
  const n = countOf(node)
  const ok = await confirmAction({
    title: `删除分组「${node.name}」`,
    message: n
      ? `里面的 ${n} 个项目不会被删除，会退回「未归类」。`
      : '这是一个空分组，删除后不可恢复。',
    confirmText: '删除',
    danger: true,
  })
  if (!ok) return
  try {
    const d = await api.del(`/api/collections/${node.id}`)
    toast(d.moved_to_unassigned ? `已删除，${d.moved_to_unassigned} 个项目退回未归类` : '已删除')
    if (props.active === String(node.id)) emit('select', '')
    emit('changed')
  } catch (e) {
    toast(e.message || '删除失败', 'err')
  }
}

function countOf(node) {
  return node.total ?? node.count ?? 0
}
</script>

<template>
  <aside class="rail">
    <div class="railhead">
      <span>分类</span>
      <button class="railadd" title="新建分组" @click="startNew(null)">
        <Icon name="plus" :size="12" />
      </button>
    </div>

    <div class="raillist">
      <div class="railrow" :class="{ on: active === '' && !visibility }" role="button" tabindex="0" @click="pick('')" @keydown.enter="pick('')">
        <Icon name="layers" :size="12" />
        <span class="nm">全部项目</span>
        <span class="n num">{{ grandTotal }}</span>
      </div>

      <div
        v-for="v in VIS_ROWS"
        :key="v.key"
        class="railrow vis"
        :class="{ on: !active && visibility === v.key }"
        role="button"
        tabindex="0"
        :title="`跳出分组，看全站${v.label}的项目`"
        @click="pick('vis:' + v.key)"
        @keydown.enter="pick('vis:' + v.key)"
      >
        <Icon :name="v.icon" :size="12" />
        <span class="nm">{{ v.label }}</span>
        <span class="n num">{{ vis[v.key] || 0 }}</span>
      </div>

      <div class="railrow" :class="{ on: active === 'none' }" role="button" tabindex="0" @click="pick('none')" @keydown.enter="pick('none')">
        <Icon name="inbox" :size="12" />
        <span class="nm">未归类</span>
        <span class="n num">{{ loose }}</span>
      </div>

      <div class="railsep" />
      <div class="raillabel">
        <span>分组</span>
        <select
          v-if="showGroups"
          v-model="ownerPick"
          class="railpick"
          title="只看某个成员名下的分组"
          @change="emitFilter"
        >
          <option value="">全部成员</option>
          <option v-for="o in owners" :key="o.id" :value="String(o.id)">
            {{ isSelf(o.id) ? '我的' : o.display_name }} ({{ o.count }})
          </option>
        </select>
      </div>

      <div v-for="g in groups" :key="g.key" class="railgw">
        <div
          v-if="!g.flat"
          class="railgroup"
          :class="{ open: groupOpen(g.key) }"
          role="button"
          tabindex="0"
          :title="`@${g.username || ''} 名下的分组`"
          @click="toggleGroup(g.key)"
          @keydown.enter="toggleGroup(g.key)"
        >
          <i class="dot" :style="{ background: dotColor(g.id) }" />
          <span class="gn">{{ isSelf(g.id) ? '我的分组' : g.display_name }}</span>
          <span class="gc num">{{ g.count }}</span>
          <Icon name="chevron" :size="10" class="crt" />
        </div>

        <div v-if="g.flat || groupOpen(g.key)" class="railgbody">
        <div v-for="node in g.nodes" :key="node.id" class="railnode">
          <div
            class="railrow"
            :class="{ on: active === String(node.id) }"
            role="button"
            tabindex="0"
            @click="pick(node.id)"
            @keydown.enter="pick(node.id)"
          >
            <span
              class="caret"
              :class="{ open: open[node.id], leaf: !node.children?.length }"
              @click.stop="node.children?.length && toggle(node.id)"
            >
              <Icon v-if="node.children?.length" name="chevron" :size="10" />
            </span>
            <span class="nm" :title="node.name">{{ node.name }}</span>
            <span class="n num">
              {{ countOf(node) }}<em v-if="node.total_foreign" class="xf" title="其中含其他成员的项目">+{{ node.total_foreign }}</em>
            </span>
            <span class="dots" title="更多" @click.stop="menu = menu === node.id ? '' : node.id">⋯</span>
          </div>

          <div v-if="menu === node.id" class="railmenu">
            <button @click="startNew(node.id)">新建子分组</button>
            <button @click="startRename(node)">重命名</button>
            <button class="danger" @click="remove(node)">删除</button>
          </div>

          <div v-if="editKey === 'r' + node.id" class="railedit">
            <input
              :ref="bindEditor"
              class="input"
              :value="edit.value"
              :disabled="busy"
              @input="edit.value = $event.target.value"
              @keyup.enter="submitEdit"
              @keydown.esc.stop.prevent="cancelEdit"
              @blur="submitEdit"
            />
          </div>

          <div v-if="editKey === 'n' + node.id" class="railedit kid">
            <input
              :ref="bindEditor"
              class="input"
              placeholder="子分组名"
              :value="edit.value"
              :disabled="busy"
              @input="edit.value = $event.target.value"
              @keyup.enter="submitEdit"
              @keydown.esc.stop.prevent="cancelEdit"
              @blur="submitEdit"
            />
          </div>

          <div v-if="open[node.id] && node.children?.length" class="railkids">
            <div v-for="kid in node.children" :key="kid.id" class="railnode">
              <div
                class="railrow kid"
                :class="{ on: active === String(kid.id) }"
                role="button"
                tabindex="0"
                @click="pick(kid.id)"
                @keydown.enter="pick(kid.id)"
              >
                <span class="nm" :title="kid.name">{{ kid.name }}</span>
                <span class="n num">
                  {{ countOf(kid) }}<em v-if="kid.count_foreign" class="xf" title="其中含其他成员的项目">+{{ kid.count_foreign }}</em>
                </span>
                <span class="dots" title="更多" @click.stop="menu = menu === kid.id ? '' : kid.id">⋯</span>
              </div>

              <div v-if="menu === kid.id" class="railmenu kidmenu">
                <button @click="startRename(kid)">重命名</button>
                <button class="danger" @click="remove(kid)">删除</button>
              </div>

              <div v-if="editKey === 'r' + kid.id" class="railedit kid">
                <input
                  :ref="bindEditor"
                  class="input"
                  :value="edit.value"
                  :disabled="busy"
                  @input="edit.value = $event.target.value"
                  @keyup.enter="submitEdit"
                  @keydown.esc.stop.prevent="cancelEdit"
                  @blur="submitEdit"
                />
              </div>
            </div>
          </div>
        </div>

          <div v-if="isSelf(g.id) && editKey === 'n0'" class="railedit">
            <input
              :ref="bindEditor"
              class="input"
              placeholder="分组名，回车保存"
              :value="edit.value"
              :disabled="busy"
              @input="edit.value = $event.target.value"
              @keyup.enter="submitEdit"
              @keydown.esc.stop.prevent="cancelEdit"
              @blur="submitEdit"
            />
          </div>
        </div>
      </div>

      <div v-if="!visibleCount && !loading" class="railempty">
        <template v-if="ownerPick">这个成员名下还没有分组。</template>
        <template v-else>还没有分组。<br />新建一个，或从浏览器导入书签。</template>
      </div>
    </div>
  </aside>
</template>
