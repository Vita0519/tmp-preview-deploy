<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { api } from '../api'
import { confirmAction, toast } from '../store'
import { fmtBytes, fmtDate, fmtRemain, hoursLabel, relTime, typeLabel } from '../format'
import { TAG_RULES, allowedText, checkOneTag } from '../tags'
import { TITLE_RULE, fmtWidth, titleError, titleWidth } from '../namerule'
import Icon from './Icon.vue'
import Sparkline from './Sparkline.vue'

const props = defineProps({
  slug: { type: String, required: true },
  now: { type: Number, default: Date.now() },
})
const emit = defineEmits(['close', 'changed'])

const detail = ref(null)
const loading = ref(true)
const busy = ref(false)
const tagDraft = ref('')
const showFiles = ref(false)
const customHours = ref('')

const remaining = computed(() => {
  const d = detail.value
  if (!d) return { text: '—', cls: '', pct: 0 }
  if (d.permanent) return { text: '永久有效', cls: 'perm', pct: 100 }
  const ms = (d.expires_at || 0) - props.now
  if (ms <= 0) return { text: '已到期', cls: 'dead', pct: 0 }
  const total = (d.expires_at || 0) - (d.created_at || 0)
  return { text: fmtRemain(ms), cls: ms < 6 * 3600e3 ? 'warn' : '', pct: Math.min(100, (ms / total) * 100) }
})

// 统一用短链：外链项目由后端 302 到源站，同时记一次访问
const previewUrl = computed(() =>
  detail.value ? `${location.origin}/v/${detail.value.slug}` : ''
)

async function load() {
  loading.value = true
  try {
    detail.value = await api.get(`/api/projects/${props.slug}`)
  } catch (e) {
    toast(e.message || '读取失败', 'err')
    emit('close')
  } finally {
    loading.value = false
  }
}

async function patch(body, msg = '已保存') {
  busy.value = true
  try {
    const d = await api.patch(`/api/projects/${props.slug}`, body)
    detail.value = { ...detail.value, ...d, files: detail.value?.files }
    toast(msg)
    emit('changed')
    return true
  } catch (e) {
    toast(e.message || '保存失败', 'err')
    return false
  } finally {
    busy.value = false
  }
}

// ---- 改项目名：点标题就能改，宽度超了直接拦住 ----
const renaming = ref(false)
const titleDraft = ref('')
const titleInput = ref(null)

const draftWidth = computed(() => titleWidth(titleDraft.value))
const draftError = computed(() => titleError(titleDraft.value))
const draftLeft = computed(() => Math.max(0, TITLE_RULE.max_width - draftWidth.value))
const canSaveTitle = computed(
  () => !draftError.value && !!titleDraft.value.trim() && titleDraft.value.trim() !== detail.value?.title
)

function startRename() {
  titleDraft.value = detail.value?.title || ''
  renaming.value = true
  nextTick(() => {
    titleInput.value?.focus()
    titleInput.value?.select()
  })
}

function cancelRename() {
  renaming.value = false
  titleDraft.value = ''
}

async function saveTitle() {
  if (!canSaveTitle.value && !draftError.value && titleDraft.value.trim() === detail.value?.title) {
    return cancelRename()
  }
  if (draftError.value) return toast(draftError.value, 'err')
  const t = titleDraft.value.trim()
  if (!t) return toast('项目名不能为空', 'err')
  if (await patch({ title: t }, '项目名已更新')) cancelRename()
}

function extend(hours) {
  if (hours === null) return patch({ permanent: true }, '已设为永久')
  return patch({ hours, revive: true }, `已延长 ${hoursLabel(hours)}`)
}

async function setCustomHours() {
  const h = Number(customHours.value)
  if (!h || h <= 0) return toast('请输入有效小时数', 'err')
  await extend(h)
  customHours.value = ''
}

async function toggleDownload() {
  await patch({ allow_download: !detail.value.allow_download }, detail.value.allow_download ? '已关闭下载' : '已开放下载')
}

async function setVisibility(v) {
  await patch({ visibility: v }, '可见性已更新')
}

async function toggleExpireAction() {
  const next = detail.value.expire_action === 'delete' ? 'block' : 'delete'
  await patch({ expire_action: next }, next === 'delete' ? '到期将删除文件' : '到期将保留文件')
}

const tagFull = computed(() => (detail.value?.tags?.length || 0) >= TAG_RULES.max_per_project)

async function addTag() {
  const raw = tagDraft.value.trim()
  if (!raw) return
  const { tag, error } = checkOneTag(raw)
  if (error) return toast(error, 'err')
  const tags = detail.value.tags || []
  if (tags.includes(tag)) {
    tagDraft.value = ''
    return toast('这个标签已经有了', 'err')
  }
  if (tags.length >= TAG_RULES.max_per_project) {
    return toast(`每个项目最多 ${TAG_RULES.max_per_project} 个标签`, 'err')
  }
  tagDraft.value = ''
  await patch({ tags: [...tags, tag] }, '标签已更新')
}

async function removeTag(name) {
  const tags = (detail.value.tags || []).filter((t) => t !== name)
  await patch({ tags }, '标签已更新')
}

async function resetViews() {
  const ok = await confirmAction({
    title: '重置访问计数',
    message: `将把「${detail.value.title}」的访问次数与历史曲线清零，操作不可撤销。`,
    confirmText: '重置',
    danger: true,
  })
  if (!ok) return
  try {
    await api.post(`/api/projects/${props.slug}/reset-views`)
    detail.value.views = 0
    detail.value.daily_views = []
    toast('计数已清零')
    emit('changed')
  } catch (e) {
    toast(e.message, 'err')
  }
}

async function remove() {
  const ok = await confirmAction({
    title: '删除项目',
    message: `「${detail.value.title}」及其全部文件将被永久删除，链接立即失效。`,
    confirmText: '永久删除',
    danger: true,
  })
  if (!ok) return
  try {
    await api.del(`/api/projects/${props.slug}`)
    toast('项目已删除')
    emit('changed')
    emit('close')
  } catch (e) {
    toast(e.message, 'err')
  }
}

function copy(text, msg = '链接已复制') {
  navigator.clipboard?.writeText(text).then(
    () => toast(msg),
    () => toast('复制失败，请手动选择', 'err')
  )
}

onMounted(load)
</script>

<template>
  <div class="scrim" @click="emit('close')" />
  <aside class="drawer" @keydown.esc="emit('close')">
    <div v-if="loading" class="drawer-body">
      <div class="skel" style="height: 16px; width: 60%" />
      <div class="skel" style="height: 10px; width: 40%; margin-top: 10px" />
      <div class="skel" style="height: 60px; margin-top: 24px" />
    </div>

    <template v-else-if="detail">
      <div class="drawer-head">
        <div class="top">
          <div style="flex: 1; min-width: 0">
            <div v-if="!renaming" class="titlerow">
              <h2 class="truncate" :title="`${detail.title}（点一下改名）`" @click="startRename">
                {{ detail.title }}
              </h2>
              <button class="editbtn" title="重命名" @click="startRename">
                <Icon name="edit" :size="12" />
              </button>
            </div>
            <div v-else class="renamebox">
              <input
                ref="titleInput"
                v-model="titleDraft"
                class="input"
                maxlength="40"
                placeholder="项目名"
                @keydown.enter.prevent="saveTitle"
                @keydown.esc.stop.prevent="cancelRename"
              />
              <div class="renamefoot">
                <span class="counter" :class="{ over: !!draftError }" :title="draftError || '按显示宽度算：中文 1、英文数字 0.5'">
                  {{ fmtWidth(draftWidth) }} / {{ TITLE_RULE.max_width }}
                  <template v-if="draftError">· 超出 {{ fmtWidth(draftWidth - TITLE_RULE.max_width) }}</template>
                  <template v-else>· 还能写 {{ fmtWidth(draftLeft) }}</template>
                </span>
                <span style="flex: 1" />
                <button class="btn sm" :disabled="busy" @click="cancelRename">取消</button>
                <button class="btn sm primary" :disabled="busy || !canSaveTitle" @click="saveTitle">
                  {{ busy ? '保存中…' : '保存' }}
                </button>
              </div>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; margin-top: 5px">
              <span class="mono muted">/{{ detail.slug }}/</span>
              <button class="linkbtn" @click="copy(previewUrl)">复制链接</button>
              <button v-if="!renaming" class="linkbtn" @click="startRename">重命名</button>
            </div>
          </div>
          <button class="btn ghost icon" title="关闭" @click="emit('close')">
            <Icon name="close" :size="14" />
          </button>
        </div>
        <div style="display: flex; gap: 6px; margin-top: 10px; flex-wrap: wrap">
          <span class="badge" :class="{ brand: detail.kind === 'link' }">{{ typeLabel(detail.kind) }}</span>
          <span v-if="detail.expired" class="badge danger">已到期</span>
          <span v-else-if="detail.permanent" class="badge brand">永久</span>
          <span v-else class="badge">限时</span>
          <span
            v-if="detail.expire_action === 'delete'"
            class="badge del"
            title="到期后自动删除项目与文件，不可恢复"
          >
            <Icon name="trash" :size="10" />到期删除
          </span>
          <span class="badge">{{ detail.visibility === 'portal' ? '门户可见' : detail.visibility === 'private' ? '仅自己' : '链接可见' }}</span>
        </div>
      </div>

      <div class="drawer-body">
        <div class="panel" style="padding: 13px 14px; box-shadow: none; background: var(--surface-2)">
          <div style="display: flex; align-items: baseline; justify-content: space-between">
            <span class="muted" style="font-size: 11.5px">剩余时间</span>
            <span class="ttl num" :class="remaining.cls" style="font-size: 17px">{{ remaining.text }}</span>
          </div>
          <div v-if="!detail.permanent" class="bar" style="width: 100%; margin-top: 8px" :class="{ warn: remaining.cls === 'warn' }">
            <i :style="{ width: remaining.pct + '%' }" />
          </div>
          <div class="dim" style="font-size: 11px; margin-top: 7px">
            到期后{{ detail.expire_action === 'delete' ? '删除项目及文件' : '停止访问、保留文件' }} · 创建于 {{ fmtDate(detail.created_at) }}
          </div>
        </div>

        <div class="section">
          <h4>快速延长</h4>
          <div style="display: flex; gap: 6px; flex-wrap: wrap">
            <button class="btn sm" :disabled="busy" @click="extend(1)">+1 小时</button>
            <button class="btn sm" :disabled="busy" @click="extend(24)">+24 小时</button>
            <button class="btn sm" :disabled="busy" @click="extend(168)">+7 天</button>
            <button class="btn sm" :disabled="busy" @click="extend(null)">设为永久</button>
          </div>
          <div style="display: flex; gap: 6px; margin-top: 8px">
            <input v-model="customHours" class="input" type="number" min="0.1" step="0.5" placeholder="自定义小时数" style="height: 30px" @keyup.enter="setCustomHours" />
            <button class="btn sm" :disabled="busy" @click="setCustomHours">应用</button>
          </div>
        </div>

        <div class="section">
          <h4>
            标签
            <span class="dim" style="font-weight: 500; text-transform: none; letter-spacing: 0">
              {{ (detail.tags || []).length }}/{{ TAG_RULES.max_per_project }}
            </span>
          </h4>
          <div style="display: flex; gap: 5px; flex-wrap: wrap; align-items: center">
            <span v-for="t in detail.tags" :key="t" class="tag">
              {{ t }}
              <button
                style="border: 0; background: none; padding: 0 0 0 4px; color: var(--ink-4); cursor: pointer; font-size: 11px"
                @click="removeTag(t)"
              >
                ×
              </button>
            </span>
            <input
              v-model="tagDraft"
              class="input"
              :maxlength="TAG_RULES.max_len"
              :disabled="tagFull"
              :placeholder="tagFull ? '已达上限' : '+ 添加标签'"
              style="width: 108px; height: 24px; font-size: 11.5px; padding: 0 8px"
              @keyup.enter="addTag"
            />
          </div>
          <div class="dim" style="font-size: 10.5px; margin-top: 6px; line-height: 1.5">
            每个 ≤{{ TAG_RULES.max_len }} 字，只能用{{ allowedText }}；没有空格，全角自动转半角
          </div>
        </div>

        <div class="section">
          <h4>访问趋势（近 14 天）</h4>
          <div style="display: flex; align-items: flex-end; gap: 12px">
            <Sparkline :values="(detail.daily_views || []).map((d) => d.count)" :width="150" :height="34" />
            <div>
              <div class="num" style="font-size: 15px; font-weight: 650">{{ detail.views }}</div>
              <div class="dim" style="font-size: 10.5px">
                累计访问 · 最近 {{ detail.last_viewed_at ? relTime(detail.last_viewed_at) : '无' }}
              </div>
            </div>
          </div>
        </div>

        <div class="section">
          <h4>属性</h4>
          <dl class="kv">
            <dt>归属</dt>
            <dd>{{ detail.owner?.display_name || '—' }}</dd>
            <dt>文件</dt>
            <dd>{{ detail.file_count }} 个 · {{ fmtBytes(detail.size_bytes) }}</dd>
            <dt>下载</dt>
            <dd>
              <button class="linkbtn" :disabled="busy" @click="toggleDownload">
                {{ detail.allow_download ? '已开放，点击关闭' : '已关闭，点击开放' }}
              </button>
            </dd>
            <dt>可见性</dt>
            <dd style="display: flex; gap: 8px">
              <button class="linkbtn" :class="{ dim: detail.visibility !== 'portal' }" @click="setVisibility('portal')">门户</button>
              <button class="linkbtn" :class="{ dim: detail.visibility !== 'link' }" @click="setVisibility('link')">链接</button>
              <button class="linkbtn" :class="{ dim: detail.visibility !== 'private' }" @click="setVisibility('private')">私有</button>
            </dd>
            <dt>到期后</dt>
            <dd>
              <button class="linkbtn" :disabled="busy" @click="toggleExpireAction">
                {{ detail.expire_action === 'delete' ? '删除项目及文件（点击改）' : '停止访问、保留文件（点击改）' }}
              </button>
            </dd>
            <dt>更新</dt>
            <dd>{{ fmtDate(detail.updated_at) }}</dd>
            <dt>到期</dt>
            <dd>{{ detail.permanent ? '永久' : fmtDate(detail.expires_at) }}</dd>
          </dl>
        </div>

        <div v-if="detail.files?.length" class="section">
          <h4>
            文件清单
            <button class="linkbtn" style="margin-left: 6px; font-weight: 500" @click="showFiles = !showFiles">
              {{ showFiles ? '收起' : `展开 ${detail.files.length} 项` }}
            </button>
          </h4>
          <div v-if="showFiles" class="filelist" style="max-height: 220px">
            <div v-for="f in detail.files" :key="f.path">
              <span class="mono truncate" style="max-width: 280px">{{ f.path }}</span>
              <span class="dim num">{{ fmtBytes(f.size) }}</span>
            </div>
          </div>
        </div>

        <div class="section">
          <h4>危险操作</h4>
          <div class="actions-grid">
            <button class="btn sm" :disabled="busy" @click="resetViews">重置访问计数</button>
            <button class="btn sm danger" @click="remove">删除项目</button>
          </div>
        </div>
      </div>

      <div class="drawer-foot">
        <a class="btn primary" :href="detail.kind === 'link' ? detail.link_url : previewUrl" target="_blank" rel="noopener" style="flex: 1">
          <Icon name="external" :size="13" /> 打开预览
        </a>
        <a v-if="detail.allow_download" class="btn" :href="`/download/${detail.slug}`">下载 zip</a>
        <button class="btn ghost" @click="copy(`/p/${detail.slug}/`, '原始路径已复制')">复制原始路径</button>
      </div>
    </template>
  </aside>
</template>
