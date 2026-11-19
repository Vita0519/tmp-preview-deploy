import { reactive } from 'vue'

export const store = reactive({
  user: null,
  version: '',
  siteTitle: '临时预览站',
  toasts: [],
  confirm: null,
  mobileNav: false,
  // 标签规则由站点设置决定（管理员可调小），启动时从 /api/meta 同步过来。
  // 初值只是兜底，别写死 6 就当准了——否则界面允许填 6 个、后端按 2 个打回。
  tagRules: { max_per_project: 6, max_len: 12 },
  // 署名信息由 /api/meta 下发（AGPL-3.0 §7(b) 要求保留，别在前端另抄一份）
  project: {
    name: 'tmp-preview',
    url: 'https://github.com/Vita0519/tmp-preview-deploy',
    author: 'Vita0519',
    license: 'AGPL-3.0-only',
  },
})

/** 用 /api/meta 下发的实际规则覆盖前端兜底值 */
export function applyTagRules(raw) {
  if (!raw) return
  const n = Number(raw.max_per_project)
  const len = Number(raw.max_len)
  if (n > 0) store.tagRules.max_per_project = n
  if (len > 0) store.tagRules.max_len = len
}

let seq = 0
export function toast(message, type = 'ok', ttl = 2600) {
  const id = ++seq
  store.toasts.push({ id, message, type })
  setTimeout(() => {
    const i = store.toasts.findIndex((t) => t.id === id)
    if (i >= 0) store.toasts.splice(i, 1)
  }, ttl)
}

let confirmResolver = null
export function confirmAction(opts) {
  store.confirm = {
    title: opts.title || '确认操作',
    message: opts.message || '',
    confirmText: opts.confirmText || '确认',
    cancelText: opts.cancelText || '取消',
    danger: !!opts.danger,
  }
  return new Promise((resolve) => {
    confirmResolver = resolve
  })
}

export function resolveConfirm(value) {
  store.confirm = null
  if (confirmResolver) {
    confirmResolver(value)
    confirmResolver = null
  }
}
