<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api'
import { store, toast } from '../store'
import { fmtBytes, hoursLabel } from '../format'
import { allowedText, checkTags } from '../tags'
import { TITLE_RULE, clampTitle, fmtWidth, titleError, titleWidth } from '../namerule'
import Icon from './Icon.vue'

const emit = defineEmits(['close', 'created'])

const props = defineProps({
  collections: { type: Object, default: () => ({ items: [] }) },
})

const mode = ref('files') // files | zip | link
const ttlDefaults = ref({ portal: 6, link: 12, private: 0 })
const form = ref({
  slug: '',
  title: '',
  description: '',
  tags: '',
  collection: '',
  hours: '', // 空 = 跟随可见性默认
  forever: false,
  expire_action: 'block',
  allow_download: true, // 文件夹传上来就该能直接下走，默认开着
  visibility: 'link',
  link_url: '',
})
const picked = ref([]) // {file, rel}
const zipFile = ref(null)
const dragOver = ref(false)
const uploading = ref(false)
const progress = ref(0)
const error = ref('')
// 存活时长/到期动作这些一次性的选项收在「高级」里，首屏留给名字和分类
const advOpen = ref(false)
const advEl = ref(null)

function toggleAdv() {
  advOpen.value = !advOpen.value
  // 弹窗内容比视口高，展开后高级区往往落在折叠线以下，滚过去免得只露个边
  if (advOpen.value) nextTick(() => advEl.value?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }))
}

const totalSize = computed(() => picked.value.reduce((s, p) => s + p.file.size, 0))

// 标签边填边校验：不合规直接在弹窗里说清楚，别等提交才被打回
const tagCheck = computed(() => checkTags(form.value.tags, store.tagRules))

// 项目名按显示宽度算：10 个中文字符 ≈ 20 个英文字符，超了在失焦时自动截短
const titleW = computed(() => titleWidth(form.value.title))
const titleErr = computed(() => titleError(form.value.title))

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

function clampInputTitle() {
  form.value.title = clampTitle(form.value.title)
}

const VIS_OPTS = [
  { key: 'portal', label: '门户可见', desc: '出现在访客门户列表' },
  { key: 'link', label: '持链接可见', desc: '不列出，拿到链接即可打开' },
  { key: 'private', label: '仅自己可见', desc: '需登录且为本人或管理员' },
]

const ttlOf = (vis = form.value.visibility) => Number(ttlDefaults.value[vis] ?? 0)
const ttlLabel = (vis = form.value.visibility) => (ttlOf(vis) > 0 ? hoursLabel(ttlOf(vis)) : '永久')

// 时长为空时跟随可见性默认，这里只是给个可视化提示
const effectiveTTL = computed(() => {
  if (form.value.forever) return '永久'
  return form.value.hours === '' ? ttlLabel() : hoursLabel(Number(form.value.hours))
})

// 高级区收起时也要能一眼看到将按什么规则创建
const advSummary = computed(
  () => `${effectiveTTL.value} · ${form.value.expire_action === 'delete' ? '到期删除文件' : '到期停止访问'}`
)

onMounted(async () => {
  window.addEventListener('keydown', onKey, true)
  try {
    const m = await api.get('/api/meta')
    if (m.ttl_defaults) ttlDefaults.value = { ...ttlDefaults.value, ...m.ttl_defaults }
    if (m.default_expire_action) form.value.expire_action = m.default_expire_action
  } catch {
    /* 拿不到就用内置默认值 */
  }
})
onUnmounted(() => window.removeEventListener('keydown', onKey, true))

function onKey(e) {
  if (e.key === 'Escape' && !uploading.value) {
    e.stopPropagation()
    emit('close')
  }
}

function addFiles(list) {
  const next = []
  for (const item of list) {
    const f = item.file || item
    const rel = item.rel || f.webkitRelativePath || f.name
    if (!rel || rel.endsWith('/')) continue
    next.push({ file: f, rel })
  }
  const seen = new Set(picked.value.map((p) => p.rel))
  picked.value = [...picked.value, ...next.filter((n) => !seen.has(n.rel))]
}

function onPick(e) {
  addFiles([...e.target.files].map((f) => ({ file: f, rel: f.webkitRelativePath || f.name })))
  e.target.value = ''
}

function onZipPick(e) {
  zipFile.value = e.target.files?.[0] || null
  e.target.value = ''
}

async function walkEntry(entry, prefix = '') {
  if (!entry) return []
  if (entry.isFile) {
    const file = await new Promise((res, rej) => entry.file(res, rej))
    return [{ file, rel: prefix + file.name }]
  }
  if (entry.isDirectory) {
    const reader = entry.createReader()
    const entries = []
    while (true) {
      const batch = await new Promise((res, rej) => reader.readEntries(res, rej))
      if (!batch.length) break
      entries.push(...batch)
    }
    const out = []
    for (const e of entries) out.push(...(await walkEntry(e, `${prefix}${entry.name}/`)))
    return out
  }
  return []
}

async function onDrop(e) {
  dragOver.value = false
  const items = [...(e.dataTransfer?.items || [])]
  if (!items.length) {
    addFiles([...e.dataTransfer.files].map((f) => ({ file: f, rel: f.name })))
    return
  }
  const all = []
  for (const it of items) {
    const entry = it.webkitGetAsEntry?.()
    if (entry) all.push(...(await walkEntry(entry)))
  }
  if (!all.length) addFiles([...e.dataTransfer.files].map((f) => ({ file: f, rel: f.name })))
  else addFiles(all)
}

function humanRel(rel) {
  return rel.replace(/\/$/, '')
}

async function submit() {
  error.value = ''
  clampInputTitle() // 后端也会截，这里先截一次让用户看到的是最终名字
  if (mode.value === 'link') return submitLink()
  if (mode.value === 'files' && !picked.value.length) return (error.value = '请选择要上传的文件或文件夹')
  if (mode.value === 'zip' && !zipFile.value) return (error.value = '请选择 zip 文件')
  if (tagCheck.value.error) return (error.value = tagCheck.value.error)

  const fd = new FormData()
  fd.append('slug', form.value.slug || '')
  fd.append('title', form.value.title || '')
  fd.append('description', form.value.description || '')
  fd.append('tags', form.value.tags || '')
  fd.append('collection', form.value.collection || '')
  fd.append('expire_action', form.value.expire_action)
  fd.append('visibility', form.value.visibility)
  fd.append('allow_download', form.value.allow_download ? '1' : '0')
  if (form.value.forever) fd.append('forever', '1')
  else fd.append('hours', String(form.value.hours || ''))

  if (mode.value === 'zip') {
    fd.append('zip', zipFile.value, zipFile.value.name)
  } else {
    for (const p of picked.value) fd.append('files', p.file, p.rel)
  }

  uploading.value = true
  progress.value = 0
  try {
    const d = await api.upload(fd, (p) => (progress.value = p))
    toast('上传完成，预览已生成')
    emit('created', d)
    emit('close')
  } catch (e) {
    error.value = e.message || '上传失败'
  } finally {
    uploading.value = false
  }
}

async function submitLink() {
  if (!form.value.link_url.trim()) return (error.value = '请填写外链地址')
  clampInputTitle()
  if (tagCheck.value.error) return (error.value = tagCheck.value.error)
  uploading.value = true
  try {
    const d = await api.post('/api/projects/link', {
      link_url: form.value.link_url,
      title: form.value.title,
      slug: form.value.slug,
      description: form.value.description,
      tags: form.value.tags,
      collection_id: form.value.collection || null,
      visibility: form.value.visibility,
      hours: form.value.forever ? null : form.value.hours === '' ? null : Number(form.value.hours),
      forever: form.value.forever,
    })
    toast('外链已登记')
    emit('created', d)
    emit('close')
  } catch (e) {
    error.value = e.message || '创建失败'
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div class="scrim" @click="emit('close')" />
  <div class="modal" role="dialog" aria-modal="true">
    <div class="modal-head">
      <h2>新建项目</h2>
      <div style="flex: 1" />
      <button class="btn ghost icon" @click="emit('close')"><Icon name="close" :size="16" /></button>
    </div>

    <div class="modal-body">
      <div class="seg" style="margin-bottom: 12px">
        <button :class="{ on: mode === 'files' }" @click="mode = 'files'">文件 / 文件夹</button>
        <button :class="{ on: mode === 'zip' }" @click="mode = 'zip'">ZIP 压缩包</button>
        <button :class="{ on: mode === 'link' }" @click="mode = 'link'">外部链接</button>
      </div>

      <div
        v-if="error"
        style="background: var(--danger-soft); color: var(--danger); border: 1px solid var(--danger-line); border-radius: 8px; padding: 7px 10px; font-size: 12px; margin-bottom: 12px"
      >
        {{ error }}
      </div>

      <div class="form">
        <template v-if="mode !== 'link'">
          <div
            v-if="mode === 'files'"
            class="dropzone"
            :class="{ over: dragOver }"
            @click="$refs.dir.click()"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
          >
            <div style="font-weight: 600; color: var(--ink-2); margin-bottom: 2px">拖入文件夹，或点击选择</div>
            <div>支持整个目录，自动保留相对路径；单文件不限文件名，多文件需有根目录 index.html</div>
            <div style="margin-top: 9px; display: flex; gap: 6px; justify-content: center">
              <button class="btn sm" @click.stop="$refs.dir.click()">选择文件夹</button>
              <button class="btn sm" @click.stop="$refs.files.click()">选择文件</button>
            </div>
          </div>

          <div v-else class="dropzone" @click="$refs.zip.click()">
            <div style="font-weight: 600; color: var(--ink-2); margin-bottom: 2px">
              {{ zipFile ? zipFile.name : '选择一个 zip 压缩包' }}
            </div>
            <div>{{ zipFile ? fmtBytes(zipFile.size) : '压缩包作为下载内容，不参与在线预览' }}</div>
            <div style="margin-top: 9px">
              <button class="btn sm" @click.stop="$refs.zip.click()">浏览文件</button>
            </div>
          </div>

          <input ref="dir" type="file" multiple webkitdirectory directory style="display: none" @change="onPick" />
          <input ref="files" type="file" multiple style="display: none" @change="onPick" />
          <input ref="zip" type="file" accept=".zip" style="display: none" @change="onZipPick" />

          <div v-if="picked.length" class="filelist">
            <div v-for="p in picked.slice(0, 60)" :key="p.rel">
              <span class="mono truncate" style="max-width: 300px">{{ humanRel(p.rel) }}</span>
              <span class="dim num">{{ fmtBytes(p.file.size) }}</span>
            </div>
            <div v-if="picked.length > 60" class="dim">… 共 {{ picked.length }} 个文件（{{ fmtBytes(totalSize) }}）</div>
          </div>
        </template>

        <div v-else class="frow">
          <label>目标地址</label>
          <input v-model="form.link_url" class="input" placeholder="https://example.com/demo" />
          <span class="hint">只登记链接，不复制内容；点开经本地短链跳转，能统计访问</span>
        </div>

        <div class="frow two">
          <div class="frow">
            <label>
              名称
              <span class="dim" style="font-weight: 500">（{{ fmtWidth(titleW) }}/{{ TITLE_RULE.max_width }}）</span>
            </label>
            <input
              v-model="form.title"
              class="input"
              placeholder="用于列表展示，可中文"
              @blur="clampInputTitle"
            />
            <span v-if="titleErr" class="hint" style="color: var(--danger)">
              超了，提交时会自动截短
            </span>
            <span v-else class="hint">
              ≤{{ TITLE_RULE.max_cjk }} 中文 / {{ TITLE_RULE.max_narrow }} 英文，同名不可重复
            </span>
          </div>
          <div class="frow">
            <label>Slug</label>
            <input v-model="form.slug" class="input" placeholder="留空自动生成" />
            <span class="hint">同名再传一次 = 覆盖更新</span>
          </div>
        </div>

        <div class="frow">
          <label>分组</label>
          <select v-model="form.collection" class="field">
            <option value="">未归类</option>
            <option v-for="o in folderOptions" :key="o.id" :value="o.id">{{ o.label }}</option>
          </select>
          <span class="hint">项目多了按分组归类更好找；也可以先空着，回头批量挪</span>
        </div>

        <div class="frow">
          <label>说明</label>
          <textarea v-model="form.description" class="textarea" placeholder="一句话描述用途（可选）" />
        </div>

        <div class="frow">
          <label>
            标签
            <span class="dim" style="font-weight: 500">（{{ tagCheck.tags.length }}/{{ store.tagRules.max_per_project }}）</span>
          </label>
          <input v-model="form.tags" class="input" placeholder="逗号分隔，例如：前端, 验收, v2" />
          <div v-if="tagCheck.tags.length" class="tagprev">
            <span v-for="t in tagCheck.tags" :key="t" class="tag">{{ t }}</span>
          </div>
          <span v-if="tagCheck.error" class="hint" style="color: var(--danger)">{{ tagCheck.error }}</span>
          <span v-else class="hint">
            最多 {{ store.tagRules.max_per_project }} 个、每个 ≤{{ store.tagRules.max_len }} 字，只能用{{ allowedText }}；英文自动转小写
          </span>
        </div>

        <div class="frow">
          <label>可见性</label>
          <div class="seg" style="width: fit-content">
            <button
              v-for="v in VIS_OPTS"
              :key="v.key"
              :class="{ on: form.visibility === v.key }"
              :title="`${v.desc} · 默认 ${ttlLabel(v.key)}`"
              @click="form.visibility = v.key"
            >
              {{ v.label }}
            </button>
          </div>
          <span class="hint">
            {{ VIS_OPTS.find((v) => v.key === form.visibility)?.desc }} · 该可见性默认 {{ ttlLabel() }}
          </span>
        </div>

        <div ref="advEl" class="adv" :class="{ open: advOpen }">
          <button type="button" class="advhead" @click="toggleAdv">
            <Icon name="sliders" :size="16" />
            <span>高级设置</span>
            <span class="advsum">{{ advSummary }}</span>
            <Icon name="chevron" :size="16" class="advcaret" />
          </button>

          <div v-if="advOpen" class="advbody">
            <div class="frow">
              <label>存活时长</label>
              <select v-model="form.hours" class="input" :disabled="form.forever">
                <option value="">跟随可见性默认（{{ ttlLabel() }}）</option>
                <option value="1">1 小时</option>
                <option value="6">6 小时</option>
                <option value="12">12 小时</option>
                <option value="24">24 小时</option>
                <option value="72">3 天</option>
                <option value="168">7 天</option>
                <option value="720">30 天</option>
              </select>
              <span class="hint">本次将创建为：{{ effectiveTTL }}</span>
            </div>

            <div class="checkrow">
              <label class="check">
                <input v-model="form.forever" type="checkbox" /> 永久保存（不自动到期）
              </label>
              <label class="check">
                <input v-model="form.allow_download" type="checkbox" /> 允许下载（整包 zip + 单个文件）
              </label>
            </div>

            <div class="frow">
              <label>到期后</label>
              <div class="seg" style="width: fit-content">
                <button
                  :class="{ on: form.expire_action === 'block' }"
                  @click="form.expire_action = 'block'"
                >
                  停止访问
                </button>
                <button
                  :class="{ on: form.expire_action === 'delete' }"
                  @click="form.expire_action = 'delete'"
                >
                  删除文件
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="uploading" class="progress"><i :style="{ width: progress + '%' }" /></div>
    </div>

    <div class="modal-foot">
      <button class="btn" @click="emit('close')">取消</button>
      <button class="btn primary" :disabled="uploading" @click="submit">
        {{ uploading ? (progress ? `上传中 ${progress}%` : '处理中…') : '创建' }}
      </button>
    </div>
  </div>
</template>
