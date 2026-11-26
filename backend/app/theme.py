"""主题插件引擎：主题 = 一个 theme.json 语义令牌清单（声明式，无代码执行）。

设计：
- 每套主题（内置或商店安装）定义一整套 CSS 语义令牌（画布 / 容器 / 文字 / 描边 /
  阴影 / 弹层……约 30 个 --var），覆盖在对应明暗基底的变量之上；只写部分键也可以，
  缺省键回落到该模式的基底（noir / ivory）。
- `--brand-*` 一族永远不进清单：它们由用户主色（theme_accent）实时派生，
  派生公式按主题明暗模式各有一把尺（深底提亮 / 浅底压深）。
- 商店：给定 GitHub 仓库（owner/repo、仓库 URL、/tree/ 深链均可），用 GitHub API
  枚举仓库里的 theme.json，逐个取回（raw.githubusercontent.com，jsDelivr 兜底），
  校验后落盘到 <DATA_DIR>/themes/<id>/theme.json。

清单格式见 examples/theme-plugin/README.md。
"""
from __future__ import annotations

import base64
import json
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import config

DEFAULT = "#2563eb"

# 校正主色用的两种画布参照（与内置主题 --bg 一致）
DARK_CANVAS = "#0b0d10"
LIGHT_CANVAS = "#f6f7f5"

BUILTIN_DIR = Path(__file__).resolve().parent / "builtin_themes"
PLUGINS_DIR = Path(config.DATA_DIR) / "themes"

MANIFEST_MAX = 64 * 1024
PREVIEW_MAX = 256 * 1024

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
VAR_KEY_RE = re.compile(r"^--[a-z0-9-]{2,40}$")
# 主色派生族：插件不许带，永远由 theme_accent 现算
BRAND_KEYS = {
    "--brand", "--brand-hover", "--brand-soft", "--brand-line",
    "--brand-deep", "--brand-light", "--brand-rgb",
}

# 可选布局令牌（v2.4）：倒计时条 / 卡片圆角 / 数字字体。缺省值写在页面 CSS 的 var() 回退里，
# 老主题不写就和以前完全一样。长度类只收 0-40px 的 px 值，防止把页面撑坏。
_PX = re.compile(r"^(0|\d{1,2}(\.\d)?px)$")
LAYOUT_KEYS = {
    "--track-h": re.compile(r"^([1-9]|1[0-2])(\.\d)?px$"),
    "--track-seg": _PX,
    "--track-gap": _PX,
    "--track-radius": _PX,
    "--card-radius": _PX,
    "--track-bg": re.compile(r"^[#a-z0-9(),.%\s-]{1,80}$", re.I),
    "--track-glow": re.compile(r"^(none|[#a-z0-9(),.%\s-]{1,120})$", re.I),
    "--font-num": re.compile(r"^[a-z0-9\s,\"'-]{1,160}$", re.I),
}

PRESETS = [
    ("电光蓝", "#2563eb"),
    ("翠绿", "#10b981"),
    ("靛蓝", "#6366f1"),
    ("深青", "#0ea5e9"),
    ("藏紫", "#8b5cf6"),
    ("玫红", "#f43f5e"),
    ("砖红", "#f97316"),
    ("石板", "#94a3b8"),
]


# ---------------------------------------------------------------- 色值工具
def normalize(raw: object) -> str:
    """把 #abc / #aabbcc / 带空格的输入收敛成 #aabbcc；非法就回默认。"""
    s = str(raw or "").strip().lower()
    if not s.startswith("#"):
        s = "#" + s
    body = s[1:]
    if len(body) == 3 and all(c in "0123456789abcdef" for c in body):
        body = "".join(c * 2 for c in body)
    if len(body) == 6 and all(c in "0123456789abcdef" for c in body):
        return "#" + body
    return DEFAULT


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = normalize(hex_color)[1:]
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in rgb)


def mix(a: str, b: str, t: float) -> str:
    """a 与 b 按 t（b 的占比）混合。"""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(ra[i] * (1 - t) + rb[i] * t for i in range(3)))


def _lum(c: str) -> float:
    def ch(v: float) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = _rgb(c)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


MIN_CONTRAST = 3.0


def _shift_toward(c: str, target: str, canvas: str, minimum: float) -> str:
    """往 target 方向二分，直到 c 对 canvas 的对比度达标（色相不动）。"""
    lo, hi = 0.0, 0.95
    for _ in range(18):
        mid = (lo + hi) / 2
        if contrast(mix(c, target, mid), canvas) >= minimum:
            hi = mid
        else:
            lo = mid
    return mix(c, target, hi)


def readable(brand: str, mode: str = "dark") -> str:
    """主色两头都要撑住：白字压上去（主按钮）够、所在画布上放文字/徽标也要够。

    深色主题：对白不够就压黑，对深画布不够就提白（先压后提不会打架）。
    浅色主题：两个约束都往黑压，方向一致。
    """
    c = normalize(brand)
    if contrast(c, "#ffffff") < MIN_CONTRAST:
        c = _shift_toward(c, "#000000", "#ffffff", MIN_CONTRAST)
    canvas = DARK_CANVAS if mode == "dark" else LIGHT_CANVAS
    if contrast(c, canvas) < MIN_CONTRAST:
        target = "#ffffff" if mode == "dark" else "#000000"
        c = _shift_toward(c, target, canvas, MIN_CONTRAST)
    return c


# ---------------------------------------------------------------- 清单读写
def _manifest_from_raw(raw: bytes, source: str) -> dict:
    """解析并校验一份主题清单；不合法直接抛 ValueError，消息面向插件作者。"""
    if len(raw) > MANIFEST_MAX:
        raise ValueError(f"theme.json 超过 {MANIFEST_MAX // 1024}KB 上限")
    try:
        m = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"theme.json 不是合法 JSON：{e}") from e
    if not isinstance(m, dict):
        raise ValueError("theme.json 顶层必须是对象")
    pid = str(m.get("id") or "").strip().lower()
    if not ID_RE.match(pid):
        raise ValueError("id 必须是 2-40 位小写字母/数字/连字符，且以字母或数字开头")
    name = str(m.get("name") or "").strip()
    if not name:
        raise ValueError("缺少 name")
    mode = str(m.get("mode") or "dark").strip().lower()
    if mode not in ("dark", "light"):
        raise ValueError("mode 只能是 dark 或 light")
    vars_in = m.get("vars") or {}
    if not isinstance(vars_in, dict):
        raise ValueError("vars 必须是对象")
    cleaned: dict[str, str] = {}
    for k, v in vars_in.items():
        key = str(k).strip().lower()
        if key in BRAND_KEYS:
            continue  # 主色派生族一律忽略：accent 永远赢
        if not VAR_KEY_RE.match(key):
            raise ValueError(f"非法变量名：{k!r}（应为 --xx-yy 形式）")
        val = str(v).strip()
        if not val or len(val) > 500:
            raise ValueError(f"变量 {key} 的值必须是 1-500 字符")
        if any(ch in val for ch in "{};<>"):
            raise ValueError(f"变量 {key} 的值不能包含 {{ }} ; < >")
        rule = LAYOUT_KEYS.get(key)
        if rule and not rule.match(val):
            raise ValueError(f"变量 {key} 的值不合法：{val!r}")
        cleaned[key] = val
    accent = normalize(m.get("default_accent") or DEFAULT)
    accents = []
    for a in (m.get("accents") or [])[:12]:
        na = normalize(a)
        if na not in accents:
            accents.append(na)
    if accent not in accents:
        accents.insert(0, accent)
    return {
        "id": pid,
        "name": name[:40],
        "version": str(m.get("version") or "1.0.0")[:20],
        "author": str(m.get("author") or "").strip()[:60],
        "homepage": str(m.get("homepage") or "").strip()[:200],
        "desc": str(m.get("desc") or "").strip()[:200],
        "mode": mode,
        "default_accent": accent,
        "accents": accents,
        "vars": cleaned,
        "source": source,
    }


def _load_json_file(p: Path) -> dict | None:
    try:
        return _manifest_from_raw(p.read_bytes(), "builtin")
    except Exception:  # noqa: BLE001 - 单个坏清单不要拖垮整个主题系统
        return None


def builtin_manifests() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if BUILTIN_DIR.is_dir():
        for p in sorted(BUILTIN_DIR.glob("*.json")):
            m = _load_json_file(p)
            if m:
                out[m["id"]] = m
    return out


def installed_manifests() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if PLUGINS_DIR.is_dir():
        for d in sorted(PLUGINS_DIR.iterdir()):
            f = d / "theme.json"
            if d.is_dir() and f.is_file():
                m = _load_json_file(f)
                if m:
                    m["builtin"] = False
                    out[m["id"]] = m
    return out


def all_manifests() -> dict[str, dict]:
    """内置 + 已安装；同 id 时安装版优先（内置 id 不允许被安装覆盖，这里只是兜底）。"""
    merged = builtin_manifests()
    merged.update(installed_manifests())
    return merged


def plugin_error(pid: str) -> str:
    if not ID_RE.match(str(pid or "")):
        return "主题 id 不合法"
    return "没有找到这个主题插件"


def get_plugin(pid: str) -> dict | None:
    """完整清单：vars 合并到对应明暗基底的完整令牌集。"""
    m = all_manifests().get(str(pid or "").strip().lower())
    if not m:
        return None
    base = builtin_manifests().get("noir" if m["mode"] == "dark" else "ivory") or {}
    base_vars = (base.get("vars") or {}).copy()
    base_vars.update(m.get("vars") or {})
    out = dict(m)
    out["vars"] = base_vars
    return out


def _meta(m: dict) -> dict:
    # 预览色从「合并到基底后的完整令牌」里取：部分覆盖的清单也有完整的画布/容器色
    full = get_plugin(m["id"]) or m
    v = full.get("vars") or {}
    return {
        "id": m["id"],
        "name": m["name"],
        "version": m.get("version", "1.0.0"),
        "author": m.get("author", ""),
        "desc": m.get("desc", ""),
        "mode": m["mode"],
        "builtin": m.get("builtin", True),
        "default_accent": m.get("default_accent", DEFAULT),
        "accents": m.get("accents", []),
        "homepage": m.get("homepage", ""),
        # 卡片预览色：画布 → 容器 → 文字 → 主色，一眼看清气质
        "preview": {
            "bg": v.get("--bg", ""),
            "surface": v.get("--surface", ""),
            "ink": v.get("--ink", ""),
            "accent": m.get("default_accent", DEFAULT),
        },
    }


def list_plugins() -> list[dict]:
    return [_meta(m) for m in all_manifests().values()]


# ---------------------------------------------------------------- 当前主题
_cache: dict[str, object] = {"at": 0.0, "value": DEFAULT, "plugin": "noir"}


def _load() -> None:
    plugin, accent = "noir", DEFAULT
    try:
        from .db import get_setting

        plugin = str(get_setting("theme_plugin") or "").strip().lower()
        if not plugin:
            # 迁移：老库只有 theme_series。classic 是深色默认；其余系列是浅色画布 → 象牙。
            legacy = str(get_setting("theme_series") or "").strip().lower()
            plugin = "ivory" if legacy and legacy != "classic" else "noir"
        if plugin not in all_manifests():
            plugin = "noir"
        m = get_plugin(plugin) or {}
        accent = normalize(
            get_setting("theme_accent") or m.get("default_accent") or DEFAULT
        )
        # 不在这里做可读性校正：raw 要保持用户填的原值，校正发生在 palette() 派生时
    except Exception:  # noqa: BLE001 - 库还没建好时不要让页面挂掉
        pass
    _cache["value"] = accent
    _cache["plugin"] = plugin


def current_plugin() -> str:
    import time

    if time.monotonic() - float(_cache["at"] or 0) < 5:
        return str(_cache["plugin"])
    _load()
    _cache["at"] = time.monotonic()
    return str(_cache["plugin"])


def current() -> str:
    """当前生效的主色。带 5 秒缓存，页面渲染不额外打库。"""
    import time

    if time.monotonic() - float(_cache["at"] or 0) < 5:
        return str(_cache["value"])
    _load()
    _cache["at"] = time.monotonic()
    return str(_cache["value"])


def reset_cache() -> None:
    _cache["at"] = 0.0


# ---------------------------------------------------------------- 派生
def palette(accent: str | None = None, mode: str | None = None) -> dict:
    """主色 + 主题明暗模式 → 品牌色族。模式缺省取当前主题。"""
    raw = normalize(accent if accent else current())
    mode = mode or (get_plugin(current_plugin()) or {}).get("mode", "dark")
    brand = readable(raw, mode)
    r, g, b = _rgb(brand)
    dark = mode == "dark"
    return {
        "accent": brand,
        "raw": raw,
        "adjusted": brand != raw,
        # hover：深底往白提（亮起=可点），浅底往黑压（classic 行为）
        "hover": mix(brand, "#ffffff", 0.10) if dark else mix(brand, "#000000", 0.12),
        # 软底：主色低透明度叠在画布上
        "soft": f"rgba({r},{g},{b},{0.14 if dark else 0.08})",
        "line": f"rgba({r},{g},{b},{0.38 if dark else 0.22})",
        "deep": mix(brand, "#000000", 0.32),
        "light": mix(brand, "#ffffff", 0.30 if dark else 0.18),
        "rgb": f"{r},{g},{b}",
    }


def css_vars(accent: str | None = None) -> str:
    """注入到页面 <style> 开头的 :root 变量块：主色派生族 + 当前主题全部语义令牌。"""
    p = palette(accent)
    plugin = get_plugin(current_plugin()) or {}
    parts = [
        f"--brand:{p['accent']}",
        f"--brand-hover:{p['hover']}",
        f"--brand-soft:{p['soft']}",
        f"--brand-line:{p['line']}",
        f"--brand-deep:{p['deep']}",
        f"--brand-light:{p['light']}",
        f"--brand-rgb:{p['rgb']}",
    ]
    for k, v in (plugin.get("vars") or {}).items():
        if k not in BRAND_KEYS:
            parts.append(f"{k}:{v}")
    out = ":root{" + ";".join(parts) + "}"
    v = plugin.get("vars") or {}
    if str(v.get("--track-seg", "0")).strip() not in ("0", "0px", ""):
        # 分段倒计时条：只在主题声明了 --track-seg 时才加遮罩，老主题零变化
        m = ("repeating-linear-gradient(90deg,#000 0 var(--track-seg),transparent var(--track-seg) "
             "calc(var(--track-seg) + var(--track-gap,2px)))")
        out += ".track{-webkit-mask:" + m + ";mask:" + m + "}"
    return out


def payload(accent: str | None = None) -> dict:
    """给 /api/meta 与 /api/settings 的完整主题载荷（前端 applyPalette 直接吃）。"""
    pid = current_plugin()
    plugin = get_plugin(pid) or {}
    p = palette(accent)
    return {
        **p,
        "plugin": pid,
        "plugin_name": plugin.get("name", pid),
        "mode": plugin.get("mode", "dark"),
        # 完整语义令牌：前端逐个写进 :root，服务端页面与 SPA 共用同一契约
        "vars": {k: v for k, v in (plugin.get("vars") or {}).items() if k not in BRAND_KEYS},
        "plugins": list_plugins(),
        "presets": [{"name": n, "value": v} for n, v in PRESETS],
    }


# ---------------------------------------------------------------- 安装 / 卸载
def install_manifest(raw: bytes, source: str) -> dict:
    """校验并落盘一份主题清单；返回插件元信息。"""
    m = _manifest_from_raw(raw, source)
    if m["id"] in builtin_manifests():
        raise ValueError(f"id {m['id']} 与内置主题重名，换一个 id 再发布")
    target = PLUGINS_DIR / m["id"]
    target.mkdir(parents=True, exist_ok=True)
    (target / "theme.json").write_bytes(
        json.dumps({k: v for k, v in m.items() if k != "source"}, ensure_ascii=False, indent=2).encode("utf-8")
    )
    reset_cache()
    return _meta({**m, "builtin": False})


def save_preview(pid: str, raw: bytes) -> None:
    """保存商店带来的预览图（可选，超限直接放弃，不影响安装）。"""
    if not ID_RE.match(pid) or len(raw) > PREVIEW_MAX or raw[:4] != b"\x89PNG":
        return
    try:
        (PLUGINS_DIR / pid / "preview.png").write_bytes(raw)
    except Exception:  # noqa: BLE001 - 预览图失败不算安装失败
        pass


def uninstall(pid: str) -> None:
    pid = str(pid or "").strip().lower()
    if pid in builtin_manifests():
        raise ValueError("内置主题不能卸载")
    target = PLUGINS_DIR / pid
    if not (target / "theme.json").is_file():
        raise ValueError(plugin_error(pid))
    shutil.rmtree(target, ignore_errors=True)
    reset_cache()
    # 当前主题被卸了就回玄夜
    from .db import get_setting, set_setting

    if str(get_setting("theme_plugin") or "").lower() == pid:
        set_setting("theme_plugin", "noir")
        set_setting("theme_accent", DEFAULT)


# ---------------------------------------------------------------- GitHub 商店
GH_API = "https://api.github.com"
GH_RAW = "https://raw.githubusercontent.com"
GH_JSD = "https://cdn.jsdelivr.net/gh"
_HTTP_TIMEOUT = 15


def _gh_headers() -> dict:
    """GitHub API 头：UA 必须；配了 THEME_GH_TOKEN 就带上（未认证限额 60 次/小时）。"""
    h = {"User-Agent": "tmp-preview-theme-store", "Accept": "application/vnd.github+json"}
    token = str(getattr(config, "THEME_GH_TOKEN", "") or "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def parse_repo_input(raw: str) -> dict:
    """把各种输入收敛成 {repo, ref, path}。

    支持：owner/repo · owner/repo@v1 · https://github.com/owner/repo[/tree/ref[/path]]
    · …/blob/ref/path/theme.json · https://raw.githubusercontent.com/owner/repo/ref/path
    """
    s = str(raw or "").strip().strip("/")
    repo = ref = path = ""
    m = re.match(r"^(?:https?://)?(?:raw\.githubusercontent\.com|cdn\.jsdelivr\.net/gh)/([^/\s]+)/([^/\s@]+)(?:@([^/\s]+))?/(.+)$", s)
    if m:
        return {"repo": f"{m.group(1)}/{m.group(2)}", "ref": m.group(3) or "", "path": m.group(4).strip("/")}
    m = re.match(r"^(?:https?://)?github\.com/([^/\s]+)/([^/\s]+)(?:/(?:tree|blob)/([^/\s]+)(?:/(.+))?)?/?$", s)
    if m:
        return {"repo": f"{m.group(1)}/{m.group(2)}", "ref": m.group(3) or "", "path": (m.group(4) or "").strip("/")}
    m = re.match(r"^([\w.-]+)/([\w.-]+)(?:@([^/\s]+))?(?:/(.+))?$", s)
    if m:
        return {"repo": f"{m.group(1)}/{m.group(2)}", "ref": m.group(3) or "", "path": (m.group(4) or "").strip("/")}
    raise ValueError("仓库格式不认识：支持 owner/repo、owner/repo@分支 或 GitHub 链接")


def _http_get(url: str, timeout: int = _HTTP_TIMEOUT) -> bytes:
    headers = _gh_headers() if url.startswith(GH_API) else {"User-Agent": "tmp-preview-theme-store"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _fetch_file(repo: str, ref: str, path: str) -> bytes:
    """取仓库文件，通道按序兜底：自定义镜像（可选）→ raw → jsDelivr（Fastly / Cloudflare
    两家节点）→ GitHub contents API（base64）。

    部分网络环境 raw.githubusercontent.com 与 jsDelivr 都会被重置连接，
    api.github.com 往往仍可达，contents 接口（≤1MB，base64）就是最后一条通道；
    THEME_RAW_MIRROR 环境变量可指定自己的镜像（填到 {repo}/{ref}/{path} 之前那段）。
    """
    r = ref or "HEAD"
    mirror = str(getattr(config, "THEME_RAW_MIRROR", "") or "").strip().rstrip("/")
    urls = []
    if mirror:
        urls.append(f"{mirror}/{repo}/{r}/{path}")
    urls += [
        f"{GH_RAW}/{repo}/{r}/{path}",
        f"https://fastly.jsdelivr.net/gh/{repo}@{r}/{path}",
        f"{GH_JSD}/{repo}@{r}/{path}",
        f"https://gcore.jsdelivr.net/gh/{repo}@{r}/{path}",
    ]
    errors = []
    for url in urls:
        try:
            return _http_get(url)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{url.split('/')[2]}: {e}")
    # 最后兜底：contents API 走 api.github.com（base64，单文件 ≤1MB，theme.json 远够）
    try:
        q = urllib.parse.quote(path)
        data = json.loads(_http_get(f"{GH_API}/repos/{repo}/contents/{q}?ref={r}").decode("utf-8"))
        if data.get("encoding") == "base64" and data.get("content"):
            return base64.b64decode(data["content"])
        errors.append("api.github.com: 响应不是 base64 内容")
    except Exception as e:  # noqa: BLE001
        errors.append(f"api.github.com: {e}")
    raise RuntimeError(
        "；".join(errors) + "（全部通道不可达时，可设置 THEME_RAW_MIRROR 指向自建镜像）"
    )


def _default_branch(repo: str) -> str:
    """仓库默认分支（GitHub trees API 直接吃分支名）。"""
    data = json.loads(_http_get(f"{GH_API}/repos/{repo}").decode("utf-8"))
    return data.get("default_branch") or "main"


def discover_themes(repo: str, ref: str) -> list[dict]:
    """枚举仓库里所有 theme.json（根目录与任意子目录，最多取 12 个）。"""
    r = ref or _default_branch(repo)
    data = json.loads(_http_get(f"{GH_API}/repos/{repo}/git/trees/{r}?recursive=1").decode("utf-8"))
    paths = [
        t["path"]
        for t in data.get("tree", [])
        if t.get("type") == "blob" and t.get("path", "").endswith("theme.json")
    ][:12]
    if not paths:
        raise ValueError("仓库里没有找到 theme.json（格式见 examples/theme-plugin/README.md）")
    out = []
    for p in paths:
        entry = {"repo": repo, "ref": ref, "path": p, "manifest": None, "error": ""}
        try:
            entry["manifest"] = _manifest_from_raw(_fetch_file(repo, ref, p), f"{repo}@{ref}:{p}")
        except Exception as e:  # noqa: BLE001 - 单个坏主题不拖垮列表
            entry["error"] = str(e)
        out.append(entry)
    return out


def store_preview(repo_input: str) -> dict:
    """商店预览：解析输入 → 枚举清单。失败时给出能看懂的错误。"""
    try:
        parsed = parse_repo_input(repo_input)
    except ValueError as e:
        return {"ok": False, "error": str(e), "items": []}
    repo, ref, path = parsed["repo"], parsed["ref"], parsed["path"]
    try:
        if path:
            # 明确指到某个目录/文件：只取那一个
            p = path if path.endswith("theme.json") else path.rstrip("/") + "/theme.json"
            raw = _fetch_file(repo, ref, p)
            items = [{"repo": repo, "ref": ref, "path": p,
                      "manifest": _manifest_from_raw(raw, f"{repo}@{ref}:{p}"), "error": ""}]
        else:
            items = discover_themes(repo, ref)
        return {"ok": True, "error": "", "items": items}
    except urllib.error.HTTPError as e:
        if e.code == 403:
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                body = ""
            if "rate limit" in body.lower():
                hint = "GitHub API 限额（未认证 60 次/小时）。稍后再试，或在 .env 配置 THEME_GH_TOKEN 提高限额"
            else:
                hint = "仓库不存在或设为私有"
        elif e.code == 404:
            hint = "仓库不存在、已改名或设为私有"
        else:
            hint = f"GitHub 返回 {e.code}"
        return {"ok": False, "error": f"{hint}（{e.code}）", "items": []}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300], "items": []}


def store_install(repo: str, ref: str, path: str) -> dict:
    raw = _fetch_file(repo, ref or "HEAD", path)
    meta = install_manifest(raw, f"{repo}@{ref or 'HEAD'}:{path}")
    # 预览图有就带上，失败不影响安装
    for name in ("preview.png", path.rsplit("/", 1)[0] + "/preview.png" if "/" in path else ""):
        if name:
            try:
                save_preview(meta["id"], _fetch_file(repo, ref or "HEAD", name))
            except Exception:  # noqa: BLE001
                pass
    return meta
