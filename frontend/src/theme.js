/**
 * 主题：与 backend/app/theme.py 同一套派生公式。
 *
 * 配色按 60-30-10 拆：60% 画布（--bg 几个）、30% 容器（--surface）、10% 主色（--brand）。
 * 所以「换主题」要同时换主色和中性色画布，这里两边都算。
 * 后端会在 /api/meta、/api/settings 里直接下发整份色板，这里只在设置页实时预览时用。
 */

export const PRESETS = [
  { name: '墨绿', value: '#0f766e' },
  { name: '靛蓝', value: '#3b5bdb' },
  { name: '深青', value: '#0b7285' },
  { name: '藏紫', value: '#6741d9' },
  { name: '砖红', value: '#c2410c' },
  { name: '玫红', value: '#be1250' },
  { name: '赭石', value: '#a16207' },
  { name: '石板', value: '#475569' },
]

/** 本地兜底的一套（后端不可用时设置页也不至于空白）；实际以 /api/settings 下发为准 */
export const FALLBACK_SERIES = [
  {
    key: 'classic', name: '经典墨绿', desc: '暖灰画布 + 墨绿强调，克制耐看', use: '通用后台',
    accent: '#0f766e', neutral: { bg: '#f6f7f5', ink: '#14161a', ink2: '#4a5057' },
  },
]

export const DEFAULT_ACCENT = '#0f766e'

const HEX = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i

export function normalize(raw) {
  let s = String(raw || '').trim().toLowerCase()
  if (!s) return DEFAULT_ACCENT
  if (!s.startsWith('#')) s = `#${s}`
  if (!HEX.test(s)) return DEFAULT_ACCENT
  if (s.length === 4) s = `#${s[1]}${s[1]}${s[2]}${s[2]}${s[3]}${s[3]}`
  return s
}

function rgb(hex) {
  const h = normalize(hex).slice(1)
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]
}

function hexOf(triple) {
  return `#${triple
    .map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0'))
    .join('')}`
}

/** a 与 b 按 t（b 的占比）混合 */
export function mix(a, b, t) {
  const ra = rgb(a)
  const rb = rgb(b)
  return hexOf(ra.map((v, i) => v * (1 - t) + rb[i] * t))
}

function lum(c) {
  const ch = (v) => {
    v /= 255
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
  }
  const [r, g, b] = rgb(c)
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)
}

export function contrast(a, b) {
  const la = lum(a)
  const lb = lum(b)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}

/** 主色要同时当按钮底和「浅底上的文字」，跟白底对比度不够就等比压深（色相不动） */
export const MIN_CONTRAST = 3.0

export function readable(brand) {
  const c = normalize(brand)
  if (contrast(c, '#ffffff') >= MIN_CONTRAST) return c
  let lo = 0
  let hi = 0.88
  for (let i = 0; i < 18; i += 1) {
    const mid = (lo + hi) / 2
    if (contrast(mix(c, '#000000', mid), '#ffffff') >= MIN_CONTRAST) hi = mid
    else lo = mid
  }
  return mix(c, '#000000', hi)
}

/**
 * 系列 → 整套中性色。
 * 只给 bg / ink / ink2 三个锚点，其余 8 个混出来（与 theme.py 的 neutral_of 一一对应）。
 */
export function neutralOf(s) {
  const bg = normalize(s?.bg || s?.neutral?.bg || '#f6f7f5')
  const ink = normalize(s?.ink || s?.neutral?.ink || '#14161a')
  const ink2 = normalize(s?.ink2 || s?.neutral?.['ink-2'] || '#4a5057')
  return {
    bg,
    'bg-2': mix('#ffffff', bg, 0.42),
    'bg-deep': mix(bg, ink, 0.025),
    'surface-2': mix('#ffffff', bg, 0.48),
    'surface-3': mix(bg, ink, 0.012),
    ink,
    'ink-2': ink2,
    'ink-3': mix(ink2, bg, 0.28),
    'ink-4': mix(ink2, bg, 0.55),
    line: mix(bg, ink, 0.065),
    'line-2': mix(bg, ink, 0.14),
    'ink-rgb': rgb(ink).join(','),
    'bg-rgb': rgb(bg).join(','),
  }
}

export function palette(accent, series) {
  const raw = normalize(accent)
  const brand = readable(raw)
  const [r, g, b] = rgb(brand)
  return {
    accent: brand,
    raw,
    adjusted: brand !== raw,
    hover: mix(brand, '#000000', 0.12),
    soft: mix('#ffffff', brand, 0.07),
    line: `rgba(${r},${g},${b},.22)`,
    deep: mix(brand, '#000000', 0.32),
    light: mix(brand, '#ffffff', 0.18),
    rgb: `${r},${g},${b}`,
    neutral: series ? neutralOf(series) : null,
  }
}

/** 把色板写进 :root，控制台全局立刻变色（主色 + 中性色画布） */
export function applyPalette(p) {
  const board = p && p.accent ? p : palette(p)
  const root = document.documentElement
  root.style.setProperty('--brand', board.accent)
  root.style.setProperty('--brand-hover', board.hover)
  root.style.setProperty('--brand-soft', board.soft)
  root.style.setProperty('--brand-line', board.line)
  root.style.setProperty('--brand-deep', board.deep)
  root.style.setProperty('--brand-light', board.light)
  root.style.setProperty('--brand-rgb', board.rgb)
  const n = board.neutral
  if (n) {
    Object.keys(n).forEach((k) => {
      if (k === 'ink2') return
      root.style.setProperty(`--${k}`, n[k])
    })
    // 阴影也跟着正文色走，免得冷底上挂一圈暖黑影子
    const [ir, ig, ib] = String(n['ink-rgb'] || '20,22,26').split(',')
    root.style.setProperty('--shadow-1', `0 1px 2px rgba(${ir},${ig},${ib},0.04)`)
    root.style.setProperty(
      '--shadow-2',
      `0 1px 2px rgba(${ir},${ig},${ib},0.04), 0 12px 24px -18px rgba(${ir},${ig},${ib},0.4)`
    )
    root.style.setProperty(
      '--shadow-pop',
      `0 18px 48px -24px rgba(${ir},${ig},${ib},0.45), 0 2px 6px rgba(${ir},${ig},${ib},0.06)`
    )
  }
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', board.accent)
}

export function applyAccent(accent) {
  applyPalette(palette(accent))
}

/** 设置页「点一下看效果」：主色 + 该系列的中性色一起套 */
export function previewSeries(series) {
  applyPalette({ ...palette(series.accent, series), neutral: neutralOf(series) })
}

/** 站点图标：换成自定义图标，或回落到内置那套 */
export function applySiteIcon(info) {
  const url = (info && info.url) || ''
  document.querySelectorAll('link[rel="icon"], link[rel="apple-touch-icon"]').forEach((n) => n.remove())
  const add = (rel, href, sizes) => {
    const l = document.createElement('link')
    l.rel = rel
    l.href = href
    if (sizes) l.sizes = sizes
    document.head.appendChild(l)
  }
  if (url) {
    add('icon', url)
    add('apple-touch-icon', url)
    return
  }
  add('icon', '/favicon.svg')
  add('icon', '/favicon.ico', '16x16 32x32 48x48')
  add('apple-touch-icon', '/apple-touch-icon.png')
}
