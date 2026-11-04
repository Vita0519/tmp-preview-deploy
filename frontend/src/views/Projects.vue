<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { api, qs } from '../api'
import { confirmAction, store, toast } from '../store'
import { fmtNum } from '../format'
import Icon from '../components/Icon.vue'
import StatStrip from '../components/StatStrip.vue'
import ProjectTable from '../components/ProjectTable.vue'
import ProjectDrawer from '../components/ProjectDrawer.vue'
import UploadDialog from '../components/UploadDialog.vue'
import CollectionTree from '../components/CollectionTree.vue'
import ImportDialog from '../components/ImportDialog.vue'

const data = reactive({
  items: [],
  total: 0,
  stats: {},
  facets: { agents: [], tags: [], kinds: {} },
  server_now: 0,
})
const trend = ref([])
const filters = reactive({
  q: '',
  agent: '',
  kind: '',
  visibility: '',
  collection: '',
  status: 'online',
  tags: [],
  sort: 'updated_at',
  order: 'desc',
})
const page = ref(1)
const size = ref(50)
const loading = ref(false)
const err = ref('')
const selected = ref([])
const openSlug = ref('')
const uploadOpen = ref(false)
const importOpen = ref(false)
const colTree = ref({ items: [], unassigned: 0, total: 0 })
const colLoading = ref(false)
const now = ref(Date.now())
let offset = 0
let qTimer = null
let refreshTimer = null
let tickTimer = null

const isAdmin = computed(() => store.user?.role === 'admin')
const totalPages = computed(() => Math.max(1, Math.ceil(data.total / size.value)))
const maxTagCount = computed(() =>
  Math.max(...(data.facets.tags || []).map((t) => t.count), 1)
)
const tagsForBar = computed(() => (data.facets.tags || []).slice(0, 10))

// 窄屏侧栏收起后，收藏夹（含「未归类」）只能靠工具栏这个下拉筛
const collectionOptions = computed(() => {
  const out = []
  for (const n of colTree.value.items || []) {
    out.push({ id: n.id, label: n.name })
    for (const k of n.children || []) out.push({ id: k.id, label: `└ ${k.name}` })
  }
  return out
})

const saved = (() => {
  try {
    return JSON.parse(localStorage.getItem('pv_filters') || '{}')
  } catch {
    return {}
  }
})()
if (saved.status) filters.status = saved.status
if (saved.sort) filters.sort = saved.sort
if (saved.order) filters.order = saved.order
if (saved.size) size.value = saved.size
// 收藏夹与可见性分类共用一条选中线，只能有一个生效：老版本存过两个的，按收藏夹优先
if (saved.collection) filters.collection = String(saved.collection)
else if (saved.visibility) filters.visibility = saved.visibility

async function load(keepSelection = false) {
  loading.value = true
  err.value = ''
  const prev = selected.value
  try {
    const query = qs({
      q: filters.q.trim(),
      agent: filters.agent,
      kind: filters.kind,
      visibility: filters.visibility,
      collection: filters.collection,
      status: filters.status,
      tag: filters.tags,
      sort: filters.sort,
      order: filters.order,
      limit: size.value,
      offset: (page.value - 1) * size.value,
    })
    const d = await api.get(`/api/projects?${query}`)
    data.items = d.items
    data.total = d.total
    data.stats = d.stats
    data.facets = d.facets
    data.server_now = d.server_now
    offset = d.server_now - Date.now()
    if (!keepSelection) {
      // 刷新（筛选变化 / 定时轮询 / 操作完成）时只丢掉「已经不在结果里」的勾选，
      // 还在的就留着——否则抽屉里改个标签回来，勾好的三个全白勾了
      const alive = new Set(data.items.map((i) => i.slug))
      selected.value = prev.filter((s) => alive.has(s))
    }
  } catch (e) {
    if (e.status !== 401) err.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadTrend() {
  try {
    const d = await api.get('/api/stats/trend?days=14')
    trend.value = d.items
  } catch {}
}

async function loadCollections() {
  colLoading.value = true
  try {
    colTree.value = await api.get('/api/collections')
  } catch {
    /* 收藏夹接口挂了不该拦着项目列表 */
  } finally {
    colLoading.value = false
  }
}

function onCollectionPicked(key) {
  // 赋值本身会触发下面的 watch（重置到第 1 页并重新拉取），不用手动 load
  const k = String(key)
  if (k === '') {
    filters.collection = ''
    filters.visibility = ''
    return
  }
  if (k.startsWith('vis:')) {
    // 三档可见性是「跳出收藏夹」的权限维度：选中它就脱离当前收藏夹，看全站这一档。
    // 所以跟收藏夹互斥——同一时间只能站在一个维度上。再点一次同一档 = 回到全部。
    const v = k.slice(4)
    filters.visibility = filters.visibility === v ? '' : v
    filters.collection = ''
    return
  }
  // 选收藏夹就离开可见性维度，回到「这个夹里的全部项目」
  filters.collection = k
  filters.visibility = ''
}

function onCollectionsChanged() {
  loadCollections()
  load(true)
}

const exportHref = computed(
  () => '/api/export/bookmarks' + (filters.collection && filters.collection !== 'none'
    ? `?collection=${filters.collection}`
    : '')
)

function scheduleLoad() {
  clearTimeout(qTimer)
  qTimer = setTimeout(() => {
    page.value = 1
    load()
  }, 260)
}

watch(() => filters.q, scheduleLoad)
watch(
  () => [
    filters.agent,
    filters.kind,
    filters.visibility,
    filters.collection,
    filters.status,
    filters.tags.join(','),
    filters.sort,
    filters.order,
    size.value,
  ],
  () => {
    if (page.value !== 1) page.value = 1
    localStorage.setItem(
      'pv_filters',
      JSON.stringify({
        status: filters.status,
        visibility: filters.visibility,
        sort: filters.sort,
        order: filters.order,
        size: size.value,
        collection: filters.collection,
      })
    )
    load()
  }
)
watch(page, () => load())

function onSort(field) {
  if (filters.sort === field) filters.order = filters.order === 'desc' ? 'asc' : 'desc'
  else {
    filters.sort = field
    filters.order = 'desc'
  }
}

function toggleTag(name) {
  const i = filters.tags.indexOf(name)
  if (i >= 0) filters.tags.splice(i, 1)
  else filters.tags.push(name)
}

function resetFilters() {
  filters.q = ''
  filters.agent = ''
  filters.kind = ''
  filters.visibility = ''
  filters.collection = ''
  filters.status = 'online'
  filters.tags = []
  filters.sort = 'updated_at'
  filters.order = 'desc'
  page.value = 1
  load()
}

function toggleSelect(slug) {
  const i = selected.value.indexOf(slug)
  if (i >= 0) selected.value.splice(i, 1)
  else selected.value.push(slug)
}

function toggleAll(on) {
  selected.value = on ? data.items.map((i) => i.slug) : []
}

async function bulk(action, extra = {}, label = '') {
  if (!selected.value.length) return
  if (action === 'delete') {
    const ok = await confirmAction({
      title: `删除 ${selected.value.length} 个项目`,
      message: '所选项目及其全部文件将被永久删除，链接立即失效。',
      confirmText: '永久删除',
      danger: true,
    })
    if (!ok) return
  }
  try {
    const d = await api.post('/api/projects/bulk', { slugs: selected.value, action, ...extra })
    const extraBits = []
    if (d.expired) extraBits.push(`${d.expired} 个已到期（需先续期才会出现在门户）`)
    if (d.skipped) extraBits.push(`${d.skipped} 个无权操作已跳过`)
    toast(
      (label ? `${label} · ` : '') +
        `已处理 ${d.done} 个项目` +
        (extraBits.length ? `，${extraBits.join('，')}` : ''),
    )
    selected.value = []
    load()
    loadTrend()
  } catch (e) {
    toast(e.message || '操作失败', 'err')
  }
}

const VIS_LABEL = { portal: '门户可见', link: '持链接可见', private: '仅自己可见' }

async function bulkMove(cid) {
  if (!selected.value.length) return
  await bulk(
    'collection',
    { collection_id: cid || null },
    cid ? '已归入收藏夹' : '已移出收藏夹',
  )
  loadCollections()
}

async function bulkVisibility(v) {
  if (!selected.value.length) return
  if (v === 'private') {
    const ok = await confirmAction({
      title: `把 ${selected.value.length} 个项目改为「仅自己可见」`,
      message:
        '已发出去的链接对其他人立即失效（打开是 404），同时从访客门户下架。' +
        '只有你自己或管理员在登录状态下的浏览器能打开。',
      confirmText: '改为仅自己',
    })
    if (!ok) return
  }
  await bulk('visibility', { visibility: v }, VIS_LABEL[v])
}

function onCreated(d) {
  load()
  loadTrend()
  if (d?.slug) openSlug.value = d.slug
}

function onAction({ type, item }) {
  if (type === 'copied') toast(`已复制 ${item.slug} 的链接`)
  if (type === 'copy-failed') toast('复制失败，请手动复制', 'err')
}

function onDrawerChanged() {
  load(true)
  loadTrend()
  loadCollections()
}

function onImported(d) {
  load()
  loadTrend()
  loadCollections()
  if (d?.created) {
    filters.status = 'online'
  }
}

function tick() {
  now.value = Date.now() + offset
}

onMounted(() => {
  load()
  loadTrend()
  loadCollections()
  refreshTimer = setInterval(() => {
    if (document.hidden) return
    if (openSlug.value || uploadOpen.value) return
    load(true)
  }, 30000)
  tickTimer = setInterval(tick, 1000)
})

onBeforeUnmount(() => {
  clearInterval(refreshTimer)
  clearInterval(tickTimer)
  clearTimeout(qTimer)
})
</script>

<template>
  <header class="topbar">
    <h1>项目</h1>
    <span class="sub num">{{ fmtNum(data.total) }} 个</span>
    <div class="grow" />
    <div class="search">
      <Icon name="search" :size="13" />
      <input v-model="filters.q" class="field" placeholder="搜索名称 / slug / 说明" />
    </div>
    <button class="btn ghost icon" title="刷新" :disabled="loading" @click="load(true)">
      <Icon name="refresh" :size="14" />
    </button>
    <button class="btn ghost" title="导入浏览器书签（Chrome / Edge / Firefox）" @click="importOpen = true">
      <Icon name="download" :size="13" /> 导入书签
    </button>
    <a class="btn ghost" :href="exportHref" title="导出为书签 HTML，可被浏览器直接导入">
      <Icon name="external" :size="13" /> 导出
    </a>
    <button class="btn primary" @click="uploadOpen = true">
      <Icon name="plus" :size="13" /> 新建项目
    </button>
  </header>

  <div class="content">
    <div class="withrail">
      <CollectionTree
        :tree="colTree"
        :active="filters.collection"
        :visibility="filters.visibility"
        :loading="colLoading"
        @select="onCollectionPicked"
        @changed="onCollectionsChanged"
      />

      <div class="maincol">
        <StatStrip :stats="data.stats" :trend="trend" />

    <div class="toolbar">
      <select v-if="isAdmin" v-model="filters.agent" class="field" style="min-width: 116px">
        <option value="">全部成员</option>
        <option v-for="a in data.facets.agents" :key="a.username" :value="a.username">
          {{ a.display_name }} ({{ a.count }})
        </option>
      </select>

      <div class="seg">
        <button :class="{ on: filters.kind === '' }" @click="filters.kind = ''">全部类型</button>
        <button :class="{ on: filters.kind === 'static' }" @click="filters.kind = 'static'">静态站</button>
        <button :class="{ on: filters.kind === 'zip' }" @click="filters.kind = 'zip'">压缩包</button>
        <button :class="{ on: filters.kind === 'link' }" @click="filters.kind = 'link'">外链</button>
      </div>

      <!-- 可见性筛选：跟分类同一维度，选了它就跳出收藏夹，看全站这一档 -->
      <select
        v-model="filters.visibility"
        class="field"
        style="min-width: 112px"
        title="按可见性筛选（会跳出当前收藏夹）"
        @change="filters.collection = ''"
      >
        <option value="">全部可见性</option>
        <option value="portal">门户可见</option>
        <option value="link">持链接可见</option>
        <option value="private">仅自己可见</option>
      </select>

      <!-- 归类筛选：宽屏走左侧收藏夹栏，窄屏只剩这里，「未归类」得能一键筛出来 -->
      <select
        v-model="filters.collection"
        class="field colfallback"
        style="min-width: 118px"
        title="按收藏夹筛选"
        @change="filters.visibility = ''"
      >
        <option value="">全部归类</option>
        <option value="none">未归类</option>
        <option v-for="c in collectionOptions" :key="c.id" :value="String(c.id)">
          {{ c.label }}
        </option>
      </select>

      <select v-model="filters.status" class="field" style="min-width: 104px">
        <option value="online">仅在线</option>
        <option value="expired">已到期</option>
        <option value="permanent">永久项目</option>
        <option value="all">全部状态</option>
      </select>

      <div class="grow" style="flex: 1" />

      <select v-model="filters.sort" class="field" style="min-width: 116px">
        <option value="updated_at">按更新时间</option>
        <option value="created_at">按创建时间</option>
        <option value="views">按访问次数</option>
        <option value="expires_at">按到期时间</option>
        <option value="size_bytes">按体积</option>
      </select>
      <button class="btn icon" :title="filters.order === 'desc' ? '降序' : '升序'" @click="filters.order = filters.order === 'desc' ? 'asc' : 'desc'">
        {{ filters.order === 'desc' ? '↓' : '↑' }}
      </button>
      <select v-model.number="size" class="field" style="min-width: 86px">
        <option :value="20">20 / 页</option>
        <option :value="50">50 / 页</option>
        <option :value="100">100 / 页</option>
      </select>
      <button v-if="filters.q || filters.tags.length || filters.agent || filters.kind || filters.visibility" class="btn ghost sm" @click="resetFilters">
        清除筛选
      </button>
    </div>

    <div class="chipbar">
      <button
        v-for="t in tagsForBar"
        :key="t.name"
        class="chip"
        :class="{ on: filters.tags.includes(t.name) }"
        @click="toggleTag(t.name)"
      >
        {{ t.name }}<span class="n">{{ t.count }}</span>
      </button>
      <span v-if="!tagsForBar.length" class="dim" style="font-size: 11.5px; padding: 3px 0">
        还没有标签 · 上传时或打开项目详情可添加
      </span>
      <span v-if="filters.tags.length" class="dim" style="font-size: 11.5px; padding: 3px 0; margin-left: auto">
        已选 {{ filters.tags.length }} 个标签
      </span>
    </div>

    <div v-if="err" class="panel" style="padding: 12px 14px; margin-bottom: 12px; color: var(--danger)">
      {{ err }}
      <button class="linkbtn" style="margin-left: 8px" @click="load()">重试</button>
    </div>

    <ProjectTable
      :items="data.items"
      :loading="loading"
      :sort="filters.sort"
      :order="filters.order"
      :now="now"
      :selected="selected"
      @sort="onSort"
      @open="(p) => (openSlug = p.slug)"
      @toggle="toggleSelect"
      @toggle-all="toggleAll"
      @action="onAction"
    />

    <div
      style="display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 12px; padding: 0 2px"
    >
      <span class="dim" style="font-size: 12px">
        共 {{ fmtNum(data.total) }} 条 · 第 {{ page }} / {{ totalPages }} 页
        <span v-if="loading" style="margin-left: 6px">读取中…</span>
      </span>
      <div style="display: flex; gap: 6px">
        <button class="btn sm" :disabled="page <= 1" @click="page--">上一页</button>
        <button class="btn sm" :disabled="page >= totalPages" @click="page++">下一页</button>
      </div>
    </div>
      </div>
    </div>
  </div>

  <div v-if="selected.length" class="bulkbar">
    <span>已选 {{ selected.length }} 项</span>
    <span class="bulksep" aria-hidden="true"></span>
    <em class="bulklab">门户可见性</em>
    <button class="btn sm vis-p" title="出现在访客门户列表里" @click="bulkVisibility('portal')">
      门户可见
    </button>
    <button class="btn sm" title="不出现在门户，但知道链接的人能打开" @click="bulkVisibility('link')">
      持链接
    </button>
    <button class="btn sm" title="只有你和管理员登录后能打开（外部一律 404）" @click="bulkVisibility('private')">
      仅自己
    </button>
    <span class="bulksep" aria-hidden="true"></span>
    <select
      class="field sm"
      style="min-width: 118px; height: 26px"
      title="批量归入收藏夹"
      @change="bulkMove($event.target.value); $event.target.value = ''"
    >
      <option value="">移到收藏夹…</option>
      <option value="none">移出收藏夹</option>
      <!-- 平铺而不是 optgroup：optgroup 的组名会和夹名重复显示一次，看着像同一个夹出现了两层 -->
      <template v-for="node in colTree.items" :key="node.id">
        <option :value="node.id">{{ node.name }}</option>
        <option v-for="kid in node.children || []" :key="kid.id" :value="kid.id">
          　└ {{ kid.name }}
        </option>
      </template>
    </select>
    <span class="bulksep" aria-hidden="true"></span>
    <button class="btn sm" @click="bulk('extend', { hours: 24 })">+24 小时</button>
    <button class="btn sm" @click="bulk('permanent')">设为永久</button>
    <button class="btn sm" @click="bulk('allow_download')">开放下载</button>
    <button class="btn sm danger" @click="bulk('delete')">删除</button>
    <button class="btn sm" @click="selected = []">取消</button>
  </div>

  <ProjectDrawer
    v-if="openSlug"
    :key="openSlug"
    :slug="openSlug"
    :now="now"
    @close="openSlug = ''"
    @changed="onDrawerChanged"
  />

  <UploadDialog
    v-if="uploadOpen"
    :collections="colTree"
    @close="uploadOpen = false"
    @created="onCreated"
  />

  <ImportDialog
    v-if="importOpen"
    :collections="colTree"
    :default-collection="filters.collection"
    @close="importOpen = false"
    @imported="onImported"
  />
</template>

<style scoped>
@media (max-width: 900px) {
  .search { max-width: 100%; flex: 1 1 140px; }
}
</style>
