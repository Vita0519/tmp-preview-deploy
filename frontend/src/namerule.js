/** 项目名规则的前端镜像：跟 backend/app/namerule.py 保持一致。
 *
 * 按「显示宽度」数，不按字符个数：中文 1、半角 0.5，
 * 所以 10 个中文字符 ≈ 20 个英文字符。后端是最终裁判（改名超长会 422），
 * 这里只负责边打字边提示，别让人敲完才被打回。
 */

export const TITLE_RULE = { max_width: 10, max_cjk: 10, max_narrow: 20 }

// Unicode East Asian Width 里的 W / F 区间，跟 Python 侧 east_asian_width 对齐
const WIDE =
  /[\u1100-\u115F\u2E80-\u303E\u3041-\u33FF\u3400-\u4DBF\u4E00-\u9FFF\uA000-\uA4CF\uA960-\uA97F\uAC00-\uD7A3\uF900-\uFAFF\uFE10-\uFE19\uFE30-\uFE6F\uFF00-\uFF60\uFFE0-\uFFE6]/

export function charWidth(ch) {
  return WIDE.test(ch) ? 1 : 0.5
}

/** 整串的显示宽度（中文字符算 1，英文/数字/空格/标点算 0.5） */
export function titleWidth(text) {
  let w = 0
  for (const ch of String(text || '')) w += charWidth(ch)
  return w
}

export function fmtWidth(w) {
  return Number(w.toFixed(1)).toString()
}

/** 超长返回错误文案，合规返回空串 */
export function titleError(text, rule = TITLE_RULE) {
  const max = rule.max_width ?? TITLE_RULE.max_width
  const w = titleWidth(text)
  if (w <= max) return ''
  return `项目名最多 ${max} 个中文字符（约 ${max * 2} 个英文字符），当前 ${fmtWidth(w)} 个`
}

/** 截到上限内（不劈坏字符，去掉尾部空格与标点），提交前兜底用 */
export function clampTitle(text, rule = TITLE_RULE) {
  const max = rule.max_width ?? TITLE_RULE.max_width
  const s = String(text || '').trim()
  if (titleWidth(s) <= max) return s
  let out = ''
  let used = 0
  for (const ch of s) {
    const w = charWidth(ch)
    if (used + w > max) break
    out += ch
    used += w
  }
  return out.replace(/[\s\u3000\-—_·,，.。:：;；|/\\]+$/u, '')
}
