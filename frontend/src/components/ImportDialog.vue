<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api'
import { toast } from '../store'
import Icon from './Icon.vue'

const props = defineProps({
  collections: { type: Object, default: () => ({ items: [] }) },
  defaultCollection: { type: String, default: '' },
})
const emit = defineEmits(['close', 'imported'])

const file = ref(null)
const dragOver = ref(false)
const bm = ref(null)
const parentId = ref(
  props.defaultCollection && props.defaultCollection !== 'none' ? props.defaultCollection : ''
)
const visibility = ref('private')
const tag = ref('')
const preview = ref(null)
const busy = ref(false)
const error = ref('')

const folderOptions = computed(() => {
  const out = []
  for (const node of props.collections.items || []) {
    out.push({ id: String(node.id), label: node.name })
    for (const kid of node.children || []) {
      out.push({ id: String(kid.id), label: `${node.name} / ${kid.name}` })
    }
  }
  return out
})

function onKey(e) {
  if (e.key === 'Escape' && !busy.value) {
    e.stopPropagation()
    emit('close')
  }
}
onMounted(() => window.addEventListener('keydown', onKey, true))
onUnmounted(() => window.removeEventListener('keydown', onKey, true))

function pick(e) {
  const f = e.target.files?.[0]
  if (f) setFile(f)
  e.target.value = ''
}

function onDrop(e) {
  dragOver.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f) setFile(f)
}

function setFile(f) {
  file.value = f
  preview.value = null
  error.value = ''
}

function payload() {
  const fd = new FormData()
  fd.append('file', file.value, file.value.name)
  fd.append('parent_id', parentId.value || '')
  fd.append('visibility', visibility.value)
  fd.append('tag', tag.value || '')
  return fd
}

async function runPreview() {
  if (!file.value) return (error.value = '先选一个书签文件（.html）')
  busy.value = true
  error.value = ''
  try {
    const fd = payload()
    fd.append('dry_run', '1')
    preview.value = await api.postForm('/api/import/bookmarks', fd)
    if (!preview.value.will_create) {
      error.value = preview.value.skipped_duplicate
        ? '这些书签都已经在库里了（按网址判重），没有新内容可导入'
        : '这个文件里没有可导入的书签'
    }
  } catch (e) {
    error.value = e.message || '解析失败'
  } finally {
    busy.value = false
  }
}

async function doImport() {
  if (!preview.value?.will_create) return
  busy.value = true
  error.value = ''
  try {
    const d = await api.postForm('/api/import/bookmarks', payload())
    toast(
      `已导入 ${d.created} 个书签` +
        (d.folders_created ? `、${d.folders_created} 个分组` : '') +
        (d.skipped_duplicate ? `，跳过 ${d.skipped_duplicate} 个重复` : ''),
    )
    emit('imported', d)
    emit('close')
  } catch (e) {
    error.value = e.message || '导入失败'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="scrim" @click="emit('close')" />
  <div class="modal" role="dialog" aria-modal="true" style="max-width: 520px">
    <div class="modal-head">
      <h2>导入浏览器书签</h2>
      <div style="flex: 1" />
      <button class="btn ghost icon" @click="emit('close')"><Icon name="close" :size="16" /></button>
    </div>

    <div class="modal-body">
      <div
        class="dropzone"
        :class="{ over: dragOver }"
        @click="bm?.click()"
        @dragover.prevent="dragOver = true"
        @dragleave.prevent="dragOver = false"
        @drop.prevent="onDrop"
      >
        <div style="font-weight: 600; color: var(--ink-2); margin-bottom: 2px">
          {{ file ? file.name : '把书签文件拖进来，或点击选择' }}
        </div>
        <div>Chrome / Edge / Firefox / Safari 导出的 HTML 都行</div>
      </div>
      <input ref="bm" type="file" accept=".html,.htm,text/html" style="display: none" @change="pick" />

      <div class="hint" style="margin: 8px 0 14px; line-height: 1.6">
        文件夹会变成分组（只取前两级，更深的折进第二级），书签变成外链项目；
        选了「导入到」某个分组时，书签的文件夹会挂在它下面，只多一层。
        同一个网址重复导入会自动跳过。
      </div>

      <div class="frow two">
        <div class="frow">
          <label>导入到</label>
          <select v-model="parentId" class="field">
            <option value="">顶层（按书签文件夹新建）</option>
            <option v-for="o in folderOptions" :key="o.id" :value="o.id">{{ o.label }}</option>
          </select>
        </div>
        <div class="frow">
          <label>可见性</label>
          <select v-model="visibility" class="field">
            <option value="private">仅自己可见（推荐）</option>
            <option value="link">持链接可见</option>
            <option value="portal">门户可见</option>
          </select>
        </div>
      </div>

      <div class="frow">
        <label>打一个标签（可选）</label>
        <input v-model="tag" class="field" placeholder="例如：书签" />
      </div>

      <div v-if="error" class="hint" style="color: var(--danger); margin-top: 4px">{{ error }}</div>

      <div v-if="preview" class="panel" style="padding: 10px 12px; margin-top: 10px; background: var(--surface-2); box-shadow: none">
        <div style="display: flex; gap: 14px; font-size: 12px; flex-wrap: wrap">
          <span>可导入 <b class="num">{{ preview.will_create }}</b> 条</span>
          <span class="dim">分组 {{ preview.folders_total }} 个</span>
          <span v-if="preview.skipped_duplicate" class="dim">重复 {{ preview.skipped_duplicate }}</span>
          <span v-if="preview.skipped_invalid" class="dim">无效 {{ preview.skipped_invalid }}</span>
          <span v-if="preview.truncated" class="dim">超量截断 {{ preview.truncated }}</span>
        </div>
        <div v-if="preview.folders?.length" class="dim" style="font-size: 11.5px; margin-top: 8px; line-height: 1.6">
          分组：{{ preview.folders.map((f) => (f[1] ? `${f[0]} / ${f[1]}` : f[0])).join('、') }}
        </div>
        <div v-if="preview.items?.length" class="dim" style="font-size: 11.5px; margin-top: 6px; line-height: 1.7">
          <div v-for="(it, i) in preview.items.slice(0, 6)" :key="i" class="truncate">
            · {{ it.title || it.url }}
          </div>
          <div v-if="preview.items.length > 6">… 共 {{ preview.will_create }} 条</div>
        </div>
      </div>
    </div>

    <div class="modal-foot">
      <button class="btn ghost" @click="emit('close')">取消</button>
      <div style="flex: 1" />
      <button class="btn" :disabled="busy || !file" @click="runPreview">
        {{ busy ? '解析中…' : '先预览' }}
      </button>
      <button class="btn primary" :disabled="busy || !preview?.will_create" @click="doImport">
        导入 {{ preview?.will_create || 0 }} 条
      </button>
    </div>
  </div>
</template>
