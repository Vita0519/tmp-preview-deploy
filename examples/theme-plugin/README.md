# 主题插件格式（theme.json）

tmp-preview 的主题是一个**纯声明式的 JSON 清单**：一整套 CSS 语义令牌（`--var`），
不含任何可执行代码。把 `theme.json` 放进任意公开 GitHub 仓库，别人就能在
**设置 → 外观 → 主题商店** 里输入仓库地址一键安装。

最小可用目录结构（推到仓库根目录或任意子目录都可以，商店会枚举整仓库找 `theme.json`）：

```
your-repo/
└── theme.json          # 必须；也可放 themes/xxx/theme.json，支持多套并存
└── preview.png         # 可选；商店安装时一并抓取（PNG，≤256KB）
```

## 字段说明

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | ✅ | `^[a-z0-9][a-z0-9-]{1,39}$`，全站唯一，不能与内置主题重名 |
| `name` | ✅ | 显示名（≤40 字） |
| `mode` | ✅ | `dark` / `light`，决定主色派生的对比度尺子与缺省基底 |
| `version` |  | 语义化版本，仅展示 |
| `author` / `homepage` / `desc` |  | 展示用 |
| `default_accent` |  | 默认主色（`#rrggbb`），用户仍可在设置里微调 |
| `accents` |  | 推荐主色列表（≤12 个） |
| `vars` |  | 语义令牌表，**可以只写要覆盖的键**，缺省回落到同模式基底 |

## `vars` 语义令牌

只列常用的；完整清单见 [`backend/app/builtin_themes/noir.json`](../../backend/app/builtin_themes/noir.json)。

| 令牌 | 作用 |
|---|---|
| `--scheme` | `dark` / `light`，浏览器原生控件配色 |
| `--bg` `--bg-2` `--bg-deep` | 画布（页面底、渐变起手、更深处） |
| `--surface` `--surface-2` `--surface-3` | 容器三级（卡片 / 次级 / 三级填充） |
| `--ink` `--ink-2` `--ink-3` `--ink-4` | 文字四级（正文 / 次要 / 弱 / 更弱） |
| `--ink-rgb` `--bg-rgb` | rgba 拼色通道（悬浮层、毛玻璃都用它） |
| `--line` `--line-2` | 描边两档 |
| `--warn` `--warn-soft` `--warn-line` | 琥珀警示族 |
| `--danger` `--danger-soft` `--danger-line` | 危险红族 |
| `--scrim` `--glass` | 遮罩、毛玻璃顶栏 |
| `--tip-bg` `--tip-ink`、`--toast-bg` `--toast-ink` `--toast-line` | 工具提示 / 轻提示 |
| `--skel-a` `--skel-b` | 骨架屏微光 |
| `--scroll-thumb` `--scroll-thumb-hover` | 滚动条 |
| `--shadow-1` `--shadow-2` `--shadow-pop` `--shadow-panel` `--shadow-drawer` `--edge` | 阴影分档（`--edge` 是卡片顶部的受光高光） |
| `--select-arrow` | select 下拉箭头（data-uri，无法用 currentColor） |

### 可选布局令牌（v2.4+）

不写就保持默认外观；只收安全取值，写错会安装失败并提示。

| 令牌 | 作用 | 默认 | 取值限制 |
|---|---|---|---|
| `--track-h` | 门户倒计时条高度 | `3px` | 1–12px |
| `--track-seg` | 分段长度，非 0 即启用细分段样式 | `0`（连续线） | 0–99px |
| `--track-gap` | 段间空隙 | `2px` | 0–99px |
| `--track-radius` | 倒计时条圆角 | `99px` | px |
| `--track-bg` | 倒计时条底槽色 | 正文色 10% | 颜色值 |
| `--track-glow` | 进度发光（box-shadow） | `none` | 阴影值 |
| `--card-radius` | 门户卡片圆角 | `12px` | px |
| `--font-num` | 倒计时数字字体 | 继承 | 字体族 |

内置示例：`ticker`（刻度，深色）、`paper`（纸感，浅色）。剩余 <2 小时的倒计时条会缓慢呼吸（尊重"减少动态效果"）。

> `--brand` `--brand-hover` `--brand-soft` `--brand-line` `--brand-deep` `--brand-light` `--brand-rgb`
> **不进清单**：它们由用户主色（`default_accent` 或用户微调值）按 `mode` 实时派生，
> 清单里写了也会被忽略。深浅两把尺子保证主色在按钮（白字）和画布（文字/徽标）上都 ≥3:1。

## 发布与分享

1. Fork 本仓库或新建仓库，复制本目录的 `theme.json` 改成你的配色；
2. 推送到 GitHub（仓库公开）；
3. 把 `owner/repo`（或仓库链接）发给任何人，对方在 **主题商店** 粘贴即可安装。

本仓库自带的示例（本文件所在目录）也可以直接体验：
主题商店 → 「装示例插件」，无需外网。
