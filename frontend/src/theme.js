/**
 * 主题引擎（客户端）：与 backend/app/theme.py 同一套派生公式。
 *
 * 主题插件 = 一整套语义令牌（theme.json 的 vars），由后端随 /api/meta、
 * /api/settings 下发；这里负责把它逐个写进 :root。
 * `--brand-*` 一族不进清单——它们由用户主色实时派生（本文件 palette()），
 * 派生的对比度尺子按主题明暗模式各有一把：深底不够亮就提白，浅底不够深就压黑。
 */

export const PRESETS = [
  { name: '电光蓝', value: '#2563eb' },
  { name: '翠绿', value: '#10b981' },
  { name: '靛蓝', value: '#6366f1' },
  { name: '深青', value: '#0ea5e9' },
  { name: '藏紫', value: '#8b5cf6' },
  { name: '玫红', value: '#f43f5e' },
  { name: '砖红', value: '#f97316' },
  { name: '石板', value: '#94a3b8' },
]

export const DEFAULT_ACCENT = '#2563eb'

/** 两种画布参照（与内置主题 noir / ivory 的 --bg 一致） */
export const CANVAS_DARK = '#0b0d10'
export const CANVAS_LIGHT = '#f6f7f5'

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

export const MIN_CONTRAST = 3.0

/** 往 target 方向二分，直到 c 对 canvas 的对比度达标（色相不动） */
function shiftToward(c, target, canvas, minimum) {
  let lo = 0
  let hi = 0.95
  for (let i = 0; i < 18; i += 1) {
    const mid = (lo + hi) / 2
    if (contrast(mix(c, target, mid), canvas) >= minimum) hi = mid
    else lo = mid
  }
  return mix(c, target, hi)
}

export function readable(brand, mode = 'dark') {
  let c = normalize(brand)
  if (contrast(c, '#ffffff') < MIN_CONTRAST) {
    c = shiftToward(c, '#000000', '#ffffff', MIN_CONTRAST)
  }
  const canvas = mode === 'dark' ? CANVAS_DARK : CANVAS_LIGHT
  if (contrast(c, canvas) < MIN_CONTRAST) {
    c = shiftToward(c, mode === 'dark' ? '#ffffff' : '#000000', canvas, MIN_CONTRAST)
  }
  return c
}

/**
 * 主色 + 主题明暗模式 → 品牌色族。
 * hover：深底往白提（亮起 = 可点击的暗示），浅底往黑压（classic 行为）。
 */
export function palette(accent, mode = 'dark') {
  const raw = normalize(accent)
  const brand = readable(raw, mode)
  const [r, g, b] = rgb(brand)
  const dark = mode === 'dark'
  return {
    accent: brand,
    raw,
    adjusted: brand !== raw,
    hover: dark ? mix(brand, '#ffffff', 0.1) : mix(brand, '#000000', 0.12),
    soft: `rgba(${r},${g},${b},${dark ? 0.14 : 0.08})`,
    line: `rgba(${r},${g},${b},${dark ? 0.38 : 0.22})`,
    deep: mix(brand, '#000000', 0.32),
    light: mix(brand, '#ffffff', dark ? 0.3 : 0.18),
    rgb: `${r},${g},${b}`,
  }
}

const BRAND_VARS = [
  '--brand',
  '--brand-hover',
  '--brand-soft',
  '--brand-line',
  '--brand-deep',
  '--brand-light',
  '--brand-rgb',
]

/**
 * 把主题写进 :root。
 * p = { accent, mode?, vars? }：vars 是主题插件的完整语义令牌（缺省就只换主色）。
 */
export function applyPalette(p) {
  const board = p && (p.vars || p.accent) ? p : {}
  const root = document.documentElement
  const mode = board.mode === 'light' ? 'light' : 'dark'
  const v = board.vars || {}
  Object.keys(v).forEach((k) => {
    if (!k.startsWith('--') || BRAND_VARS.includes(k)) return
    root.style.setProperty(k, v[k])
  })
  const b = palette(board.accent || DEFAULT_ACCENT, mode)
  root.style.setProperty('--brand', b.accent)
  root.style.setProperty('--brand-hover', b.hover)
  root.style.setProperty('--brand-soft', b.soft)
  root.style.setProperty('--brand-line', b.line)
  root.style.setProperty('--brand-deep', b.deep)
  root.style.setProperty('--brand-light', b.light)
  root.style.setProperty('--brand-rgb', b.rgb)
  // 登录页/预览壳的防白闪：记下画布底色，index.html 的内联脚本下次直接用
  try {
    if (v['--bg']) localStorage.setItem('pv_bg', v['--bg'])
    if (v['--scheme']) localStorage.setItem('pv_scheme', v['--scheme'])
  } catch {}
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', b.accent)
}

export function applyAccent(accent) {
  applyPalette({ accent })
}

/** 设置页「点一下看效果」：在当前主题令牌之上换主色实时预览 */
export function previewAccent(accent, base) {
  applyPalette({ ...(base || {}), accent })
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
