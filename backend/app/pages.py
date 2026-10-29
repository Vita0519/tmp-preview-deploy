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
.wrap{max-width:1080px;margin:0 auto;padding:44px 20px 80px}
header{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:18px}
h1{margin:0;font-size:26px;letter-spacing:-.02em}
.sub{color:#7b8189;font-size:12.5px;margin-top:5px}
.btn{height:30px;display:inline-flex;align-items:center;padding:0 12px;border-radius:8px;font-size:12.5px;
font-weight:600;border:1px solid rgba(20,22,26,.14);background:#fff;color:#2a2f36}
.tools{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.seg{display:inline-flex;gap:2px;padding:2px;border-radius:9px;background:#eaecea;
border:1px solid rgba(20,22,26,.06)}
.seg button{height:26px;padding:0 11px;border:0;border-radius:7px;background:transparent;
font:600 12px/1 inherit;color:#5b636d;cursor:pointer;transition:background .16s,color .16s,box-shadow .16s}
.seg button:hover{color:#14161a}
.seg button.on{background:#fff;color:#14161a;box-shadow:0 1px 2px rgba(20,22,26,.1)}
.tools .spacer{flex:1 1 auto}
.search{height:30px;width:210px;padding:0 10px;border-radius:8px;border:1px solid rgba(20,22,26,.14);
background:#fff;font-size:12.5px;color:#14161a;outline:none;transition:border-color .16s,box-shadow .16s}
.search:focus{border-color:rgba(15,118,110,.5);box-shadow:0 0 0 3px rgba(15,118,110,.1)}
.sort{height:30px;padding:0 8px;border-radius:8px;border:1px solid rgba(20,22,26,.14);background:#fff;
font-size:12.5px;color:#2a2f36;outline:none;cursor:pointer}
.sort:focus{border-color:rgba(15,118,110,.5)}
.cnt{font-size:11.5px;color:#8a9099;font-variant-numeric:tabular-nums;white-space:nowrap}
.tagsbar{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:0 0 16px;min-height:0}
.tagsbar:empty{display:none}
.tagsbar button{height:22px;padding:0 8px;border-radius:6px;border:1px solid rgba(20,22,26,.08);
background:#f4f6f4;color:#5b636d;font:600 11px/1 inherit;cursor:pointer;transition:.16s}
.tagsbar button:hover{background:#eef2f0;color:#14161a}
.tagsbar button.on{background:#0f766e;border-color:#0f766e;color:#fff}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
.card{display:block;background:#fff;border:1px solid rgba(20,22,26,.09);border-radius:12px;padding:14px 15px 13px;
transition:transform .18s cubic-bezier(.2,.8,.2,1),box-shadow .18s,border-color .18s}
.card[hidden]{display:none}
.card:hover{transform:translateY(-2px);box-shadow:0 12px 28px -18px rgba(20,22,26,.42);border-color:rgba(15,118,110,.32)}
.top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
.name{font-weight:650;font-size:14.5px;letter-spacing:-.01em;color:#14161a;min-width:0;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kind{font-size:10px;font-weight:600;color:#7b8189;background:#f3f5f3;border:1px solid rgba(20,22,26,.06);
border-radius:5px;padding:1px 5px;margin-left:6px;vertical-align:1px}
.cv{flex:0 0 auto;font-size:11px;font-weight:600;color:#0f766e;background:#eff4f2;border-radius:999px;
padding:3px 8px;white-space:nowrap;font-variant-numeric:tabular-nums}
.cv.perm{color:#3a4a63;background:#eef2f8}
.cv.warn{color:#b45309;background:#fdf3e7}
.cv.dead{color:#b42318;background:#fdeceb}
.desc{margin:7px 0 9px;color:#5b636d;font-size:12.5px;line-height:1.55;display:-webkit-box;
-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:19px}
.track{height:3px;border-radius:99px;background:#eef1ef;overflow:hidden}
.track > i{display:block;height:100%;border-radius:99px;background:#0f766e;transition:width .5s ease}
.track.warn > i{background:#b45309}
.track.dead > i{background:#b42318}
.meta{display:flex;align-items:center;gap:7px;margin-top:9px;font-size:11.5px;color:#8a9099;
font-variant-numeric:tabular-nums}
.meta .dot{width:3px;height:3px;border-radius:50%;background:#c8ccd1;flex:0 0 auto}
.meta .who{max-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.meta .right{margin-left:auto;display:flex;align-items:center;gap:6px;flex:0 0 auto}
.meta .right b{font-weight:650;color:#5b636d;font-variant-numeric:tabular-nums}
.vbar{width:34px;height:3px;border-radius:99px;background:#eef1ef;overflow:hidden}
.vbar > i{display:block;height:100%;border-radius:99px;background:#b6c2bd}
.tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:9px}
.tags:empty{display:none}
.tag{font-size:10.5px;padding:2px 7px;border-radius:5px;background:#f3f5f3;color:#5b636d;
border:1px solid rgba(20,22,26,.06)}
.blank{grid-column:1/-1;text-align:center;color:#8a9099;padding:56px 0;
border:1px dashed rgba(20,22,26,.14);border-radius:12px;font-size:13px}
@media (max-width:620px){
  .wrap{padding:28px 14px 60px}
  h1{font-size:22px}
  .search{width:100%;order:9}
  .tools .spacer{display:none}
  .grid{grid-template-columns:1fr}
}
"""

PORTAL_JS = """
(function(){
  var NOW=__NOW__, off=0;
  var grid=document.getElementById('grid');
  var cards=[].slice.call(grid.querySelectorAll('.card'));
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
    cards.forEach(function(c){
      var exp=+c.dataset.exp; if(!exp) return;
      var left=exp-now, pill=c.querySelector('.cv'), bar=c.querySelector('.track');
      var warn=left>0&&left<2*3600e3, dead=left<=0;
      if(pill){
        pill.textContent = dead ? '已到期' : '剩余 '+fmt(left);
        pill.classList.toggle('warn',warn); pill.classList.toggle('dead',dead);
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
    var q=state.q.toLowerCase(), shown=[];
    cards.forEach(function(c){
      var tags=(c.dataset.tags||'').split('|');
      var ok = (state.kind==='all'||c.dataset.kind===state.kind)
        && (!state.tag||tags.indexOf(state.tag)>=0)
        && (!q||(c.dataset.title+' '+tags.join(' ')).toLowerCase().indexOf(q)>=0);
      c.hidden=!ok; if(ok) shown.push(c);
    });
    shown.sort(cmp).forEach(function(c,i){ c.style.order=i; });
    if(cnt) cnt.textContent=shown.length+' / '+cards.length+' 个';
    if(blank) blank.hidden=shown.length>0||!cards.length;
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


def _remain_text(ms: int) -> str:
    """剩余时长的人话表述（与前端 JS 保持一致，用于首屏无 JS 时也能看）。"""
    if ms <= 0:
        return "已到期"
    s = ms // 1000
    d, h = s // 86400, (s % 86400) // 3600
    if d > 0:
        return f"剩余 {d}天{h}h"
    return f"剩余 {h}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def portal_page(items: list[dict], site_title: str, subtitle: str, server_now: int, logged_in: bool) -> str:
    max_views = max([(p.get("views") or 0) for p in items] or [0]) or 1
    cards = []
    for p in items:
        exp = p["expires_at"] or 0
        created = p.get("created_at") or server_now
        total = max(1, exp - created) if exp else 0
        if exp:
            left = max(0, exp - server_now)
            pct = max(1.5, min(100.0, left / total * 100))
            pill_cls = "dead" if left <= 0 else ("warn" if left < 2 * 3600_000 else "")
            pill = _remain_text(left)
        else:
            pct = 100.0
            pill_cls = "perm"
            pill = "永久"
        views = p.get("views") or 0
        vpct = max(4, round(views / max_views * 100))
        tags_list = p.get("tags") or []
        tags = "".join(f'<span class="tag">{escape(t)}</span>' for t in tags_list[:4])
        owner = escape((p.get("owner") or {}).get("display_name") or "")
        cards.append(
            f"""<a class="card" href="/v/{p['slug']}" target="_blank" rel="noopener" style="order:0"
   data-exp="{exp}" data-total="{total}" data-created="{created}" data-views="{views}"
   data-kind="{p['kind']}" data-tags="{escape('|'.join(tags_list), quote=True)}"
   data-title="{escape(p['title'], quote=True)}">
  <div class="top"><div class="name">{escape(p['title'])}<span class="kind">{KIND_LABEL.get(p['kind'], p['kind'])}</span></div>
  <span class="cv {pill_cls}">{pill}</span></div>
  <p class="desc">{escape(p['description'] or '')}</p>
  <div class="track"><i style="width:{pct:.1f}%"></i></div>
  <div class="meta">
    <span class="who">{owner or '—'}</span><span class="dot"></span>
    <span>{_human(p['size_bytes']) if p['kind'] != 'link' else '外链'}</span>
    <span class="right"><b>{views}</b> 次访问<span class="vbar"><i style="width:{vpct}%"></i></span></span>
  </div>
  <div class="tags">{tags}</div>
</a>"""
        )
    body = "".join(cards) or '<div class="blank">暂无公开项目</div>'
    login = '<a class="btn ghost" href="/">进入控制台</a>' if logged_in else ""
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(site_title)}</title>
<meta name="robots" content="noindex">
<style>
{BASE_CSS}
{PORTAL_CSS}
</style></head><body><div class="wrap">
<header><div><h1>{escape(site_title)}</h1><div class="sub">{escape(subtitle)}</div></div>{login}</header>
<div class="tools">
  <div class="seg" data-kind>
    <button class="on" data-v="all">全部</button>
    <button data-v="static">静态站</button>
    <button data-v="link">外链</button>
    <button data-v="zip">压缩包</button>
  </div>
  <span class="spacer"></span>
  <span class="cnt" id="cnt">{len(items)} 个</span>
  <select class="sort" id="sort" aria-label="排序">
    <option value="created">最新创建</option>
    <option value="exp">最快到期</option>
    <option value="views">访问最多</option>
    <option value="name">名称 A→Z</option>
  </select>
  <input class="search" id="q" type="search" placeholder="搜索名称或标签" aria-label="搜索">
</div>
<div class="tagsbar" id="tagsbar"></div>
<div class="grid" id="grid">{body}</div>
<div class="blank" id="blank" hidden>没有匹配的项目，换个筛选条件试试</div>
</div>
<script>
{PORTAL_JS.replace("__NOW__", str(server_now))}
</script></body></html>"""



def error_page(code: int, title: str, desc: str, back: str = "/") -> str:
    accent = "#b45309" if code == 410 else "#14161a"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{code} · {escape(title)}</title>
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
