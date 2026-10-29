/**
 * /admin 管理页 —— 同一个 Worker 动态返回（无需额外路由）
 * 支持：口令登录、实时剩余时间、改 TTL（小时）、立即删除
 */
export function adminHTML(token) {
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>项目管理 · 临时预览</title>
<style>
*{box-sizing:border-box}
body{margin:0;min-height:100vh;font:15px/1.5 -apple-system,"PingFang SC","Microsoft YaHei",system-ui,sans-serif;
background:linear-gradient(160deg,#f6f8fc,#eef2f9 60%,#e9eef7);color:#0f172a;
display:flex;align-items:flex-start;justify-content:center;padding:12px 20px 40px}
.wrap{width:100%;max-width:1480px}
/* 搜索以上区域滚动时固定 */
.stickytop{position:sticky;top:0;z-index:60;margin:0 -12px;padding:10px 12px 12px;
background:linear-gradient(160deg,rgba(246,248,252,.92),rgba(238,242,249,.92) 60%,rgba(233,238,247,.92));
backdrop-filter:blur(14px) saturate(160%);border-bottom:1px solid rgba(148,163,184,.22);
box-shadow:0 10px 26px -20px rgba(15,23,42,.28);border-radius:0 0 16px 16px}
.topbar{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.topbar .backbtn{display:inline-flex;align-items:center;gap:7px;background:rgba(255,255,255,.9);color:#0f172a;
border:1px solid rgba(148,163,184,.5);border-radius:12px;padding:9px 15px;font-size:13.5px;font-weight:600;
text-decoration:none;cursor:pointer;transition:.18s;box-shadow:0 2px 8px -6px rgba(15,23,42,.3)}
.topbar .backbtn:hover{background:#fff;border-color:#2563eb;color:#2563eb;transform:translateX(-1px)}
.topbar .backbtn .arw{font-size:16px;line-height:1}
.topbar .brand{margin-left:auto;display:flex;align-items:center;gap:8px}
.topbar .brand .dot{width:8px;height:8px;border-radius:50%;background:#059669;box-shadow:0 0 0 3px rgba(5,150,105,.15)}
.topbar .brand .tt{font-size:13px;font-weight:600;color:#334155}
h1{font-size:22px;margin:0 0 4px;display:flex;align-items:center;gap:10px}
h1 .gear{font-size:18px;opacity:.85}
.sub{color:#64748b;font-size:13px;margin-bottom:14px}
.panel{background:rgba(255,255,255,.72);border:1px solid rgba(148,163,184,.28);border-radius:16px;
padding:14px 16px;margin-bottom:12px;box-shadow:0 6px 22px -16px rgba(15,23,42,.28)}
.panel .ptitle{font-size:12px;font-weight:700;letter-spacing:.04em;color:#94a3b8;text-transform:uppercase;margin:0 0 10px}
.bar{display:flex;gap:6px;margin-bottom:0;flex-wrap:wrap;align-items:center}
.bar .bargap{flex:1 1 auto}
input,button,select{font:14px inherit;padding:8px 11px;border-radius:10px;border:1px solid rgba(148,163,184,.45);background:#fff}
input{min-width:130px}
button{cursor:pointer;background:#0f172a;color:#fff;border:0;font-weight:600}
button.ghost{background:#fff;color:#0f172a;border:1px solid rgba(148,163,184,.5)}
button.danger{background:#dc2626}
table{width:100%;border-collapse:collapse;table-layout:fixed;background:rgba(255,255,255,.75);border-radius:14px;overflow:hidden;
box-shadow:0 6px 22px -12px rgba(15,23,42,.25)}
button.ghost.on{background:#059669;color:#fff;border-color:#059669}
td.ops{padding:8px 12px;overflow:visible}
.opsin{display:flex;flex-wrap:wrap;gap:4px;align-items:center;justify-content:flex-start}
.opsin button{margin:0;padding:3px 7px;font-size:11.5px;line-height:1.35;flex:1 1 auto;text-align:center;white-space:nowrap;border-radius:8px}
.opsin .opeset{display:inline-flex;align-items:center;gap:3px;flex:1 1 auto}
.opsin .mini{height:26px}
/* 移动端：表格变卡片，按钮两行不拥挤 */
@media(max-width:720px){
  body{padding:18px 12px}
  .wrap{max-width:100%}
  .topbar{flex-wrap:wrap;gap:8px;margin-bottom:16px}
  .topbar .brand{margin-left:0}
  .topbar .backbtn{font-size:13px;padding:8px 13px}
  h1{font-size:19px}
  .panel{padding:12px 13px;border-radius:14px}
  .bar{gap:6px}
  .bar input,.bar select,.bar button{flex:1 1 auto}
  .tokwrap{flex:1 1 100%}
  .tokwrap input{flex:1 1 auto;min-width:0}
  table,thead,tbody,th,td,tr{display:block}
  thead{display:none}
  tr{background:#fff;border:1px solid rgba(148,163,184,.25);border-radius:14px;margin-bottom:12px;padding:12px 14px;height:auto;
      box-shadow:0 4px 14px -10px rgba(15,23,42,.3)}
  td{border:0;padding:3px 0;display:flex;justify-content:space-between;gap:10px;white-space:normal!important}
  td::before{content:attr(data-l);color:#94a3b8;font-size:12px;flex:0 0 auto}
  td.tdname{display:block;font-size:15px;padding-bottom:8px;border-bottom:1px solid rgba(148,163,184,.15);margin-bottom:6px}
  td.tdname::before{display:none}
  td.tdops{display:block;padding-top:0}
  td.tdops::before{display:none}
  .opsin{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding-top:10px}
  .opsin .opeset{display:contents}
  .opsin button{margin:0;width:100%;text-align:center;padding:10px 6px;font-size:13px;flex:none}
  .opsin .mini{width:100%!important;min-width:0!important}
}
#out{margin-top:14px}
.count{color:#64748b;font-size:13px;white-space:nowrap;align-self:center}
.searchrow{display:flex;gap:8px;align-items:center;margin-bottom:0;flex-wrap:wrap}
.searchrow .count{margin-left:auto}
.searchwrap2{position:relative;flex:0 1 220px;min-width:150px}
.searchwrap2 .sic2{position:absolute;left:11px;top:50%;transform:translateY(-50%);font-size:12.5px;color:#94a3b8;pointer-events:none}
.searchwrap2 input{width:100%;padding:8px 12px 8px 32px;border-radius:10px;border:1px solid rgba(148,163,184,.45);background:rgba(255,255,255,.9);font-size:13px;outline:none;min-width:0}
.searchwrap2 input:focus{border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.12)}
.chips{display:flex;gap:7px;flex-wrap:wrap;align-items:center}
.chip{padding:5px 11px;border-radius:999px;font-size:11.5px;font-weight:600;cursor:pointer;user-select:none;
background:rgba(255,255,255,.75);color:#64748b;border:1px solid rgba(148,163,184,.4);transition:.15s}
.chip:hover{border-color:#2563eb;color:#2563eb}
.chip.on{background:#0f172a;color:#fff;border-color:#0f172a}
.chip .n{opacity:.7;font-weight:500;margin-left:3px}
.empty{padding:36px;text-align:center;color:#94a3b8;background:rgba(255,255,255,.6);border-radius:14px;
border:1px dashed rgba(148,163,184,.5)}
th,td{text-align:left;padding:8px 12px;font-size:13px;border-bottom:1px solid rgba(148,163,184,.18);vertical-align:middle}
thead th{padding-top:10px;padding-bottom:10px}
@media(min-width:721px){tbody tr{height:52px}}
th{white-space:nowrap}
td:nth-child(3),td:nth-child(4),td:nth-child(5),td:nth-child(6){white-space:nowrap}
th:nth-child(3),th:nth-child(4),th:nth-child(5),th:nth-child(6){white-space:nowrap}
.ghost.on{white-space:nowrap}
th{background:rgba(241,245,249,.8);font-weight:600;color:#475569;font-size:12px}
tr:last-child td{border-bottom:0}
.mono{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:#2563eb;text-decoration:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block;max-width:100%;vertical-align:middle}
td.tdname{min-width:0;overflow:hidden;text-overflow:ellipsis}
td{overflow:hidden;vertical-align:middle}
tr{height:auto}
.ttl{font-weight:600;color:#b45309;white-space:nowrap}
.ttl.hot{color:#dc2626}
.ttl.dead{color:#94a3b8;text-decoration:line-through}
.hint{font-size:12px;color:#94a3b8;margin-top:14px}
.tag{font-size:11px;padding:2px 8px;border-radius:99px;background:rgba(37,99,235,.1);color:#2563eb;white-space:nowrap}
.tag.zip{background:rgba(5,150,105,.12);color:#059669}
.tag.perm{background:rgba(37,99,235,.12);color:#2563eb}
.tag.block{background:rgba(245,158,11,.14);color:#b45309}
.tag.del{background:rgba(220,38,38,.12);color:#dc2626}
.tag.dash{background:transparent;color:#cbd5e1}
select{min-width:96px}
.hide{display:none!important}
/* 新增项目面板 */
#addbox{display:none;background:rgba(255,255,255,.88);border:1px solid rgba(148,163,184,.35);border-radius:16px;
padding:18px 18px 16px;margin:14px 0 18px;box-shadow:0 8px 26px -18px rgba(15,23,42,.35)}
#addbox.open{display:block}
.tokwrap{position:relative;display:inline-flex;align-items:center;flex:0 1 auto}
.tokwrap input{padding-right:38px}
.eye{position:absolute;right:6px;background:transparent;border:0;color:#64748b;font-size:15px;line-height:1;
padding:5px 7px;border-radius:8px;cursor:pointer}
.eye:hover{background:rgba(148,163,184,.18)}
#addbox h2{font-size:15px;margin:0 0 14px;display:flex;align-items:center}
#addbox h2 .closebtn{margin-left:auto;background:transparent;border:0;color:#64748b;font-size:18px;cursor:pointer;padding:2px 8px;border-radius:8px}
#addbox h2 .closebtn:hover{background:rgba(148,163,184,.18);color:#0f172a}
.frm{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.frm .full{grid-column:1/-1}
.frm label{display:block;font-size:12px;color:#64748b;margin-bottom:4px}
.frm input,.frm select{width:100%;min-width:0}
.drop{border:1.5px dashed rgba(148,163,184,.6);border-radius:12px;padding:20px;text-align:center;color:#64748b;
font-size:13px;cursor:pointer;transition:.2s;background:rgba(248,250,252,.7)}
.drop:hover,.drop.over{border-color:#2563eb;background:rgba(37,99,235,.05);color:#2563eb}
.filelist{font-size:12px;color:#475569;margin-top:8px;max-height:120px;overflow:auto}
.filelist div{padding:2px 0;display:flex;justify-content:space-between;gap:10px}
.dl-file{color:#dc2626;cursor:pointer}
.addrow{display:flex;gap:10px;margin-top:12px;align-items:center;flex-wrap:wrap}
.aok{color:#059669;font-weight:600;font-size:13px}
.aerr{color:#dc2626;font-weight:600;font-size:13px}
.mini{width:44px!important;min-width:44px!important;padding:3px 5px!important;font-size:11.5px!important;line-height:1.35!important;height:26px!important;border-radius:8px!important}
@media(max-width:720px){.frm{grid-template-columns:1fr}}
</style></head><body><div class="wrap">
<div class="stickytop">
<div class="topbar">
  <a class="backbtn" href="/" title="返回临时预览服务首页"><span class="arw">←</span> 返回预览服务</a>
  <div class="brand"><span class="dot"></span><span class="tt">管理后台</span></div>
</div>
<h1><span class="gear">⚙</span>项目管理</h1>
<div class="sub">时长可设具体小时或永久 · 下载默认关闭 · 到期可选「停止访问」或「删除项目」 · 实时刷新</div>
<div class="panel">
  <div class="ptitle">操作</div>
  <div class="bar">
    <span class="tokwrap"><input id="tok" type="password" placeholder="管理口令" value="${token ? esc(token) : ''}" style="min-width:120px;flex:0 1 150px"><button type="button" class="eye" id="eyebtn" title="显示/隐藏口令" onclick="toggleEye()">👁</button></span>
    <input id="hours" type="number" min="0" step="1" value="24" style="min-width:64px;flex:0 0 64px" title="小时，0=永久">
    <select id="preset" onchange="pickPreset()">
      <option value="">选择时长…</option>
      <option value="1">1 小时</option>
      <option value="6">6 小时</option>
      <option value="12">12 小时</option>
      <option value="24" selected>24 小时</option>
      <option value="72">3 天</option>
      <option value="168">7 天</option>
      <option value="720">30 天</option>
      <option value="0">永久</option>
    </select>
    <button onclick="load()">读取 / 刷新</button>
    <span class="bargap"></span>
    <button class="ghost" onclick="toggleAdd()" id="addbtn">+ 新增项目</button>
    <button class="ghost" onclick="ttlAll()">全部重设为该时长</button>
    <button class="ghost hide" id="lk" onclick="logout()">退出登录</button>
  </div>
</div>
<div class="searchrow">
  <div class="searchwrap2"><span class="sic2">🔍</span><input id="aq" placeholder="搜索项目名 / slug…" oninput="render()"></div>
  <select id="asort" onchange="window.__asort()" title="排序方式" style="padding:7px 10px;border-radius:10px;border:1px solid rgba(148,163,184,.45);background:#fff;font-size:12.5px;cursor:pointer">
    <option value="views">按访问次数</option>
    <option value="time">按创建时间</option>
  </select>
  <div class="chips" id="chips"></div>
  <span class="count" id="cnt"></span>
</div>
</div>
<div id="addbox">
  <h2>新增项目（URL / 文件）<button type="button" class="closebtn" title="收起" onclick="toggleAdd()">✕</button></h2>
  <div class="frm">
    <div><label>显示名</label><input id="f_name" placeholder="例如：客户验收演示"></div>
    <div><label>URL 段（留空自动生成）</label><input id="f_slug" placeholder="例如：demo-2026"></div>
    <div class="full"><label>说明（可选）</label><input id="f_desc" placeholder="一句话描述"></div>
    <div class="full"><label>外部链接 URL（填了这个就建“外链卡片”，无需选文件）</label><input id="f_link" placeholder="例如：umami-three-taupe.vercel.app"></div>
    <div><label>时长（小时，0=永久）</label><input id="f_ttl" type="number" min="0" step="1" value="24"></div>
    <div><label>到期后</label><select id="f_act"><option value="block">停止访问（保留文件）</option><option value="delete">删除项目</option></select></div>
    <div><label>开放下载</label><select id="f_dl"><option value="0">不开放</option><option value="1">开放 zip 下载</option></select></div>
    <div><label>打包 zip</label><select id="f_zip"><option value="1">生成 zip（需开放下载时选它）</option><option value="0">不生成</option></select></div>
    <div class="full">
      <label>项目文件（选择文件夹或文件，会保留目录结构）</label>
      <div class="drop" id="drop"><div>点击选文件夹，或拖拽文件/文件夹到此处</div><div style="font-size:12px;margin-top:6px"><span class="plain" id="pickfiles" style="color:#2563eb;cursor:pointer;text-decoration:underline">或点这里选单个/多个文件</span></div></div>
      <input id="f_files" type="file" multiple webkitdirectory style="display:none">
      <input id="f_files2" type="file" multiple style="display:none">
      <div class="filelist" id="flist"></div>
    </div>
  </div>
  <div class="addrow">
    <button onclick="doUpload()" id="upbtn">上传并创建</button>
    <button class="ghost" onclick="doLink()" id="lkbtn">创建外链</button>
    <span id="amsg"></span>
  </div>
</div>
<div id="out"></div>
<div class="hint">口令来自 Worker 环境变量 ADMIN_TOKEN；登录状态自动保存 30 天，下次免输。</div>

<script>
var T={};
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function absTime(ts){
  if(!ts) return '—';
  var d=new Date(ts);
  function p(n){return String(n).padStart(2,'0');}
  return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())+' '+p(d.getHours())+':'+p(d.getMinutes());
}
function tok(){return document.getElementById('tok').value.trim();}
function saveTok(t){
  try{localStorage.setItem('pp_tok',t);}catch(e){}
  // 同时种 Cookie（页面 JS 能写非 HttpOnly），下次打开免输
  document.cookie='pp_tok='+encodeURIComponent(t)+'; Path=/; Max-Age=2592000; SameSite=Lax'+(location.protocol==='https:'?'; Secure':'');
}
function logout(){
  try{localStorage.removeItem('pp_tok');}catch(e){}
  document.cookie='pp_tok=; Path=/; Max-Age=0; SameSite=Lax';
  location.href='/admin';
}
function hours(){var v=document.getElementById('hours').value;var n=parseFloat(v);return isNaN(n)?24:n;}
function fmt(ms){
  if(ms<=0) return '已到期';
  var d=Math.floor(ms/86400000),h=Math.floor(ms%86400000/3600000),
      m=Math.floor(ms%3600000/60000),s=Math.floor(ms%60000/1000);
  if(d>0) return d+'天'+h+'小时';
  if(h>0) return h+'h'+String(m).padStart(2,'0')+'m'+String(s).padStart(2,'0')+'s';
  return m+'m'+String(s).padStart(2,'0')+'s';
}
function api(path,body){
  return fetch(path,{method:body?'POST':'GET',headers:{'content-type':'application/json','x-admin-token':tok()},
    body:body?JSON.stringify(body):undefined}).then(function(r){return r.json();});
}
function load(){
  api('/api/admin/list').then(function(d){
    if(!d.ok){
      var o=document.getElementById('out');
      if(!o.dataset.err){
        o.dataset.err='1';
        o.innerHTML='<p style="color:#dc2626">口令错误或无权限，请在左上输入正确口令。</p>';
      }
      var lo=document.getElementById('lk'); if(lo) lo.classList.add('hide');
      return;
    }
    var o=document.getElementById('out'); o.dataset.err='';
    saveTok(tok());
    var lk=document.getElementById('lk'); if(lk) lk.classList.remove('hide');
    T=d; render();
    if(!window._t){window._t=setInterval(render,1000);}
  });
}
window.__asort=function(){
  window.__asortv=document.getElementById('asort').value;
  try{localStorage.setItem('pa_sort',window.__asortv);}catch(e){}
  render();
};
function render(){
  if(!T.projects){return;}
  // 若用户正在输入/聚焦，暂不重建整个表格，避免每钞刷新抹掉输入
  var ae=document.activeElement;
  if(ae && ae.closest && ae.closest('#out') && (ae.tagName==='INPUT'||ae.tagName==='SELECT')){
    refreshTimers(); return;
  }
  var now=Date.now();
  var q=(document.getElementById('aq').value||'').trim().toLowerCase();
  var base=q?T.projects.filter(function(p){
    return ((p.name||'')+' '+(p.slug||'')).toLowerCase().indexOf(q)>=0;
  }):T.projects;
  // 快捷标签过滤
  if(window._tag){
    var tg=window._tag;
    base=base.filter(function(p){
      var perm=p.permanent||!p.expireAt;
      if(tg==='外链') return !!p.link;
      if(tg==='永久') return perm;
      if(tg==='限时') return !perm;
      if(tg==='可下载') return !!(p.allowDownload&&p.zipName);
      return ((p.name||'')+' '+(p.slug||'')).toLowerCase().indexOf(tg.toLowerCase())>=0;
    });
  }
  var list=base.slice().sort(function(a,b){
    var sm=window.__asortv||'views';
    if(sm==='time') return (b.createdAt||0)-(a.createdAt||0);
    var dv=(b.views||0)-(a.views||0);
    return dv ? dv : ((b.createdAt||0)-(a.createdAt||0));
  });
  var cnt=document.getElementById('cnt');
  if(cnt) cnt.textContent=(list.length===T.projects.length?'共 '+T.projects.length+' 个项目':list.length+' / '+T.projects.length+' 个项目');
  renderChips();
  var rows=list.map(function(p){
    var perm=p.permanent||!p.expireAt;
    var remain=perm?0:(p.expireAt-now);
    var cls=(perm||remain<=0)?'ttl dead':(remain<6*3600e3?'ttl hot':'ttl');
    var ttlTxt=perm?'永久':fmt(remain);
    var act=p.expireAction||'block';
    var s=esc(p.slug);
    var isLink=!!p.link;
    var previewCell=isLink?('<a class="mono" href="'+esc(p.link)+'" target="_blank" rel="noopener">'+esc(p.link)+'</a> <span class="tag" style="background:#eef2ff;color:#4f46e5">外链</span>'):('<a class="mono" href="/'+s+'/" target="_blank">/'+s+'/</a>');
    return '<tr><td class="tdname"><div style="font-weight:600;line-height:1.25">'+esc(p.name)+'</div><div style="color:#94a3b8;font-size:11.5px;line-height:1.2">'+s+'</div></td>'+
      '<td data-l="预览">'+previewCell+'</td>'+
      '<td data-l="访问">'+(isLink?'<span class="tag dash">—</span>':(p.views||0))+'</td>'+
      '<td data-l="创建时间"><span style="color:#64748b;font-size:12px">'+absTime(p.createdAt)+'</span></td>'+
      '<td data-l="文件">'+(isLink?'<span class="tag dash">—</span>':(p.files||0))+'</td>'+
      '<td data-l="zip">'+(isLink?'<span class="tag dash">—</span>':(p.zipName?'<span class="tag zip">有zip</span>':'<span class="tag">无</span>'))+'</td>'+
      '<td data-l="下载">'+(isLink?'<span class="tag dash">—</span>':(p.allowDownload?'<button class="ghost on" data-act="dl" data-slug="'+s+'" data-val="0">开放中 ✕</button>':'<button class="ghost" data-act="dl" data-slug="'+s+'" data-val="1">已关闭 ↻</button>'))+'</td>'+
      '<td data-l="到期行为">'+(act==='delete'?'<span class="tag del">删除项目</span>':'<span class="tag block">停访保留</span>')+'</td>'+
      '<td class="'+cls+'" data-slug="'+s+'" data-l="剩余">'+ttlTxt+'</td>'+
      '<td class="ops tdops"><div class="opsin"><span class="opeset"><input class="mini" data-slug="'+s+'" type="number" min="0" step="1" value="'+rowHours(p)+'" title="小时，0=永久"><button class="ghost" data-act="ttl" data-slug="'+s+'">设为</button></span>'+
      '<button class="ghost" data-act="perm" data-slug="'+s+'">'+(perm?'取消永久':'设为永久')+'</button>'+
      '<button class="ghost" data-act="expire" data-slug="'+s+'" data-val="'+(act==='delete'?'block':'delete')+'">到期'+(act==='delete'?'停访':'删除')+'</button>'+
      '<button class="ghost" data-act="views" data-slug="'+s+'" title="访问次数清零">清零</button>'+
      '<button class="danger" data-act="del" data-slug="'+s+'">删除</button></div></td></tr>';
  }).join('');
  document.getElementById('out').innerHTML=list.length
    ? '<table><colgroup><col style="width:10%"><col style="width:13%"><col style="width:6%"><col style="width:9%"><col style="width:5%"><col style="width:5%"><col style="width:8%"><col style="width:8%"><col style="width:7%"><col style="width:29%"></colgroup><thead><tr><th>项目</th><th>预览</th><th>访问</th><th>创建时间</th><th>文件</th><th>zip</th><th>下载</th><th>到期行为</th><th>剩余</th><th>操作</th></tr></thead><tbody>'+rows+'</tbody></table>'
    : '<div class="empty">'+(T.projects.length?'没有匹配的项目':'暂无项目')+'</div>';
}
function refreshTimers(){
  var now=Date.now();
  var cells=document.querySelectorAll('#out td.ttl');
  cells.forEach(function(td){
    var slug=td.dataset.slug; var p=T.projects.find(function(x){return x.slug===slug;});
    if(!p) return;
    var perm=p.permanent||!p.expireAt;
    var remain=perm?0:(p.expireAt-now);
    td.className=(perm||remain<=0)?'ttl dead':(remain<6*3600e3?'ttl hot':'ttl');
    td.textContent=perm?'永久':fmt(remain);
  });
}
function renderChips(){
  var el=document.getElementById('chips'); if(!el||!T.projects) return;
  var list=T.projects;
  var hasLink=list.some(function(p){return p.link;});
  var hasPerm=list.some(function(p){return p.permanent||!p.expireAt;});
  var hasExp=list.some(function(p){return !(p.permanent||!p.expireAt);});
  var hasDl=list.some(function(p){return p.allowDownload&&p.zipName;});
  var chip=[];
  if(hasLink) chip.push({t:'外链',n:list.filter(function(p){return p.link;}).length});
  if(hasPerm) chip.push({t:'永久',n:list.filter(function(p){return p.permanent||!p.expireAt;}).length});
  if(hasExp) chip.push({t:'限时',n:list.filter(function(p){return !(p.permanent||!p.expireAt);}).length});
  if(hasDl) chip.push({t:'可下载',n:list.filter(function(p){return p.allowDownload&&p.zipName;}).length});
  el.innerHTML=chip.map(function(c){
    return '<span class="chip'+(window._tag===c.t?' on':'')+'" data-tag="'+c.t+'">'+c.t+'<span class="n">'+c.n+'</span></span>';
  }).join('');
  el.onclick=function(e){
    var c=e.target.closest('.chip'); if(!c) return;
    window._tag=(window._tag===c.dataset.tag)?'':c.dataset.tag;
    render();
  };
}
function rowHours(p){
  if(!p.expireAt) return 0;
  var h=Math.round((p.expireAt-Date.now())/3600e3);
  return h>0?h:0;
}
function setTtl(slug){
  var p=T.projects.find(function(x){return x.slug===slug;});
  var inp=document.querySelector('input.mini[data-slug="'+CSS.escape(slug)+'"]');
  var hv=inp?parseFloat(inp.value):NaN;
  var hrs=(inp&&!isNaN(hv))?hv:hours();
  api('/api/admin/ttl',{slug:slug,hours:hrs,action:(p&&p.expireAction)||'block'}).then(function(d){
    if(d.ok&&p){p.expireAt=d.project.expireAt;p.permanent=d.project.permanent;render();}
    else{alert(d.error||'失败');}
  });
}
/* ===== 新增项目 ===== */
var picked=[];
function toggleEye(){
  var i=document.getElementById('tok');
  i.type = (i.type==='password') ? 'text' : 'password';
  document.getElementById('eyebtn').textContent = (i.type==='password') ? '👁' : '🙈';
}
function toggleAdd(force){
  var box=document.getElementById('addbox');
  var open = (typeof force==='boolean') ? force : !box.classList.contains('open');
  box.classList.toggle('open', open);
  var b=document.getElementById('addbtn');
  if(b) b.textContent = open ? '收起新增' : '+ 新增项目';
}
function fmtSize(n){if(n<1024)return n+' B';if(n<1048576)return (n/1024).toFixed(0)+' KB';return (n/1048576).toFixed(1)+' MB';}
function renderFiles(){
  var el=document.getElementById('flist');
  if(!picked.length){el.innerHTML='<div style="color:#94a3b8">尚未选择文件</div>';return;}
  var tot=0;picked.forEach(function(f){tot+=f.file.size;});
  el.innerHTML='<div style="font-weight:600;color:#0f172a">共 '+picked.length+' 个文件 · '+fmtSize(tot)+'</div>'+
    picked.map(function(f,i){return '<div><span>'+esc(f.rel)+'</span><span>'+fmtSize(f.file.size)+' <span class="dl-file" data-rm="'+i+'">移÷</span></span></div>';}).join('');
}
function addFiles(list,base){
  base=base||'';
  for(var i=0;i<list.length;i++){
    var f=list[i];
    var rel=base? (base+'/'+f.name) : (f.webkitRelativePath||f.name);
    if(rel.charAt(0)==='/') rel=rel.slice(1);
    picked.push({rel:rel,file:f});
  }
  renderFiles();
}
function doUpload(){
  var msg=document.getElementById('amsg');
  var name=document.getElementById('f_name').value.trim();
  var slug=document.getElementById('f_slug').value.trim();
  if(!name && !slug){msg.className='aerr';msg.textContent='请填显示名';return;}
  if(!picked.length){msg.className='aerr';msg.textContent='请选择项目文件';return;}
  var ttlv=document.getElementById('f_ttl').value;
  var ttlN=parseFloat(ttlv);
  var wantZip=document.getElementById('f_zip').value==='1';
  var fd=new FormData();
  fd.append('slug',slug||name);
  fd.append('name',name||slug);
  fd.append('desc',document.getElementById('f_desc').value);
  if(!isNaN(ttlN) && ttlN<=0) fd.append('ttl','forever'); else fd.append('ttl', String(isNaN(ttlN)?24:ttlN));
  fd.append('expireAction',document.getElementById('f_act').value);
  fd.append('allowDownload',document.getElementById('f_dl').value);
  picked.forEach(function(f){fd.append('files',f.file,f.rel);});
  var btn=document.getElementById('upbtn');btn.disabled=true;
  msg.className='';msg.textContent='上传中…';
  var prep = Promise.resolve();
  if(wantZip){
    msg.textContent='打包 zip 中…';
    prep = buildZip(picked).then(function(blob){
      if(blob) fd.append('zip', blob, (slug||name||'project')+'.zip');
    }).catch(function(e){console.warn('zip build failed',e);});
  }
  prep.then(function(){
    msg.textContent='上传中…';
    return fetch('/upload',{method:'POST',headers:{'x-admin-token':tok()},body:fd});
  }).then(function(r){return r.json();}).then(function(d){
    btn.disabled=false;
    if(d.ok){
      msg.className='aok';
      msg.textContent='✅ 已创建：'+location.origin+(d.url||('/'+d.slug+'/'))+(d.download?'（zip 下载已'+(d.allowDownload?'开放':'关闭')+'）':'');
      picked=[];renderFiles();
      document.getElementById('f_name').value='';document.getElementById('f_slug').value='';document.getElementById('f_desc').value='';document.getElementById('f_link').value='';
      load();
    }else{msg.className='aerr';msg.textContent='失败：'+(d.error||'未知错误');}
  }).catch(function(e){btn.disabled=false;msg.className='aerr';msg.textContent='上传失败：'+e.message;});
}
function doLink(){
  var msg=document.getElementById('amsg');
  var name=document.getElementById('f_name').value.trim();
  var slug=document.getElementById('f_slug').value.trim();
  var link=document.getElementById('f_link').value.trim();
  if(!link){msg.className='aerr';msg.textContent='请填外部链接 URL';return;}
  if(!name && !slug){msg.className='aerr';msg.textContent='请填显示名';return;}
  var ttlv=document.getElementById('f_ttl').value;
  var ttlN=parseFloat(ttlv);
  var fd=new FormData();
  fd.append('slug',slug||name);
  fd.append('name',name||slug);
  fd.append('desc',document.getElementById('f_desc').value);
  fd.append('link',link);
  if(!isNaN(ttlN) && ttlN<=0) fd.append('ttl','forever'); else fd.append('ttl', String(isNaN(ttlN)?24:ttlN));
  fd.append('expireAction',document.getElementById('f_act').value);
  var btn=document.getElementById('lkbtn');btn.disabled=true;
  msg.className='';msg.textContent='创建中…';
  fetch('/upload',{method:'POST',headers:{'x-admin-token':tok()},body:fd})
  .then(function(r){return r.json();}).then(function(d){
    btn.disabled=false;
    if(d.ok){
      msg.className='aok';
      msg.textContent='✅ 已创建外链：'+d.link;
      document.getElementById('f_name').value='';document.getElementById('f_slug').value='';document.getElementById('f_desc').value='';document.getElementById('f_link').value='';
      load();
    }else{msg.className='aerr';msg.textContent='失败：'+(d.error||'未知错误');}
  }).catch(function(e){btn.disabled=false;msg.className='aerr';msg.textContent='创建失败：'+e.message;});
}
/* ===== 极简 ZIP 打包（STORE 无压缩，浏览器兼容性好） ===== */
function crc32(u8){
  var c,table=crc32.t;
  if(!table){ table=crc32.t=[]; for(var n=0;n<256;n++){ c=n; for(var k=0;k<8;k++) c = c&1 ? (0xEDB88320 ^ (c>>>1)) : (c>>>1); table[n]=c>>>0; } }
  var crc=0xFFFFFFFF;
  for(var i=0;i<u8.length;i++) crc = (crc>>>8) ^ table[(crc ^ u8[i]) & 0xFF];
  return (crc ^ 0xFFFFFFFF)>>>0;
}
function u16(n){return [n&255,(n>>8)&255];}
function u32(n){return [n&255,(n>>8)&255,(n>>16)&255,(n>>24)&255];}
function enc(str){return new TextEncoder().encode(str);}
function buildZip(items){
  return Promise.all(items.map(function(it){
    return it.file.arrayBuffer().then(function(ab){ return {rel:it.rel, bytes:new Uint8Array(ab), date:it.file.lastModified?new Date(it.file.lastModified):new Date()}; });
  })).then(function(entries){
    var parts=[], central=[], offset=0;
    entries.forEach(function(en){
      var nameB=enc(en.rel);
      var crc=crc32(en.bytes);
      var dosT=((en.date.getHours()<<11)|(en.date.getMinutes()<<5)|(en.date.getSeconds()/2))&0xFFFF;
      var dosD=(((en.date.getFullYear()-1980)<<9)|((en.date.getMonth()+1)<<5)|en.date.getDate())&0xFFFF;
      var lh=[].concat([0x50,0x4b,0x03,0x04], u16(20), u16(0), u16(0), u16(dosT), u16(dosD), u32(crc), u32(en.bytes.length), u32(en.bytes.length), u16(nameB.length), u16(0));
      parts.push(new Uint8Array(lh), nameB, en.bytes);
      var ch=[].concat([0x50,0x4b,0x01,0x02], u16(20), u16(20), u16(0), u16(0), u16(dosT), u16(dosD), u32(crc), u32(en.bytes.length), u32(en.bytes.length), u16(nameB.length), u16(0), u16(0), u16(0), u16(0), u32(0), u32(offset));
      central.push(new Uint8Array(ch), nameB);
      offset += lh.length + nameB.length + en.bytes.length;
    });
    var cdSize=central.reduce(function(a,b){return a+b.length;},0);
    var eocd=new Uint8Array([].concat([0x50,0x4b,0x05,0x06], u16(0), u16(0), u16(entries.length), u16(entries.length), u32(cdSize), u32(offset), u16(0)));
    return new Blob(parts.concat(central,[eocd]),{type:'application/zip'});
  });
}
(function(){
  var drop=document.getElementById('drop'),f1=document.getElementById('f_files'),f2=document.getElementById('f_files2');
  if(!drop) return;
  drop.addEventListener('click',function(e){ if(e.target && e.target.id==='pickfiles') return; f1.click(); });
  var pf=document.getElementById('pickfiles');
  if(pf) pf.addEventListener('click',function(e){e.stopPropagation();f2.click();});
  f1.addEventListener('change',function(){addFiles(f1.files);f1.value='';});
  f2.addEventListener('change',function(){addFiles(f2.files);f2.value='';});
  drop.addEventListener('dragover',function(e){e.preventDefault();drop.classList.add('over');});
  drop.addEventListener('dragleave',function(){drop.classList.remove('over');});
  drop.addEventListener('drop',function(e){
    e.preventDefault();drop.classList.remove('over');
    var items=e.dataTransfer.items, files=e.dataTransfer.files;
    if(items && items.length && items[0].webkitGetAsEntry){
      var roots=[];for(var i=0;i<items.length;i++){var en=items[i].webkitGetAsEntry();if(en)roots.push(en);}
      var pending=roots.length;
      roots.forEach(function(root){walkEntry(root,'',function(){if(--pending<=0)renderFiles();},function(f,rel){picked.push({rel:rel,file:f});});});
    }else{ addFiles(files); }
  });
  document.getElementById('flist').addEventListener('click',function(e){
    var rm=e.target.closest('[data-rm]'); if(!rm) return;
    picked.splice(parseInt(rm.dataset.rm,10),1); renderFiles();
  });
  document.getElementById('addbtn') && document.getElementById('addbtn');
})();
function walkEntry(entry,path,done,onFile){
  if(entry.isFile){ entry.file(function(f){ onFile(f, path? path+'/'+entry.name : entry.name); done&&done(); }); return; }
  if(entry.isDirectory){
    var rd=entry.createReader(), all=[];
    (function readmore(){
      rd.readEntries(function(ents){
        if(!ents.length){
          var p2=path? path+'/'+entry.name : entry.name;
          var pend=all.length;
          if(!pend){done&&done();return;}
          all.forEach(function(en){walkEntry(en,p2,function(){if(--pend<=0)done&&done();},onFile);});
          return;
        }
        all=all.concat(Array.prototype.slice.call(ents));readmore();
      });
    })();
    return;
  }
  done&&done();
}
function pickPreset(){var v=document.getElementById('preset').value;if(v!==''){document.getElementById('hours').value=v;}}
function setPerm(slug,makePerm){
  api('/api/admin/ttl',{slug:slug,hours:(makePerm?0:24)}).then(function(d){
    if(d.ok){var p=T.projects.find(function(x){return x.slug===slug;});if(p){p.expireAt=d.project.expireAt;p.permanent=d.project.permanent;}render();}
    else{alert(d.error||'失败');}
  });
}
/* 事件委托：所有操作按钮走 data-act，避开内联引号转义 */
document.getElementById('out').addEventListener('click', function(e){
  var b=e.target.closest('[data-act]'); if(!b) return;
  var act=b.dataset.act, slug=b.dataset.slug;
  if(act==='dl') setDl(slug, b.dataset.val==='1');
  else if(act==='ttl') setTtl(slug);
  else if(act==='perm') setPerm(slug, b.textContent.indexOf('取消')<0);
  else if(act==='expire') setActTo(slug, b.dataset.val);
  else if(act==='views') resetViews(slug);
  else if(act==='del') del(slug);
});
function resetViews(slug){
  if(!confirm('把 '+slug+' 的访问次数清零？')) return;
  api('/api/admin/views',{slug:slug,views:0}).then(function(d){
    if(d.ok){var p=T.projects.find(function(x){return x.slug===slug;});if(p){p.views=0;}render();}
    else{alert(d.error||'失败');}
  });
}
function setActTo(slug,next){
  var p=T.projects.find(function(x){return x.slug===slug;});
  api('/api/admin/ttl',{slug:slug,hours:(p&&p.permanent)?0:((p.expireAt-Date.now())/3600e3),action:next}).then(function(d){
    if(d.ok&&p){p.expireAction=d.project.expireAction;render();}
    else{alert(d.error||'失败');}
  });
}
function setDl(slug,allow){
  api('/api/admin/download',{slug:slug,allow:allow}).then(function(d){
    if(d.ok){var p=T.projects.find(function(x){return x.slug===slug;});if(p){p.allowDownload=d.project.allowDownload;}render();}
    else{alert(d.error||'失败');}
  });
}
function setViews(slug,n){
  api('/api/admin/views',{slug:slug,views:n}).then(function(d){
    if(d.ok){var p=T.projects.find(function(x){return x.slug===slug;});if(p){p.views=d.views;}render();}
    else{alert(d.error||'失败');}
  });
}
function hoursLabel(){var v=document.getElementById('hours').value;var n=parseFloat(v);if(isNaN(n))n=24;return n<=0?'永久':n+'h';}
function del(slug){
  if(!confirm('删除 '+slug+' ？文件和记录都会清除，不可恢复。')) return;
  api('/api/admin/delete',{slug:slug}).then(function(d){
    if(d.ok){T.projects=T.projects.filter(function(x){return x.slug!==slug;});render();}
    else{alert(d.error||'失败');}
  });
}
function ttlAll(){
  if(!T.projects||!T.projects.length) return;
  if(!confirm('把全部 '+T.projects.length+' 个项目重设为 '+hoursLabel()+'？')) return;
  var list=T.projects.slice();
  (function next(i){
    if(i>=list.length){load();return;}
    api('/api/admin/ttl',{slug:list[i].slug,hours:hours(),action:list[i].expireAction||'block'}).then(function(){next(i+1);});
  })(0);
}
// 启动：服务端已给 token（cookie 生效）；否则尝试 localStorage 里记住的
try{ var _s2=localStorage.getItem('pa_sort'); if(_s2==='time'){ window.__asortv='time'; var _el=document.getElementById('asort'); if(_el) _el.value='time'; } }catch(e){}
try{ if(!tok()){var st=localStorage.getItem('pp_tok'); if(st) document.getElementById('tok').value=st;} }catch(e){}
if(tok()) load();
</script></div></body></html>`;
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
