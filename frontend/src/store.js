import { reactive } from 'vue'

export const store = reactive({
  user: null,
  siteTitle: '临时预览站',
  toasts: [],
  confirm: null,
  mobileNav: false,
})

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
