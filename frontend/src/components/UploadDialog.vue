<script setup>
import { computed, ref } from 'vue'
import { api } from '../api'
import { toast } from '../store'
import { fmtBytes } from '../format'
import Icon from './Icon.vue'

const emit = defineEmits(['close', 'created'])

const mode = ref('files') // files | zip | link
const form = ref({
  slug: '',
  title: '',
  description: '',
  tags: '',
  hours: '24',
  forever: false,
  expire_action: 'block',
  allow_download: false,
  visibility: 'link',
  link_url: '',
})
const picked = ref([]) // {file, rel}
const zipFile = ref(null)
const dragOver = ref(false)
const uploading = ref(false)
const progress = ref(0)
const error = ref('')

const totalSize = computed(() => picked.value.reduce((s, p) => s + p.file.size, 0))

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
  if (mode.value === 'link') return submitLink()
  if (mode.value === 'files' && !picked.value.length) return (error.value = '请选择要上传的文件或文件夹')
  if (mode.value === 'zip' && !zipFile.value) return (error.value = '请选择 zip 文件')

  const fd = new FormData()
  fd.append('slug', form.value.slug || '')
  fd.append('title', form.value.title || '')
  fd.append('description', form.value.description || '')
  fd.append('tags', form.value.tags || '')
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
  uploading.value = true
  try {
    const d = await api.post('/api/projects/link', {
      link_url: form.value.link_url,
      title: form.value.title,
      slug: form.value.slug,
      description: form.value.description,
      tags: form.value.tags,
      visibility: form.value.visibility,
      hours: form.value.forever ? null : Number(form.value.hours || 24),
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
      <button class="btn ghost icon" @click="emit('close')"><Icon name="close" :size="14" /></button>
    </div>

    <div class="modal-body">
      <div class="seg" style="margin-bottom: 14px">
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
            <div>支持整个目录，自动保留相对路径；入口需为 index.html</div>
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
          <span class="hint">只登记链接，不复制内容；点击卡片直接跳转</span>
        </div>

        <div class="frow two">
          <div class="frow">
            <label>名称</label>
            <input v-model="form.title" class="input" placeholder="用于列表展示，可中文" />
          </div>
          <div class="frow">
            <label>Slug</label>
            <input v-model="form.slug" class="input" placeholder="留空自动生成" />
          </div>
        </div>

        <div class="frow">
          <label>说明</label>
          <textarea v-model="form.description" class="textarea" placeholder="一句话描述用途（可选）" />
        </div>

        <div class="frow">
          <label>标签</label>
          <input v-model="form.tags" class="input" placeholder="用逗号分隔，例如：前端, 验收, v2" />
        </div>

        <div class="frow two">
          <div class="frow">
            <label>存活时长</label>
            <select v-model="form.hours" class="input" :disabled="form.forever">
              <option value="1">1 小时</option>
              <option value="6">6 小时</option>
              <option value="24">24 小时（默认）</option>
              <option value="72">3 天</option>
              <option value="168">7 天</option>
              <option value="720">30 天</option>
            </select>
          </div>
          <div class="frow">
            <label>可见性</label>
            <select v-model="form.visibility" class="input">
              <option value="link">持链接可见</option>
              <option value="portal">门户列表可见</option>
              <option value="private">仅自己可见</option>
            </select>
          </div>
        </div>

        <label class="check">
          <input v-model="form.forever" type="checkbox" /> 永久保存（不自动到期）
        </label>
        <label class="check">
          <input v-model="form.allow_download" type="checkbox" /> 开放 zip 下载
        </label>

        <div class="frow">
          <label>到期后</label>
          <div class="seg" style="width: fit-content">
            <button :class="{ on: form.expire_action === 'block' }" @click="form.expire_action = 'block'">停止访问</button>
            <button :class="{ on: form.expire_action === 'delete' }" @click="form.expire_action = 'delete'">删除文件</button>
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
