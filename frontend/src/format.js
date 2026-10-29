export function fmtBytes(n) {
  n = Number(n) || 0
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`
  return `${(n / 1024 ** 3).toFixed(2)} GB`
}

export function fmtNum(n) {
  n = Number(n) || 0
  if (n < 1000) return String(n)
  if (n < 1e6) return `${(n / 1000).toFixed(n < 1e4 ? 1 : 0)}k`
  return `${(n / 1e6).toFixed(1)}M`
}

const pad = (n) => (n < 10 ? `0${n}` : String(n))

export function fmtRemain(ms) {
  if (ms === null || ms === undefined) return '永久'
  if (ms <= 0) return '已到期'
  const s = Math.floor(ms / 1000)
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (d > 0) return `${d}天${h}时`
  if (h > 0) return `${h}:${pad(m)}:${pad(sec)}`
  return `${pad(m)}:${pad(sec)}`
}

export function fmtDate(ts) {
  if (!ts) return '—'
  const d = new Date(ts)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function fmtDay(day) {
  if (!day) return ''
  return day.slice(5)
}

export function relTime(ts) {
  if (!ts) return '—'
  const diff = Date.now() - ts
  if (diff < 60e3) return '刚刚'
  if (diff < 3600e3) return `${Math.floor(diff / 60e3)} 分钟前`
  if (diff < 86400e3) return `${Math.floor(diff / 3600e3)} 小时前`
  if (diff < 7 * 86400e3) return `${Math.floor(diff / 86400e3)} 天前`
  return fmtDate(ts).slice(5, 10)
}

export function hoursLabel(h) {
  if (h === null || h === undefined) return '永久'
  if (h === 0) return '永久'
  if (h < 1) return `${Math.round(h * 60)} 分钟`
  if (h < 24) return `${h} 小时`
  return `${(h / 24).toFixed(h % 24 === 0 ? 0 : 1)} 天`
}

export function typeLabel(kind) {
  return { static: '静态站', zip: '压缩包', link: '外链' }[kind] || kind
}

export function initial(text) {
  const t = (text || '').trim()
  return t ? t.slice(0, 1).toUpperCase() : 'P'
}
