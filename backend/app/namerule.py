"""项目名长度规则：短一点，卡片上才看得全。

按**显示宽度**数，不按字符个数：一个中文字符算 1，一个半角字符（英文字母、数字、
空格、标点）算 0.5。于是 10 个中文字符 ≈ 20 个英文字符，肉眼看过去差不多长。

超长时两条路，别一刀切：

* **顺手给的**标题（上传时从文件名/目录名推的、外链从 URL 推的、CLI 传的模糊名字）
  → 静默截断。为了一个名字把人拦在上传门外不值当，返回体里给的是真实落库的名字。
* **用户明确写的**标题（改名 PATCH）→ 422 让他改。偷偷改掉别人刚敲的名字更讨厌。

前端 `frontend/src/namerule.js` 是同一套算法的镜像，用于边打字边提示；后端永远是裁判。
"""
from __future__ import annotations

import unicodedata

# 服务端硬上限：24 个中文字符（≈48 个半角字符）。
# 「10 字以内」只是 skill 层面的建议，服务端只兜底防止离谱长名。
MAX_WIDTH = 24.0

# 半角字符的权重
NARROW = 0.5


def char_width(ch: str) -> float:
    """单个字符占的宽度：全角/宽字符 1，其余 0.5。"""
    return 1.0 if unicodedata.east_asian_width(ch) in ("W", "F") else NARROW


def width(text: str) -> float:
    """整串的显示宽度。"""
    return sum(char_width(c) for c in str(text or ""))


def too_long(text: str, max_width: float = MAX_WIDTH) -> bool:
    return width(text) > max_width + 1e-9


def fmt(w: float) -> str:
    """12.0 → '12'，9.5 → '9.5'。"""
    return f"{w:.1f}".rstrip("0").rstrip(".")


def rules() -> dict:
    """给 /api/meta 用的规则描述，前端据此做即时提示。"""
    return {
        "max_width": MAX_WIDTH,
        "max_cjk": int(MAX_WIDTH),
        "max_narrow": int(MAX_WIDTH / NARROW),
        "hint": f"最多 {int(MAX_WIDTH)} 个中文字符（约 {int(MAX_WIDTH / NARROW)} 个英文字符）",
    }


def clamp(text: str, max_width: float = MAX_WIDTH) -> str:
    """截到宽度上限内（不会把一个字符劈成两半），去掉尾部空格与标点。"""
    s = str(text or "").strip()
    if not too_long(s, max_width):
        return s
    out: list[str] = []
    used = 0.0
    for ch in s:
        w = char_width(ch)
        if used + w > max_width + 1e-9:
            break
        out.append(ch)
        used += w
    return "".join(out).rstrip(" \u3000-—_·,，.。:：;；|/\\")


def check(text: str, max_width: float = MAX_WIDTH) -> str | None:
    """超长返回错误文案，合规返回 None。"""
    s = str(text or "").strip()
    if too_long(s, max_width):
        return (f"项目名最多 {int(max_width)} 个中文字符"
                f"（约 {int(max_width / NARROW)} 个英文字符），当前 {fmt(width(s))} 个")
    return None
