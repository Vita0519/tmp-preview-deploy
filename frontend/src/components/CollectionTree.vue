<script setup>
import { computed, nextTick, ref } from 'vue'
import { api } from '../api'
import { confirmAction, toast } from '../store'
import Icon from './Icon.vue'

const props = defineProps({
  tree: { type: Object, default: () => ({ items: [], unassigned: 0, total: 0 }) },
  active: { type: String, default: '' }, // '' 全部 | 'none' 未归类 | '12' 收藏夹 id
  visibility: { type: String, default: '' }, // '' | portal | link | private；只有收藏夹为空时才归三档高亮
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['select', 'changed'])

const items = computed(() => props.tree.items || [])
const loose = computed(() => props.tree.unassigned || 0)
const grandTotal = computed(() => props.tree.total || 0)
const vis = computed(() => props.tree.visibility || { portal: 0, link: 0, private: 0 })

// 三档可见性是「跳全站」的导航，跟收藏夹抢同一个当前选中；
// 工具栏那个下拉是「在当前夹里快筛」，两者不是一回事，所以这里高亮要排除 active 非空的情况
const VIS_ROWS = [
  { key: 'portal', label: '门户可见', icon: 'eye' },
  { key: 'link', label: '持链接', icon: 'external' },
  { key: 'private', label: '仅自己', icon: 'key' },
]

const open = ref({})
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
}

function pick(key) {
  menu.value = ''
  emit('select', String(key))
}

function startNew(parentId = null) {
  menu.value = ''
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
      toast(`收藏夹「${d.collection.name}」已创建`)
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
    title: `删除收藏夹「${node.name}」`,
    message: n
      ? `里面的 ${n} 个项目不会被删除，会退回「未归类」。`
      : '这是一个空收藏夹，删除后不可恢复。',
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
      <button class="railadd" title="新建收藏夹" @click="startNew(null)">
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
        :title="`跳出收藏夹，看全站${v.label}的项目`"
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
      <div class="raillabel">收藏夹</div>

      <div v-for="node in items" :key="node.id" class="railnode">
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
          <span class="n num">{{ countOf(node) }}</span>
          <span class="dots" title="更多" @click.stop="menu = menu === node.id ? '' : node.id">⋯</span>
        </div>

        <div v-if="menu === node.id" class="railmenu">
          <button @click="startNew(node.id)">新建子收藏夹</button>
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
            placeholder="子收藏夹名"
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
              <span class="n num">{{ countOf(kid) }}</span>
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

      <div v-if="editKey === 'n0'" class="railedit">
        <input
          :ref="bindEditor"
          class="input"
          placeholder="收藏夹名，回车保存"
          :value="edit.value"
          :disabled="busy"
          @input="edit.value = $event.target.value"
          @keyup.enter="submitEdit"
          @keydown.esc.stop.prevent="cancelEdit"
          @blur="submitEdit"
        />
      </div>

      <div v-if="!items.length && !loading" class="railempty">
        还没有收藏夹。<br />新建一个，或从浏览器导入书签。
      </div>
    </div>
  </aside>
</template>
