/**
 * 主题色：与 backend/app/theme.py 同一套派生公式。
 * 后端会在 /api/meta 里直接下发整份色板，这里只在「设置页拖色盘实时预览」时用得到。
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

export function palette(accent) {
  const brand = normalize(accent)
  const [r, g, b] = rgb(brand)
  return {
    accent: brand,
    hover: mix(brand, '#000000', 0.12),
    soft: mix('#ffffff', brand, 0.07),
    line: `rgba(${r},${g},${b},.22)`,
    deep: mix(brand, '#000000', 0.32),
    light: mix(brand, '#ffffff', 0.18),
    rgb: `${r},${g},${b}`,
  }
}

/** 把色板写进 :root，控制台全局立刻变色 */
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
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', board.accent)
}

export function applyAccent(accent) {
  applyPalette(palette(accent))
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
