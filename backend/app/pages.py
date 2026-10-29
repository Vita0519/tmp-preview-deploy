"""服务端渲染的轻页面：访客预览外壳 / 门户 / 错误页（无框架，首屏快）。"""
from html import escape

FONT = (
    '-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB",'
    '"Microsoft YaHei","Segoe UI",Roboto,sans-serif'
)
MONO = 'ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace'

BASE_CSS = f"""
*{{box-sizing:border-box}}
html,body{{margin:0;padding:0}}
body{{font-family:{FONT};color:#14161a;background:#f6f7f5;-webkit-font-smoothing:antialiased}}
a{{color:#0f766e;text-decoration:none}}
.num{{font-variant-numeric:tabular-nums}}
"""

# 站点图标：项目自带就用项目的，否则回落到站点图标
FAVICON_NAMES = ("favicon.ico", "favicon.svg", "favicon.png", "apple-touch-icon.png")


def favicon_href(slug: str | None = None) -> str:
    if slug:
        from . import storage  # 局部导入，避免模块级循环依赖
        for name in FAVICON_NAMES:
            try:
                target = storage.resolve_in_project(slug, name)
            except Exception:  # noqa: BLE001 - 找不到就当没有
                target = None
            if target is not None and target.is_file():
                return f"/p/{slug}/{name}"
    return "/favicon.svg"


def preview_page(p: dict, server_now: int, site_title: str) -> str:
    title = escape(p["title"])
    owner = escape((p.get("owner") or {}).get("display_name") or "")
    kind = p["kind"]
    allow_dl = bool(p["allow_download"])
    expires = p["expires_at"] or 0
    raw = f"/p/{p['slug']}/"
    size = _human(p["size_bytes"])
    expired = bool(p["expired"])
    missing_entry = kind == "static" and not p["entry"]

    body = ""
    if kind == "link":
        body = _empty_state("这是一个外链项目", "点击下方按钮跳转到目标站点", p["link_url"], "打开外部站点")
    elif kind == "zip":
        body = _empty_state(
            "压缩包项目", f"{size} · 仅提供下载", f"/download/{p['slug']}" if allow_dl else "", "下载压缩包" if allow_dl else ""
        )
    elif missing_entry:
        body = _empty_state("没有入口页面", "该项目缺少 index.html，无法直接预览", raw, "浏览目录")
    elif expired:
        body = _empty_state("项目已到期", "该项目已超过设定的存活时长，访问已停止", "", "")
    else:
        body = f'<iframe id="frame" src="{escape(raw)}" title="{title}" allow="fullscreen; clipboard-write; autoplay; xr-spatial-tracking"></iframe>'

    dl_btn = (
        f'<a class="btn primary" href="/download/{p["slug"]}" download>下载</a>'
        if allow_dl and not expired else ""
    )

    return f"""<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<link rel="icon" href="{favicon_href(p['slug'])}">
<title>{title} · {escape(site_title)}</title>
<style>
{BASE_CSS}
body{{height:100vh;display:flex;flex-direction:column;overflow:hidden}}
.bar{{flex:0 0 auto;height:52px;display:flex;align-items:center;gap:10px;padding:0 14px;
background:rgba(255,255,255,.86);backdrop-filter:blur(14px) saturate(180%);
border-bottom:1px solid rgba(20,22,26,.08);position:relative;z-index:5}}
.mark{{width:26px;height:26px;border-radius:7px;background:#0f766e;color:#fff;display:flex;
align-items:center;justify-content:center;font:600 13px/1 {MONO};flex:0 0 auto}}
.ttl{{min-width:0;display:flex;flex-direction:column;gap:1px}}
.ttl b{{font-size:13.5px;font-weight:650;letter-spacing:-.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:46vw}}
.ttl span{{font-size:11.5px;color:#7b8189;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.spacer{{flex:1 1 auto}}
.pill{{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 10px;border-radius:999px;
font-size:12px;font-weight:600;background:#eff4f2;color:#0f766e;border:1px solid rgba(15,118,110,.16);white-space:nowrap}}
.pill .dot{{width:6px;height:6px;border-radius:50%;background:#0f766e;animation:pulse 2.4s ease-in-out infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}
.pill.warn{{background:#fdf3e7;color:#b45309;border-color:rgba(180,83,9,.18)}}
.pill.warn .dot{{background:#b45309}}
.pill.dead{{background:#fdeceb;color:#b42318;border-color:rgba(180,35,24,.18)}}
.pill.perm{{background:#eef2f8;color:#3a4a63;border-color:rgba(58,74,99,.16)}}
.btn{{height:28px;display:inline-flex;align-items:center;padding:0 11px;border-radius:7px;font-size:12.5px;
font-weight:600;border:1px solid rgba(20,22,26,.14);background:#fff;color:#2a2f36;cursor:pointer;
transition:background .16s,border-color .16s,transform .16s}}
.btn svg{{display:block;flex:0 0 auto}}
.btn:hover{{background:#f7f8f7;border-color:rgba(20,22,26,.26)}}
.btn:active{{transform:translateY(1px)}}
.btn.primary{{background:#0f766e;border-color:#0f766e;color:#fff}}
.btn.primary:hover{{background:#0d6a62}}
.btn.ghost{{border-color:transparent;background:transparent;color:#5b636d}}
.btn.ghost:hover{{background:rgba(20,22,26,.05);border-color:transparent}}
.icon{{width:28px;justify-content:center;padding:0}}
main{{flex:1 1 auto;position:relative;background:#fff;min-height:0}}
iframe{{width:100%;height:100%;border:0;display:block;background:#fff}}
.toast{{position:fixed;left:50%;bottom:22px;transform:translate(-50%,10px);background:#14161a;color:#fff;
padding:9px 14px;border-radius:9px;font-size:12.5px;opacity:0;pointer-events:none;transition:.22s;z-index:20}}
.toast.on{{opacity:1;transform:translate(-50%,0)}}
.empty{{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;
background:radial-gradient(120% 90% at 50% 0%,#fbfcfb 0%,#f1f3f1 100%);padding:24px;text-align:center}}
.empty h2{{margin:0;font-size:17px;letter-spacing:-.01em}}
.empty p{{margin:0;color:#7b8189;font-size:13px;max-width:380px;line-height:1.6}}
.empty .btn{{margin-top:6px;height:32px;padding:0 14px}}
@media (max-width:640px){{
  .bar{{height:48px;padding:0 10px;gap:8px}}
  .ttl b{{max-width:34vw;font-size:13px}}
  .hide-sm{{display:none}}
  .btn{{height:27px;padding:0 9px}}
}}
</style></head>
<body>
<div class="bar">
  <div class="mark">P</div>
  <div class="ttl"><b>{title}</b><span>{owner + ' · ' if owner else ''}{size}{' · ' + str(p['file_count']) + ' 个文件' if p['file_count'] else ''}</span></div>
  <div class="spacer"></div>
  <span class="pill {'dead' if expired else ('perm' if not expires else '')}" id="pill"><span class="dot"></span><span id="cd">{'已到期' if expired else ('永久' if not expires else '—')}</span></span>
  {dl_btn}
  <button class="btn ghost hide-sm" id="copy" title="复制链接" style="gap:5px">
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6.5 6.5V3.8c0-.7.6-1.3 1.3-1.3h4.4c.7 0 1.3.6 1.3 1.3v4.9c0 .7-.6 1.3-1.3 1.3H7.8c-.7 0-1.3-.6-1.3-1.3Z"/><path d="M3.5 7.5h5.2c.7 0 1.3.6 1.3 1.3v4.4c0 .7-.6 1.3-1.3 1.3H3.5c-.7 0-1.3-.6-1.3-1.3V8.8c0-.7.6-1.3 1.3-1.3Z"/></svg>
    复制
  </button>
  <button class="btn ghost icon hide-sm" id="open" title="新窗口打开">
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 3.5H13V7M13 3.5 7.5 9M11 12.5H4.5V4.5"/></svg>
  </button>
  <button class="btn ghost icon" id="refresh" title="刷新 (R)">
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12.8 6.4A5 5 0 1 0 13 9.5M12.8 3.2v3.4h-3.4"/></svg>
  </button>
</div>
<main>{body}</main>
<div class="toast" id="toast"></div>
<script>
(function(){{
  var EXP={expires}, NOW={server_now}, off=0;
  var el=document.getElementById('cd'), pill=document.getElementById('pill');
  function pad(n){{return n<10?'0'+n:''+n}}
  function fmt(ms){{
    if(ms<=0) return '已到期';
    var s=Math.floor(ms/1000), d=Math.floor(s/86400), h=Math.floor(s%86400/3600),
        m=Math.floor(s%3600/60), sec=s%60;
    if(d>0) return d+' 天 '+h+' 小时';
    if(h>0) return h+':'+pad(m)+':'+pad(sec);
    return pad(m)+':'+pad(sec);
  }}
  function tick(){{
    if(!EXP) return;
    var left=EXP-(Date.now()+off);
    if(el) el.textContent=fmt(left);
    if(pill){{
      pill.classList.toggle('warn', left>0 && left<2*3600e3);
      pill.classList.toggle('dead', left<=0);
      var dot=pill.querySelector('.dot'); if(dot) dot.style.animation = left<=0?'none':'';
    }}
    if(left<=0 && !window.__reloaded){{ window.__reloaded=1; setTimeout(function(){{ location.reload(); }},1500); }}
  }}
  tick(); setInterval(tick,1000);
  function toast(msg){{
    var t=document.getElementById('toast'); t.textContent=msg; t.classList.add('on');
    clearTimeout(window.__tt); window.__tt=setTimeout(function(){{t.classList.remove('on')}},1600);
  }}
  var copy=document.getElementById('copy');
  if(copy) copy.onclick=function(){{
    var url=location.href.split('#')[0];
    (navigator.clipboard?navigator.clipboard.writeText(url):Promise.reject()).then(function(){{toast('链接已复制')}})
      .catch(function(){{
        var ta=document.createElement('textarea'); ta.value=url; document.body.appendChild(ta); ta.select();
        try{{document.execCommand('copy'); toast('链接已复制')}}catch(e){{toast(url)}} document.body.removeChild(ta);
      }});
  }};
  var op=document.getElementById('open');
  if(op) op.onclick=function(){{ window.open('{escape(raw)}','_blank','noopener'); }};
  var rf=document.getElementById('refresh');
  if(rf) rf.onclick=function(){{ var f=document.getElementById('frame'); if(f) f.src=f.src; else location.reload(); }};
  document.addEventListener('keydown',function(e){{
    if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA') return;
    if(e.key==='r'||e.key==='R'){{ var f=document.getElementById('frame'); if(f) f.src=f.src; else location.reload(); }}
  }});
}})();
</script>
</body></html>"""


def _empty_state(title: str, desc: str, href: str, cta: str) -> str:
    btn = f'<a class="btn primary" href="{escape(href)}">{escape(cta)}</a>' if href and cta else ""
    return (
        f'<div class="empty"><h2>{escape(title)}</h2><p>{escape(desc)}</p>{btn}</div>'
    )


def _human(n: int) -> str:
    n = n or 0
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.0f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"


PORTAL_CSS = """
body{background:linear-gradient(180deg,#fbfcfb,#f2f4f2 60%,#eef1ef);min-height:100vh}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px 80px}
/* 标签以上整体吸附：标题 + 作者名片 + 筛选条 + 标签 */
.dock{position:sticky;top:0;z-index:20;margin:0 -20px;padding:18px 20px 0;
background:rgba(250,251,250,.9);backdrop-filter:blur(12px) saturate(1.15);
-webkit-backdrop-filter:blur(12px) saturate(1.15);border-bottom:1px solid rgba(20,22,26,.06)}
header{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:14px}
h1{margin:0;font-size:26px;letter-spacing:-.02em}
.sub{color:#7b8189;font-size:12.5px;margin-top:5px}
.author{display:flex;align-items:center;gap:11px;margin:0 0 14px;padding:11px 13px;background:#fff;
border:1px solid rgba(20,22,26,.08);border-radius:12px;box-shadow:0 1px 2px rgba(20,22,26,.03)}
.author .ava{flex:0 0 auto;width:34px;height:34px;border-radius:50%;display:grid;place-items:center;
background:#eff4f2;color:#0f766e;font-weight:650;font-size:14px;letter-spacing:-.02em;
border:1px solid rgba(15,118,110,.14)}
.author .am{min-width:0;flex:1 1 auto}
.author .am b{display:block;font-size:13.5px;letter-spacing:-.01em;color:#14161a}
.author .am span{display:block;margin-top:2px;font-size:11.5px;color:#8a9099;line-height:1.45;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.alinks{flex:0 0 auto;display:flex;align-items:center;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.alink{display:inline-flex;align-items:center;gap:5px;height:28px;padding:0 9px;border-radius:8px;
border:1px solid rgba(20,22,26,.1);background:#fff;color:#5b636d;font-size:11.5px;font-weight:600;
transition:color .16s,border-color .16s,background .16s}
.alink:hover{color:#0f766e;border-color:rgba(15,118,110,.38);background:#f6fbfa}
.alink svg{width:13px;height:13px;flex:0 0 auto}
.alink.only-icon{padding:0;width:28px;justify-content:center}
@media (max-width:620px){
  .author{flex-wrap:wrap;padding:10px 11px}
  .alinks{width:100%;justify-content:flex-start}
  .alink span{display:none}
  .alink{padding:0;width:28px;justify-content:center}
}
.btn{height:30px;display:inline-flex;align-items:center;padding:0 12px;border-radius:8px;font-size:12.5px;
font-weight:600;border:1px solid rgba(20,22,26,.14);background:#fff;color:#2a2f36}
.tools{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.seg{display:inline-flex;gap:2px;padding:2px;border-radius:9px;background:#eaecea;
border:1px solid rgba(20,22,26,.06)}
.seg button{height:26px;padding:0 11px;border:0;border-radius:7px;background:transparent;
font:600 12px/1 inherit;color:#5b636d;cursor:pointer;transition:background .16s,color .16s,box-shadow .16s}
.seg button:hover{color:#14161a}
.seg button.on{background:#fff;color:#14161a;box-shadow:0 1px 2px rgba(20,22,26,.1)}
.seg.icons button{width:28px;padding:0;display:grid;place-items:center}
.seg.icons svg{width:14px;height:14px}
.tools .spacer{flex:1 1 auto}
.search{height:30px;width:210px;padding:0 10px;border-radius:8px;border:1px solid rgba(20,22,26,.14);
background:#fff;font-size:12.5px;color:#14161a;outline:none;transition:border-color .16s,box-shadow .16s}
.search:focus{border-color:rgba(15,118,110,.5);box-shadow:0 0 0 3px rgba(15,118,110,.1)}
.sort{height:30px;padding:0 8px;border-radius:8px;border:1px solid rgba(20,22,26,.14);background:#fff;
font-size:12.5px;color:#2a2f36;outline:none;cursor:pointer}
.sort:focus{border-color:rgba(15,118,110,.5)}
.cnt{font-size:11.5px;color:#8a9099;font-variant-numeric:tabular-nums;white-space:nowrap}
.tagsbar{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:0 0 12px;min-height:0}
.tagsbar:empty{display:none}
.tagsbar button{height:22px;padding:0 8px;border-radius:6px;border:1px solid rgba(20,22,26,.08);
background:#f4f6f4;color:#5b636d;font:600 11px/1 inherit;cursor:pointer;transition:.16s}
.tagsbar button:hover{background:#eef2f0;color:#14161a}
.tagsbar button.on{background:#0f766e;border-color:#0f766e;color:#fff}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));align-items:stretch;
padding-top:14px}
.grid[hidden]{display:none}
.card{position:relative;display:flex;flex-direction:column;background:#fff;border:1px solid rgba(20,22,26,.09);
border-radius:12px;padding:14px 15px 12px;
transition:transform .18s cubic-bezier(.2,.8,.2,1),box-shadow .18s,border-color .18s}
.card[hidden]{display:none}
.card:hover{transform:translateY(-2px);box-shadow:0 12px 28px -18px rgba(20,22,26,.42);border-color:rgba(15,118,110,.32)}
.top{min-width:0;padding-right:90px}
.tinfo{min-width:0}
.name{display:flex;align-items:center;gap:6px;font-weight:650;font-size:14.5px;letter-spacing:-.01em;color:#14161a;
min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kind{flex:0 0 auto;font-size:10px;font-weight:600;color:#7b8189;background:#f3f5f3;
border:1px solid rgba(20,22,26,.06);border-radius:5px;padding:1px 5px}
.byline{margin-top:5px;display:flex;align-items:center;gap:6px;font-size:11.5px;color:#98a0a6;
font-variant-numeric:tabular-nums;min-width:0}
.byline .dot{width:3px;height:3px;border-radius:50%;background:#cdd2d6;flex:0 0 auto}
.byline span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.desc{margin:8px 0 0;color:#5b636d;font-size:12.5px;line-height:1.55;display:-webkit-box;
-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:19px}
.tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:9px}
.tags:empty{display:none}
.tag{font-size:10.5px;padding:2px 7px;border-radius:5px;background:#f3f5f3;color:#5b636d;
border:1px solid rgba(20,22,26,.06)}
.foot{margin-top:auto;padding-top:10px}
.cdrow{display:flex;align-items:baseline;gap:5px;margin-bottom:6px}
.cdlab{font-size:10.5px;color:#98a0a6}
.cd{font-size:12.5px;font-weight:650;color:#0f766e;font-variant-numeric:tabular-nums;
letter-spacing:-.01em;white-space:nowrap}
.cd.perm{color:#3a4a63}
.cd.warn{color:#b45309}
.cd.dead{color:#b42318}
.cdend{margin-left:auto;font-size:10.5px;color:#a3aab0;font-variant-numeric:tabular-nums;white-space:nowrap}
.track{height:3px;border-radius:99px;background:#eef1ef;overflow:hidden}
.track > i{display:block;height:100%;border-radius:99px;background:#0f766e;transition:width .5s ease}
.track.warn > i{background:#b45309}
.track.dead > i{background:#b42318}
/* 访问圆环：整张卡片的右上角 */
.ring{position:absolute;top:12px;right:12px;width:42px;height:42px;border-radius:50%;
display:grid;place-items:center;
background:conic-gradient(#0f766e calc(var(--p,0) * 1%), #eef1ef 0)}
.ring::after{content:'';position:absolute;inset:4px;border-radius:50%;background:#fff}
.ring .in{position:relative;z-index:1;display:flex;flex-direction:column;align-items:center;line-height:1;gap:2px}
.ring b{font-size:12px;font-weight:650;color:#14161a;font-variant-numeric:tabular-nums;letter-spacing:-.03em}
.ring b.sm{font-size:9.5px}
.ring i{font-style:normal;font-size:8px;color:#a3aab0;letter-spacing:.02em}
.card:hover .ring{background:conic-gradient(#0d6a62 calc(var(--p,0) * 1%), #e9ecea 0)}
/* 整卡可点：一层覆盖式链接，复制按钮浮在上面 */
.hit{position:absolute;inset:0;z-index:1;border-radius:inherit}
.cbtn{position:absolute;z-index:3;top:11px;right:61px;width:26px;height:26px;padding:0;
display:grid;place-items:center;border:1px solid transparent;border-radius:8px;background:transparent;
color:#9aa1a8;cursor:pointer;transition:color .16s,background .16s,border-color .16s}
.cbtn:hover{color:#0f766e;background:#f1f5f3;border-color:rgba(15,118,110,.2)}
.cbtn:active{transform:scale(.94)}
.cbtn:focus-visible{outline:2px solid rgba(15,118,110,.45);outline-offset:2px}
.cbtn svg{width:13px;height:13px;display:block}
.cbtn .ic-done{display:none;stroke-width:2.2}
.cbtn.done{color:#0f766e;background:#e9f3f0;border-color:rgba(15,118,110,.26)}
.cbtn.done .ic-copy{display:none}
.cbtn.done .ic-done{display:block}
.cbtn.fail{color:#b42318;background:#fdeceb;border-color:rgba(180,35,24,.24)}
.cbtn .tip{position:absolute;top:calc(100% + 7px);right:0;transform:scale(.92);
transform-origin:100% 0;padding:3px 8px;border-radius:6px;background:#14161a;color:#fff;
font-size:11px;font-weight:600;line-height:1.4;white-space:nowrap;opacity:0;
pointer-events:none;transition:opacity .16s,transform .16s;z-index:4}
.cbtn.done .tip{opacity:1;transform:scale(1)}
.cbtn.fail .tip{background:#b42318;opacity:1;transform:scale(1)}
/* ---------- 列表模式（独立结构，不复用卡片） ---------- */
.rows{display:flex;flex-direction:column;gap:8px;padding-top:14px}
.rows[hidden]{display:none}
.row{position:relative;display:grid;
grid-template-columns:minmax(0,240px) minmax(0,1fr) auto 36px 170px 28px;
grid-template-areas:"main desc tags ring foot copy";align-items:center;gap:14px;
background:#fff;border:1px solid rgba(20,22,26,.09);border-radius:12px;padding:10px 14px;
transition:border-color .16s,box-shadow .16s}
.row[hidden]{display:none}
.row:hover{border-color:rgba(15,118,110,.32);box-shadow:0 6px 18px -14px rgba(20,22,26,.42)}
.rmain{grid-area:main;min-width:0}
.rname{display:block;font-weight:650;font-size:13.5px;letter-spacing:-.01em;color:#14161a;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rname .kind{margin-left:6px;vertical-align:1px}
.rmeta{margin-top:3px;font-size:11.5px;color:#98a0a6;font-variant-numeric:tabular-nums;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rdesc{grid-area:desc;margin:0;min-width:0;font-size:12px;color:#5b636d;line-height:1.5;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rtags{grid-area:tags;display:flex;gap:5px;flex-wrap:nowrap}
.rring{grid-area:ring;position:relative;width:32px;height:32px;border-radius:50%;display:grid;
place-items:center;background:conic-gradient(#0f766e calc(var(--p,0) * 1%), #eef1ef 0)}
.rring::after{content:'';position:absolute;inset:3px;border-radius:50%;background:#fff}
.rring .in{position:relative;z-index:1;display:flex;flex-direction:column;align-items:center;line-height:1;gap:1px}
.rring b{font-size:10.5px;font-weight:650;color:#14161a;font-variant-numeric:tabular-nums;letter-spacing:-.03em}
.rring b.sm{font-size:8.5px}
.rring i{font-style:normal;font-size:6.5px;color:#a3aab0}
.rfoot{grid-area:foot;min-width:0}
.rfoot .cdrow{margin-bottom:5px}
.rfoot .cd{font-size:12px}
.rfoot .cdend{font-size:10px}
.cbtn.inflow{position:relative;z-index:3;top:auto;right:auto;grid-area:copy;width:26px;height:26px}
.cbtn.inflow .tip{right:auto;left:50%;transform:translateX(-50%) scale(.92);transform-origin:50% 0}
.cbtn.inflow.done .tip,
.cbtn.inflow.fail .tip{transform:translateX(-50%) scale(1)}
@media (max-width:900px){
  .row{grid-template-columns:minmax(0,1fr) 34px 152px 28px;grid-template-areas:"main ring foot copy"}
  .rdesc,.rtags{display:none}
}
@media (max-width:620px){
  .row{grid-template-columns:minmax(0,1fr) 36px 28px;
  grid-template-areas:"main ring copy" "foot foot foot";gap:8px 8px;padding:11px 12px}
  .rring{width:34px;height:34px;align-self:start}
  .cbtn.inflow{align-self:start;justify-self:end}
  .card .cbtn{top:9px;right:58px}
}
.blank{margin-top:14px;text-align:center;color:#8a9099;padding:56px 0;
border:1px dashed rgba(20,22,26,.14);border-radius:12px;font-size:13px}
@media (max-width:900px){
  .grid.list .desc{display:none}
}
@media (max-width:620px){
  .wrap{padding:0 14px 60px}
  .dock{margin:0 -14px;padding:10px 14px 0}
  h1{font-size:20px;line-height:1.25}
  .sub{font-size:11.5px;margin-top:3px}
  header{margin-bottom:10px}
  .author{margin-bottom:10px;padding:8px 10px;gap:9px}
  .author .am span{display:none}
  .tools{margin-bottom:8px;gap:6px}
  .tools .spacer{display:none}
  .cnt{display:none}
  .sort{order:2;flex:0 0 auto;height:28px}
  .search{flex:1 1 110px;width:auto;order:3;height:28px}
  .seg button{height:24px;padding:0 9px;font-size:11.5px}
  .seg.icons button{width:26px}
  /* 标签横向滚动，别把吸顶区撑高 */
  .tagsbar{flex-wrap:nowrap;overflow-x:auto;overflow-y:hidden;margin-bottom:8px;
  padding-bottom:2px;scrollbar-width:none}
  .tagsbar::-webkit-scrollbar{display:none}
  .tagsbar button{flex:0 0 auto}
  .grid{grid-template-columns:1fr;padding-top:10px}
  .rows{padding-top:10px}
  .grid.list .card{flex-wrap:wrap;gap:8px 10px;padding:11px 12px}
  .grid.list .top{flex:1 1 100%;order:1}
  .grid.list .tags{order:4;flex:1 1 100%}
  .grid.list .ring{order:2;position:absolute;top:10px;right:10px;width:36px;height:36px}
  .grid.list .foot{order:3;flex:1 1 100%}
}
"""

PORTAL_JS = """
(function(){
  var NOW=__NOW__, off=0;
  var grid=document.getElementById('grid'), rows=document.getElementById('rows');
  var cards=[].slice.call(grid.querySelectorAll('.card'));
  var rnodes=[].slice.call(rows.querySelectorAll('.row'));
  var nodes=cards.concat(rnodes);
  var cnt=document.getElementById('cnt'), blank=document.getElementById('blank');
  var state={kind:'all',q:'',tag:'',sort:'created'};
  function pad(n){return n<10?'0'+n:''+n}
  function fmt(ms){
    if(ms<=0) return '已到期';
    var s=Math.floor(ms/1000),d=Math.floor(s/86400),h=Math.floor(s%86400/3600),
        m=Math.floor(s%3600/60),sec=s%60;
    if(d>0) return d+'天'+h+'h';
    return h+':'+pad(m)+':'+pad(sec);
  }
  function tick(){
    var now=Date.now()+off;
    nodes.forEach(function(c){
      var exp=+c.dataset.exp; if(!exp) return;
      var left=exp-now, cd=c.querySelector('.cd'), bar=c.querySelector('.track');
      var warn=left>0&&left<2*3600e3, dead=left<=0;
      if(cd){
        cd.textContent = dead ? '已到期' : fmt(left);
        cd.classList.toggle('warn',warn); cd.classList.toggle('dead',dead);
      }
      if(bar){
        var total=+c.dataset.total||1;
        var pct=Math.max(1.5,Math.min(100,left/total*100));
        bar.firstElementChild.style.width=(dead?0:pct)+'%';
        bar.classList.toggle('warn',warn); bar.classList.toggle('dead',dead);
      }
    });
  }
  function cmp(a,b){
    if(state.sort==='exp'){ return (+a.dataset.exp||Infinity)-(+b.dataset.exp||Infinity); }
    if(state.sort==='views'){ return (+b.dataset.views||0)-(+a.dataset.views||0); }
    if(state.sort==='name'){ return a.dataset.title.localeCompare(b.dataset.title,'zh'); }
    return (+b.dataset.created||0)-(+a.dataset.created||0);
  }
  function apply(){
    var q=state.q.toLowerCase(), shown=[], shownCards=0;
    nodes.forEach(function(c){
      var tags=(c.dataset.tags||'').split('|');
      var ok = (state.kind==='all'||c.dataset.kind===state.kind)
        && (!state.tag||tags.indexOf(state.tag)>=0)
        && (!q||(c.dataset.title+' '+tags.join(' ')).toLowerCase().indexOf(q)>=0);
      c.hidden=!ok;
      if(ok){ shown.push(c); if(c.classList.contains('card')) shownCards++; }
    });
    shown.sort(cmp).forEach(function(c,i){ c.style.order=i; });
    if(cnt) cnt.textContent=shownCards+' / '+cards.length+' 个';
    if(blank) blank.hidden=shownCards>0||!cards.length;
  }
  document.querySelectorAll('.seg[data-kind] button').forEach(function(b){
    b.onclick=function(){
      state.kind=b.dataset.v;
      document.querySelectorAll('.seg[data-kind] button').forEach(function(x){x.classList.toggle('on',x===b)});
      apply();
    };
  });
  var q=document.getElementById('q');
  if(q) q.oninput=function(){ state.q=q.value.trim(); apply(); };
  var s=document.getElementById('sort');
  if(s) s.onchange=function(){ state.sort=s.value; apply(); };
  // 卡片 / 列表视图，选过的记在 localStorage
  var vs=document.getElementById('viewseg');
  function setView(v){
    var list = v==='list';
    grid.hidden = list; rows.hidden = !list;
    if(vs) [].forEach.call(vs.children,function(x){ x.classList.toggle('on', x.dataset.view===v); });
    try{ localStorage.setItem('pv_view', v); }catch(e){}
  }
  if(vs){
    var saved='grid';
    try{ saved=localStorage.getItem('pv_view')||'grid'; }catch(e){}
    setView(saved==='list'?'list':'grid');
    [].forEach.call(vs.children,function(b){ b.onclick=function(){ setView(b.dataset.view); }; });
  }
  // 快捷复制链接：成功后打勾 + 冒出「已复制」，失败标红「复制失败」
  function mark(btn, ok){
    btn.classList.remove('done','fail');
    btn.classList.add(ok?'done':'fail');
    var tip=btn.querySelector('.tip');
    if(tip) tip.textContent = ok?'已复制':'复制失败';
    clearTimeout(btn._t);
    btn._t=setTimeout(function(){ btn.classList.remove('done','fail'); },1600);
  }
  function copyText(text){
    if(navigator.clipboard&&window.isSecureContext){
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function(res,rej){
      var ta=document.createElement('textarea');
      ta.value=text; ta.setAttribute('readonly','');
      ta.style.cssText='position:fixed;top:0;left:-9999px;opacity:0';
      document.body.appendChild(ta); ta.select();
      try{ document.execCommand('copy')?res():rej(new Error('copy failed')); }
      catch(e){ rej(e); }
      finally{ document.body.removeChild(ta); }
    });
  }
  [].forEach.call(document.querySelectorAll('.cbtn'),function(b){
    b.addEventListener('click',function(e){
      e.preventDefault(); e.stopPropagation();
      copyText(location.origin+b.dataset.path)
        .then(function(){ mark(b,true); })
        .catch(function(){ mark(b,false); });
    });
  });
  var tb=document.getElementById('tagsbar');
  if(tb){
    var seen={}, order=[];
    cards.forEach(function(c){
      (c.dataset.tags||'').split('|').forEach(function(t){
        if(t&&!seen[t]){ seen[t]=1; order.push(t); }
      });
    });
    order.forEach(function(t){
      var b=document.createElement('button');
      b.textContent=t;
      b.onclick=function(){
        state.tag = state.tag===t ? '' : t;
        [].forEach.call(tb.children,function(x){x.classList.toggle('on',x===b&&!!state.tag)});
        apply();
      };
      tb.appendChild(b);
    });
  }
  tick(); setInterval(tick,1000); apply();
})();
"""

KIND_LABEL = {"static": "静态站", "link": "外链", "zip": "压缩包"}

# 卡片上的复制按钮：复制图标 + 打勾图标（点击后切换）
COPY_ICON = (
    '<svg class="ic-copy" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"'
    ' stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M6.5 6.5V3.8c0-.7.6-1.3 1.3-1.3h4.4c.7 0 1.3.6 1.3 1.3v4.9c0 .7-.6 1.3-1.3 1.3H7.8'
    'c-.7 0-1.3-.6-1.3-1.3Z"/>'
    '<path d="M3.5 7.5h5.2c.7 0 1.3.6 1.3 1.3v4.4c0 .7-.6 1.3-1.3 1.3H3.5c-.7 0-1.3-.6-1.3-1.3V8.8'
    'c0-.7.6-1.3 1.3-1.3Z"/></svg>'
    '<svg class="ic-done" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 8.6 6.4 11.5 12.5 5.2"/></svg>'
)

# 16×16 线性图标（stroke=currentColor），门户作者区用
ICONS = {
    "github": '<path d="M6 5 3 8l3 3"/><path d="M10 5l3 3-3 3"/>',
    "x": '<path d="M4 4l8 8"/><path d="M12 4l-8 8"/>',
    "mail": '<rect x="2.6" y="4" width="10.8" height="8" rx="1.6"/>'
            '<path d="M3.2 5.1 8 8.6l4.8-3.5"/>',
    "globe": '<circle cx="8" cy="8" r="5.4"/><path d="M2.7 8h10.6"/>'
             '<path d="M8 2.6c1.6 1.7 2.4 3.5 2.4 5.4S9.6 12.7 8 13.4C6.4 12.7 5.6 11 5.6 8S6.4 4.3 8 2.6Z"/>',
    "music": '<path d="M9.7 3.2v6.4a2.2 2.2 0 1 1-1.9-2.2"/>'
             '<path d="M9.7 3.2c.3 1.6 1.3 2.5 2.9 2.7"/>',
    "chat": '<path d="M13.4 7.6c0 2.2-2.2 4-4.9 4-.5 0-1-.1-1.5-.2l-2.4 1 .6-1.9'
            'C3.7 9.8 3.1 8.8 3.1 7.6c0-2.2 2.2-4 4.9-4s5.4 1.8 5.4 4Z"/>',
    "play": '<rect x="2.4" y="4.4" width="11.2" height="8" rx="2"/><path d="M6.7 7l2.9 1.6-2.9 1.6Z"/>',
    "star": '<path d="M8 2.8l1.6 3.3 3.6.5-2.6 2.5.6 3.6L8 11l-3.2 1.7.6-3.6L2.8 6.6l3.6-.5Z"/>',
    "rss": '<circle cx="4.7" cy="11.3" r="1.1"/><path d="M3.6 8.3a4.2 4.2 0 0 1 4.1 4.1"/>'
           '<path d="M3.6 4.9a7.6 7.6 0 0 1 7.5 7.5"/>',
    "link": '<path d="M6.6 9.4 9.4 6.6"/><path d="M8.1 4.8l1-1a2.5 2.5 0 0 1 3.5 3.5l-1 1"/>'
            '<path d="M7.9 11.2l-1 1a2.5 2.5 0 0 1-3.5-3.5l1-1"/>',
}

ICON_TPL = (
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" '
    'stroke-linecap="round" stroke-linejoin="round">{}</svg>'
)


def _author_block(author: dict | None) -> str:
    """门户顶部的作者条：头像首字母 + 名字 + 简介 + 一排链接。"""
    if not author:
        return ""
    name = (author.get("name") or "").strip()
    bio = (author.get("bio") or "").strip()
    links = author.get("links") or []
    if not (name or bio or links):
        return ""
    initial = name[:1].upper() if name else "·"
    links_html = ""
    for l in links:
        icon = ICONS.get(l.get("type", "link"), ICONS["link"])
        label = escape(l.get("label") or "")
        url = escape(l.get("url") or "#")
        cls = "alink only-icon" if len(label) > 6 else "alink"
        links_html += (
            f'<a class="{cls}" href="{url}" target="_blank" rel="noopener noreferrer" '
            f'title="{label}">{ICON_TPL.format(icon)}<span>{label}</span></a>'
        )
    meta = f'<b>{escape(name)}</b>' if name else ""
    if bio:
        meta += f'<span title="{escape(bio, quote=True)}">{escape(bio)}</span>'
    return (
        f'<div class="author"><div class="ava">{escape(initial)}</div>'
        f'<div class="am">{meta}</div>'
        f'<div class="alinks">{links_html}</div></div>'
    )


def _remain_text(ms: int) -> str:
    """剩余时长的人话表述（与前端 JS 保持一致，用于首屏无 JS 时也能看）。"""
    if ms <= 0:
        return "已到期"
    s = ms // 1000
    d, h = s // 86400, (s % 86400) // 3600
    if d > 0:
        return f"剩余 {d}天{h}h"
    return f"剩余 {h}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _fmt_day(ts: int) -> str:
    from datetime import datetime

    return datetime.fromtimestamp(ts / 1000).strftime("%m-%d %H:%M")


def portal_page(
    items: list[dict],
    site_title: str,
    subtitle: str,
    server_now: int,
    logged_in: bool,
    author: dict | None = None,
) -> str:
    max_views = max([(p.get("views") or 0) for p in items] or [0]) or 1
    cards: list[str] = []
    rows: list[str] = []
    for p in items:
        exp = p["expires_at"] or 0
        created = p.get("created_at") or server_now
        total = max(1, exp - created) if exp else 0
        if exp:
            left = max(0, exp - server_now)
            pct = max(1.5, min(100.0, left / total * 100))
            cd_cls = "dead" if left <= 0 else ("warn" if left < 2 * 3600_000 else "")
            cd_text = _remain_text(left).replace("剩余 ", "")
        else:
            pct = 100.0
            cd_cls = "perm"
            cd_text = "永久"
        views = p.get("views") or 0
        rpct = max(0, min(100, round(views / max_views * 100)))
        tags_list = p.get("tags") or []
        tags = "".join(f'<span class="tag">{escape(t)}</span>' for t in tags_list[:4])
        owner = escape((p.get("owner") or {}).get("display_name") or "")
        size = _human(p["size_bytes"]) if p["kind"] != "link" else "外链"
        num_cls = "sm" if views >= 1000 else ""
        ends = "" if not exp else f"到期 {_fmt_day(exp)}"
        data_attr = (
            f'data-exp="{exp}" data-total="{total}" data-created="{created}" data-views="{views}" '
            f'data-kind="{p["kind"]}" data-tags="{escape(chr(124).join(tags_list), quote=True)}" '
            f'data-title="{escape(p["title"], quote=True)}"'
        )
        cards.append(
            f"""<div class="card" style="order:0" {data_attr}>
  <a class="hit" href="/v/{p['slug']}" target="_blank" rel="noopener"
     aria-label="打开 {escape(p['title'])}"></a>
  <div class="top">
    <div class="tinfo">
      <div class="name">{escape(p['title'])}<span class="kind">{KIND_LABEL.get(p['kind'], p['kind'])}</span></div>
      <div class="byline"><span>{owner or '—'}</span><span class="dot"></span><span>{size}</span></div>
    </div>
  </div>
  <p class="desc">{escape(p['description'] or '')}</p>
  <div class="tags">{tags}</div>
  <div class="foot">
    <div class="cdrow"><span class="cdlab">剩余</span><span class="cd {cd_cls}">{cd_text}</span>
      <span class="cdend">{ends}</span></div>
    <div class="track"><i style="width:{pct:.1f}%"></i></div>
  </div>
  <button class="cbtn" type="button" data-path="/v/{p['slug']}" title="复制链接" aria-label="复制链接">
    {COPY_ICON}<span class="tip">已复制</span>
  </button>
  <div class="ring" style="--p:{rpct}" title="累计 {views} 次访问（占本站最高值的 {rpct}%）">
    <span class="in"><b class="{num_cls}">{views}</b><i>访问</i></span>
  </div>
</div>"""
        )
        rows.append(
            f"""<div class="row" style="order:0" {data_attr}>
  <a class="hit" href="/v/{p['slug']}" target="_blank" rel="noopener"
     aria-label="打开 {escape(p['title'])}"></a>
  <div class="rmain">
    <span class="rname">{escape(p['title'])}<span class="kind">{KIND_LABEL.get(p['kind'], p['kind'])}</span></span>
    <div class="rmeta">{owner or '—'} · {size}</div>
  </div>
  <p class="rdesc">{escape(p['description'] or '—')}</p>
  <div class="rtags">{tags}</div>
  <div class="rring" style="--p:{rpct}" title="累计 {views} 次访问（占本站最高值的 {rpct}%）">
    <span class="in"><b>{views}</b><i>访问</i></span>
  </div>
  <div class="rfoot">
    <div class="cdrow"><span class="cdlab">剩余</span><span class="cd {cd_cls}">{cd_text}</span>
      <span class="cdend">{ends}</span></div>
    <div class="track"><i style="width:{pct:.1f}%"></i></div>
  </div>
  <button class="cbtn inflow" type="button" data-path="/v/{p['slug']}" title="复制链接" aria-label="复制链接">
    {COPY_ICON}<span class="tip">已复制</span>
  </button>
</div>"""
        )
    body = "".join(cards) or ""
    rowbody = "".join(rows)
    login = '<a class="btn ghost" href="/">进入控制台</a>' if logged_in else ""
    who = _author_block(author)
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(site_title)}</title>
<link rel="icon" href="/favicon.svg">
<meta name="robots" content="noindex">
<style>
{BASE_CSS}
{PORTAL_CSS}
</style></head><body><div class="wrap">
<div class="dock">
<header><div><h1>{escape(site_title)}</h1><div class="sub">{escape(subtitle)}</div></div>{login}</header>
{who}
<div class="tools">
  <div class="seg" data-kind>
    <button class="on" data-v="all">全部</button>
    <button data-v="static">静态站</button>
    <button data-v="link">外链</button>
    <button data-v="zip">压缩包</button>
  </div>
  <span class="spacer"></span>
  <span class="cnt" id="cnt">{len(items)} 个</span>
  <div class="seg icons" id="viewseg" role="group" aria-label="显示方式">
    <button data-view="grid" class="on" title="卡片视图" aria-label="卡片视图">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round">
        <rect x="1.6" y="1.6" width="5.4" height="5.4" rx="1.2"/><rect x="9" y="1.6" width="5.4" height="5.4" rx="1.2"/>
        <rect x="1.6" y="9" width="5.4" height="5.4" rx="1.2"/><rect x="9" y="9" width="5.4" height="5.4" rx="1.2"/>
      </svg>
    </button>
    <button data-view="list" title="列表视图" aria-label="列表视图">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
        <path d="M2 3.5h12M2 8h12M2 12.5h12"/>
      </svg>
    </button>
  </div>
  <select class="sort" id="sort" aria-label="排序">
    <option value="created">最新创建</option>
    <option value="exp">最快到期</option>
    <option value="views">访问最多</option>
    <option value="name">名称 A→Z</option>
  </select>
  <input class="search" id="q" type="search" placeholder="搜索名称或标签" aria-label="搜索">
</div>
<div class="tagsbar" id="tagsbar"></div>
</div>
<div class="grid" id="grid">{body}</div>
<div class="rows" id="rows" hidden>{rowbody}</div>
<div class="blank" id="blank"{' hidden' if items else ''}>{'没有匹配的项目，换个筛选条件试试' if items else '暂无公开项目'}</div>
</div>
<script>
{PORTAL_JS.replace("__NOW__", str(server_now))}
</script></body></html>"""



def error_page(code: int, title: str, desc: str, back: str = "/") -> str:
    accent = "#b45309" if code == 410 else "#14161a"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{code} · {escape(title)}</title>
<link rel="icon" href="/favicon.svg">
<style>
{BASE_CSS}
body{{height:100vh;display:flex;align-items:center;justify-content:center;
background:radial-gradient(120% 90% at 50% 0%,#fbfcfb,#eff1ef)}}
.box{{text-align:center;padding:40px 44px;background:#fff;border:1px solid rgba(20,22,26,.08);
border-radius:14px;box-shadow:0 24px 60px -40px rgba(20,22,26,.5);max-width:420px}}
.code{{font:600 40px/1 {MONO};color:{accent};letter-spacing:-.03em}}
h1{{font-size:16px;margin:14px 0 6px;letter-spacing:-.01em}}
p{{color:#7b8189;font-size:13px;line-height:1.6;margin:0 0 18px}}
a{{display:inline-flex;align-items:center;height:32px;padding:0 14px;border-radius:8px;background:#14161a;
color:#fff;font-size:12.5px;font-weight:600}}
</style></head><body><div class="box">
<div class="code">{code}</div><h1>{escape(title)}</h1><p>{escape(desc)}</p><a href="{escape(back)}">返回</a>
</div></body></html>"""
