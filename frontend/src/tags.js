/** 标签规则的前端镜像：跟 backend/app/tagspec.py 保持一致。
 *
 * 后端才是最终裁判（不合法会 422），这里只负责「边打字边提示」，别让人填完才被打回。
 */

export const TAG_RULES = { max_per_project: 6, max_len: 12 }

// \w 在 JS 正则里只认 ASCII，中文得单独列出来
const ALLOWED = /^[\p{L}\p{N}_+#.-]+$/u
const SEP = /[,，、;；\s]+/

export const allowedText = '中英文、数字和 + # . - _'

export function normalizeTag(raw) {
  return String(raw || '')
    .normalize('NFKC') // 全角转半角
    .trim()
    .toLowerCase()
}

/** 逗号/顿号/分号/空格分隔的字符串（或数组）→ 归一化后的标签数组（去重、保序） */
export function splitTags(raw) {
  if (raw == null || raw === '') return []
  const parts = Array.isArray(raw) ? raw : String(raw).split(SEP)
  const out = []
  for (const p of parts) {
    const name = normalizeTag(p)
    if (name && !out.includes(name)) out.push(name)
  }
  return out
}

/** 校验一段输入，返回 { tags, error }：error 为空串表示可以提交 */
export function checkTags(raw, rules = TAG_RULES) {
  const tags = splitTags(raw)
  const maxLen = rules.max_len ?? TAG_RULES.max_len
  const maxCount = rules.max_per_project ?? TAG_RULES.max_per_project
  for (const name of tags) {
    if ([...name].length > maxLen) return { tags, error: `标签「${name}」太长了：最多 ${maxLen} 个字` }
    if (!ALLOWED.test(name)) return { tags, error: `标签「${name}」含有不允许的字符：只能${allowedText}` }
  }
  if (tags.length > maxCount) return { tags, error: `每个项目最多 ${maxCount} 个标签，你填了 ${tags.length} 个` }
  return { tags, error: '' }
}

/** 单个标签是否合规（抽屉里一个个加时用） */
export function checkOneTag(name, rules = TAG_RULES) {
  const { tags, error } = checkTags(name, rules)
  if (error) return { tag: '', error }
  return { tag: tags[0] || '', error: '' }
}
