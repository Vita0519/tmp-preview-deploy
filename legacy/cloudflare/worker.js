/**
 * tmp-preview — 临时项目预览 / 下载 / 到期自动删除
 * 存储：KV（清单）+ KV（文件分片，base64）—— 无需绑卡即可用
 *
 * KV 布局:
 *   meta:<slug>              → 项目元数据 JSON
 *   meta:__index__           → 所有 slug 数组
 *   file:<slug>:<ph>         → 文件记录 {path, size, type, chunks, etag}
 *   chunk:<slug>:<ph>:<i>    → 分片数据（base64 文本，每片 <= 18MB 原值）
 *   pv:d:<slug>              → 访问计数「待写入增量」（抽样累加，未落库）
 *   views:<slug>             → 访问计数「已落库总数」
 *
 * 访问计数策略（省 KV 写额度 / 最终一致，不追求精确及时）:
 *   免费额度每日仅 1000 次 KV 写，旧「每次访问写一次」很快打爆。
 *   现在：① 抽样计数 —— 仅约 1/20 的访问会触发写入，那次把 +20 记到 pv:d:<slug>；
 *   ② 主计数 views:<slug> 由 flush（cron 或惰性）合并落库：每 10 分钟最多 1 写；
 *   ③ 展示值 = 已落库 + 待写入增量；增量在额度耗尽时保留，下次再落，绝不丢数据。
 *   合计写入量 ≈ 访问量 / 20（抽样）+ 项目数 × 144（flush，每日）
 *
 * 环境变量:
 *   SITE_TITLE, DEFAULT_TTL_H, ADMIN_TOKEN, LOCAL_SITE_URL
 * 绑定:
 *   [[kv_namespaces]] binding = "KV"
 */

import { adminHTML } from './admin.js';

const DEFAULT_TTL_H = 24;
const CHUNK_MAX = 18 * 1024 * 1024; // 单分片原始字节上限（base64 后 ~24MB，留余量）

/* ---------------- 工具 ---------------- */

const json = (data, status = 200, extra = {}) =>
  new Response(JSON.stringify(data), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      'access-control-allow-origin': '*',
      ...extra,
    },
  });

const humanSize = (n) => {
  if (!n) return '0 KB';
  if (n < 1024) return n + ' B';
  if (n < 1024 * 1024) return (n / 1024).toFixed(0) + ' KB';
  if (n < 1024 * 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + ' MB';
  return (n / 1024 / 1024 / 1024).toFixed(2) + ' GB';
};

const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// 外链规范化：补全 https://，丢掉首尾空白
const normalizeUrl = (u) => {
  let s = String(u || '').trim();
  if (!s) return '';
  if (!/^https?:\/\//i.test(s)) s = 'https://' + s.replace(/^\/\/+/, '');
  return s;
};

const guessType = (name) => {
  const e = (name.split('.').pop() || '').toLowerCase();
  return (
    {
      html: 'text/html; charset=utf-8', htm: 'text/html; charset=utf-8',
      js: 'application/javascript; charset=utf-8', mjs: 'application/javascript; charset=utf-8',
      css: 'text/css; charset=utf-8', json: 'application/json; charset=utf-8',
      svg: 'image/svg+xml', xml: 'application/xml; charset=utf-8',
      png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif',
      webp: 'image/webp', avif: 'image/avif', ico: 'image/x-icon',
      mp3: 'audio/mpeg', wav: 'audio/wav', ogg: 'audio/ogg', m4a: 'audio/mp4',
      mp4: 'video/mp4', webm: 'video/webm', mov: 'video/quicktime',
      woff: 'font/woff', woff2: 'font/woff2', ttf: 'font/ttf', otf: 'font/otf',
      pdf: 'application/pdf', zip: 'application/zip', txt: 'text/plain; charset=utf-8',
      wasm: 'application/wasm', glb: 'model/gltf-binary', gltf: 'model/gltf+json',
    }[e] || 'application/octet-stream');
};

function slugify(name) {
  const raw = String(name || '').trim();
  let s = raw.toLowerCase().replace(/[^a-z0-9\-_]+/g, '-').replace(/^-+|-+$/g, '');
  if (!s) {
    let h = 0;
    for (const ch of raw) h = (h * 31 + ch.codePointAt(0)) % 0xffffff;
    s = 'p-' + h.toString(36);
  }
  return s.slice(0, 60);
}

/* base64 <-> bytes（分片存储用） */
function bytesToB64(bytes) {
  let b = '';
  const arr = new Uint8Array(bytes);
  const step = 0x8000;
  for (let i = 0; i < arr.length; i += step) b += String.fromCharCode.apply(null, arr.subarray(i, i + step));
  return btoa(b);
}
function b64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** 稳定的路径 hash（file key 用，避免超长/非法字符） */
function pathHash(p) {
  let h1 = 0x811c9dc5;
  for (let i = 0; i < p.length; i++) {
    h1 ^= p.charCodeAt(i);
    h1 = Math.imul(h1, 0x01000193) >>> 0;
  }
  return h1.toString(16).padStart(8, '0') + '-' + p.length.toString(16);
}

/** 安全文件名 */
function safeName(name) {
  return String(name).replace(/[^A-Za-z0-9._\-]/g, '_').slice(0, 120) || 'download.zip';
}

/* ---------------- 清单操作 ---------------- */

async function listSlugs(env) {
  // 优先用 KV list 动态扫描 meta:* （避免并发写导致 __index__ 丢登）
  const out = [];
  let cursor;
  do {
    const res = await env.KV.list({ prefix: 'meta:', cursor, limit: 1000 });
    for (const k of res.keys) {
      if (k.name === 'meta:__index__') continue;
      out.push(k.name.slice('meta:'.length));
    }
    cursor = res.list_complete ? null : res.cursor;
  } while (cursor);
  if (out.length) return out;
  // 兼容：KV list 不支持的旧环境回退到索引
  return (await env.KV.get('meta:__index__', 'json')) || [];
}
async function getMeta(env, slug) {
  return await env.KV.get('meta:' + slug, 'json');
}
async function putMeta(env, slug, meta) {
  await env.KV.put('meta:' + slug, JSON.stringify(meta));
  const idx = await listSlugs(env);
  if (!idx.includes(slug)) {
    idx.push(slug);
    await env.KV.put('meta:__index__', JSON.stringify(idx));
  }
}
async function delMeta(env, slug) {
  await env.KV.delete('meta:' + slug);
  const idx = (await listSlugs(env)).filter((s) => s !== slug);
  await env.KV.put('meta:__index__', JSON.stringify(idx));
}
async function listFiles(env, slug) {
  const list = await env.KV.list({ prefix: 'file:' + slug + ':' });
  const out = [];
  for (const k of list.keys) {
    const rec = await env.KV.get(k.name, 'json');
    if (rec) out.push(rec);
  }
  return out;
}
async function getFile(env, slug, relPath) {
  const key = 'file:' + slug + ':' + pathHash(relPath);
  return await env.KV.get(key, 'json');
}
/* ---- 访问计数：低写入策略（最终一致丨不追求精确及时） ---- */
//
// 免费额度每日仅 1000 次 KV 写。旧方案「每次访问写一次」很快打爆。
// 新方案：抽样计数 —— 只有约 1/SAMPLE_RATE 的访问会触发一次写入，
// 该次写入把 N=SAMPLE_RATE 记到待落库增量 pv:d:<slug>。
// 总次数 ≈ 写入次数 × SAMPLE_RATE，误差很小（大数定律），且写入量降到 1/SAMPLE_RATE。
// 写 pv:d 也只在抽样命中时发生；其余访问零写入。

const VIEW_SAMPLE_RATE = 20;   // 每 20 次访问记 1 次；写入量降至 1/20

// 记一次访问：抽样写入（大部分请求直接返回，不碰 KV）
async function bumpViews(env, slug) {
  if (VIEW_SAMPLE_RATE > 1 && Math.random() >= 1 / VIEW_SAMPLE_RATE) return;
  const key = 'pv:d:' + slug;
  const cur = parseInt(await env.KV.get(key), 10) || 0;
  await env.KV.put(key, String(cur + VIEW_SAMPLE_RATE));
}

// 视图：已落库总数 + 待写入增量
async function getViews(env, slug) {
  const [base, delta] = await Promise.all([
    env.KV.get('views:' + slug),
    env.KV.get('pv:d:' + slug),
  ]);
  return (parseInt(base, 10) || 0) + (parseInt(delta, 10) || 0);
}

// 把增量合并进主计数并清零增量
async function flushViews(env, slug) {
  const base = parseInt(await env.KV.get('views:' + slug), 10) || 0;
  const delta = parseInt(await env.KV.get('pv:d:' + slug), 10) || 0;
  if (delta <= 0) return false;
  // 先写主计数（若失败则保留增量，下次再试，绝不丢数据）
  await env.KV.put('views:' + slug, String(base + delta));
  await env.KV.delete('pv:d:' + slug);
  return true;
}

// 批量 flush（尽力而为：逐项 try/catch，额度耗尽也不报错、不丢增量）
async function flushViewsLocked(env) {
  const slugs = await listSlugs(env);
  let flushed = 0, skipped = 0, errors = 0;
  for (const slug of slugs) {
    const delta = parseInt(await env.KV.get('pv:d:' + slug), 10) || 0;
    if (delta <= 0) { skipped++; continue; }
    try {
      if (await flushViews(env, slug)) flushed++;
    } catch (e) {
      errors++;   // 例如「KV put() limit exceeded for the day」→ 保留增量，下次再落
    }
  }
  return { flushed, skipped, errors, total: slugs.length };
}

async function deleteProjectData(env, slug) {
  // 删文件记录与分片
  const files = await env.KV.list({ prefix: 'file:' + slug + ':' });
  for (const k of files.keys) await env.KV.delete(k.name);
  const chunks = await env.KV.list({ prefix: 'chunk:' + slug + ':' });
  for (const k of chunks.keys) await env.KV.delete(k.name);
  await env.KV.delete('views:' + slug);
  await env.KV.delete('pv:d:' + slug);
}

/* ---------------- 主 Worker ---------------- */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = decodeURIComponent(url.pathname);
    const siteTitle = env.SITE_TITLE || '测试预览服务';
    const localBase = (env.LOCAL_SITE_URL || url.origin).replace(/\/$/, '');

    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'access-control-allow-origin': '*',
          'access-control-allow-methods': 'GET,HEAD,PUT,POST,DELETE,OPTIONS',
          'access-control-allow-headers': 'content-type,authorization,x-admin-token',
        },
      });
    }

    /* ===== 清单 API（需门户密码，防止整站被一次性抓光） ===== */
    if (path === '/api/projects') {
      if (!checkPortal(request, env)) return json({ ok: false, error: 'unauthorized' }, 401);
      const idx = await listSlugs(env);
      const now = Date.now();
      const list = [];
      for (const slug of idx) {
        const m = await getMeta(env, slug);
        if (!m) continue;
        const perm = !m.expireAt;                       // 0 = 永久
        if (!perm && m.expireAt <= now) continue;       // 已到期：不再展示（无论 block/delete）
        const vRaw = await getViews(env, slug);
        list.push({
          slug,
          name: m.name,
          desc: m.desc || '',
          path: '/' + slug + '/',
          link: m.link || '',
          isLink: !!m.link,
          views: vRaw,
          files: m.files || 0,
          size: m.size || 0,
          sizeText: humanSize(m.size || 0),
          createdAt: m.createdAt,
          expireAt: m.expireAt || 0,
          permanent: !m.expireAt,
          expireAction: m.expireAction || 'block',
          remainMs: m.expireAt ? m.expireAt - now : null,
          download: (m.allowDownload && m.zipName) ? '/download/' + slug : null,
          hasZip: !!m.zipName,
          allowDownload: !!m.allowDownload,
          zipName: m.zipName || '',
        });
      }
      list.sort((a, b) => b.createdAt - a.createdAt);
      return json({ ok: true, serverNow: now, siteTitle, projects: list });
    }

    if (path === '/api/admin/list') {
      if (!checkAdmin(request, env)) return json({ ok: false, error: 'unauthorized' }, 401);
      const idx = await listSlugs(env);
      const now = Date.now();
      const projects = [];
      for (const slug of idx) {
        const m = await getMeta(env, slug);
        if (m) {
          const perm = !m.expireAt;
          const vRaw = await getViews(env, slug);
          projects.push({
            ...m,
            views: vRaw,
            expireAt: m.expireAt || 0,
            permanent: perm,
            expireAction: m.expireAction || 'block',
            expired: !perm && m.expireAt <= now,
            remainMs: m.expireAt ? m.expireAt - now : null,
          });
        }
      }
      projects.sort((a, b) => b.createdAt - a.createdAt);
      return json({ ok: true, serverNow: now, projects });
    }

    if (path === '/api/admin/ttl' && request.method === 'POST') {
      if (!checkAdmin(request, env)) return json({ ok: false, error: 'unauthorized' }, 401);
      const b = await request.json().catch(() => ({}));
      const m = await getMeta(env, b.slug);
      if (!m) return json({ ok: false, error: 'not found' }, 404);
      const hours = Number(b.hours);
      // hours<=0 → 永久（expireAt=0）
      m.expireAt = (!hours || hours <= 0) ? 0 : Date.now() + hours * 3600e3;
      if (b.action === 'block' || b.action === 'delete') m.expireAction = b.action;
      m.updatedAt = Date.now();
      await putMeta(env, b.slug, m);
      return json({ ok: true, project: { slug: b.slug, expireAt: m.expireAt, permanent: !m.expireAt, expireAction: m.expireAction || 'block' } });
    }

    if (path === '/api/admin/delete' && request.method === 'POST') {
      if (!checkAdmin(request, env)) return json({ ok: false, error: 'unauthorized' }, 401);
      const b = await request.json().catch(() => ({}));
      if (!b.slug) return json({ ok: false, error: 'slug required' }, 400);
      await deleteProjectData(env, b.slug);
      await delMeta(env, b.slug);
      return json({ ok: true });
    }

    if (path === '/api/admin/download' && request.method === 'POST') {
      if (!checkAdmin(request, env)) return json({ ok: false, error: 'unauthorized' }, 401);
      const b = await request.json().catch(() => ({}));
      const m = await getMeta(env, b.slug);
      if (!m) return json({ ok: false, error: 'not found' }, 404);
      m.allowDownload = !!b.allow;
      m.updatedAt = Date.now();
      await putMeta(env, b.slug, m);
      return json({ ok: true, project: { slug: b.slug, allowDownload: m.allowDownload } });
    }

    if (path === '/api/admin/views' && request.method === 'POST') {
      if (!checkAdmin(request, env)) return json({ ok: false, error: 'unauthorized' }, 401);
      const b = await request.json().catch(() => ({}));
      if (!b.slug) return json({ ok: false, error: 'slug required' }, 400);
      const n = Number.isFinite(Number(b.views)) ? Math.max(0, Math.floor(Number(b.views))) : 0;
      await env.KV.put('views:' + b.slug, String(n));
      await env.KV.delete('pv:d:' + b.slug);   // 清零时同时清掉待写入增量
      return json({ ok: true, slug: b.slug, views: n });
    }

    if (path === '/api/admin/flush-views' && request.method === 'POST') {
      if (!checkAdmin(request, env)) return json({ ok: false, error: 'unauthorized' }, 401);
      const r = await flushViewsLocked(env);   // 内部已逐项 try/catch，额度耗尽也不会 500
      return json({ ok: true, ...r });
    }

    /* ===== 上传 ===== */
    if (path === '/upload' && request.method === 'POST') {
      if (!checkAdmin(request, env)) return json({ ok: false, error: 'unauthorized' }, 401);
      try {
        return await handleUpload(request, env, url);
      } catch (e) {
        return json({ ok: false, error: 'upload failed: ' + (e && e.message ? e.message : String(e)) }, 500);
      }
    }

    /* ===== 下载 zip ===== */
    if (path.startsWith('/download/')) {
      const slug = path.slice('/download/'.length).replace(/\/$/, '');
      const m = await getMeta(env, slug);
      if (!m) return html404('项目不存在', localBase);
      if (m.expireAt && m.expireAt <= Date.now()) return html410('这个项目已超过存活时限，访问已停止。', localBase);
      if (!m.allowDownload) return html404('该项目未开放下载', localBase);
      const zrec = await getFile(env, slug, '__zip__');
      if (!zrec) return html404('该项目没有打包文件', localBase);
      const body = await readFileStream(env, slug, zrec);
      return new Response(body, {
        headers: {
          'content-type': 'application/zip',
          'content-disposition': `attachment; filename="${encodeURIComponent(zrec.displayName || m.zipName || slug + '.zip')}"`,
          'content-length': String(zrec.size),
          'cache-control': 'no-store',
        },
      });
    }

    /* ===== 管理页 ===== */
    if (path === '/admin' || path === '/admin/') {
      const token = url.searchParams.get('token') || '';
      if (token && token === env.ADMIN_TOKEN) {
        return new Response('', {
          status: 302,
          headers: { location: '/admin?ok=1', 'set-cookie': `pp_token=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000` },
        });
      }
      const cookie = (request.headers.get('cookie') || '').match(/(?:^|;\s*)(?:pp_token|pp_tok)=([^;]+)/);
      const cval = cookie ? decodeURIComponent(cookie[1]) : '';
      const authed = (cval && cval === env.ADMIN_TOKEN) || url.searchParams.get('ok') === '1';
      return new Response(adminHTML(authed ? env.ADMIN_TOKEN : ''), {
        headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store', 'x-robots-tag': 'noindex, nofollow' },
      });
    }

    /* ===== 门户登录 / 退出 ===== */
    if (path === '/api/portal/login' && request.method === 'POST') {
      const form = await request.formData().catch(() => null);
      const pw = form ? String(form.get('password') || '') : '';
      if (pw && pw === env.ADMIN_TOKEN) {
        return new Response('', { status: 302, headers: { location: '/', 'set-cookie': cookieHeader(env.ADMIN_TOKEN) } });
      }
      return new Response(gateHTML(siteTitle, '密码不正确'), {
        status: 401,
        headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store', 'x-robots-tag': 'noindex, nofollow' },
      });
    }

    /* ===== 门户首页（需密码；子项目 /<slug>/ 与 /download/ 不受影响） ===== */
    if (path === '/' || path === '/index.html') {
      if (url.searchParams.get('logout') === '1') {
        return new Response('', { status: 302, headers: { location: '/', 'set-cookie': 'pp_token=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0' } });
      }
      const qToken = url.searchParams.get('token') || '';
      if (qToken && qToken === env.ADMIN_TOKEN) {
        return new Response('', { status: 302, headers: { location: '/', 'set-cookie': cookieHeader(env.ADMIN_TOKEN) } });
      }
      if (!checkPortal(request, env)) {
        return new Response(gateHTML(siteTitle, qToken ? '密码不正确' : ''), {
          headers: {
            'content-type': 'text/html; charset=utf-8',
            'cache-control': 'no-store, must-revalidate',
            'x-robots-tag': 'noindex, nofollow',
          },
        });
      }
      return new Response(portalHTML(siteTitle), {
        headers: {
          'content-type': 'text/html; charset=utf-8',
          'cache-control': 'no-store, must-revalidate',
          'x-robots-tag': 'noindex, nofollow',
        },
      });
    }

    /* ===== 静态资源 ===== */
    const mm = path.match(/^\/([a-z0-9\-_]+)(\/.*|$)/i);
    if (mm && !RESERVED.has(mm[1])) {
      const slug = mm[1];
      let rest = mm[2] || '/';
      if (rest === '' || rest === '/') rest = '/index.html';
      rest = rest.replace(/^\/+/, '');

      const m = await getMeta(env, slug);
      if (!m || (m.expireAt && m.expireAt <= Date.now())) return html410('该项目已到期，访问已停止', localBase);

      let rec = await getFile(env, slug, rest);
      // 目录路径（以 / 结尾或无扩展名）优先补 index.html
      if (!rec && (rest.endsWith('/') || !/\.[a-z0-9]{1,8}$/i.test(rest))) {
        rec = await getFile(env, slug, rest.replace(/\/+$/, '') + '/index.html');
      }
      if (!rec) rec = await getFile(env, slug, 'index.html'); // SPA 兜底
      if (!rec) return html404('页面不存在', localBase);

      // 访问计数：只算项目首页文档（index.html）的文档型 GET 请求，子资源/API 不重复计。
      // 抽样写入热 key pv:d:<slug>（约 1/20 的访问才写一次），由 flush 合并落库 → 省 KV 写额度。
      const isEntryDoc = rec.path === 'index.html' && (request.headers.get('accept') || '').includes('text/html');
      if (isEntryDoc && request.method === 'GET') {
        ctx.waitUntil(bumpViews(env, slug).catch(() => {}));
      }

      const body = await readFileStream(env, slug, rec);
      const headers = new Headers();
      headers.set('content-type', rec.type || guessType(rec.path));
      headers.set('cache-control', /(^|\/)index\.html$/i.test(rec.path) ? 'no-store, must-revalidate' : 'public, max-age=300');
      headers.set('x-robots-tag', 'noindex, nofollow');
      headers.set('etag', rec.etag);
      if (request.headers.get('if-none-match') === rec.etag) return new Response(null, { status: 304, headers });
      return new Response(body, { headers });
    }

    return html404('页面不存在', localBase);
  },

  /* ===== 到期处理 + 计数落库 ===== */
  async scheduled(event, env, ctx) {
    // 先把访问计数增量合并落库（尽力而为，额度耗尽也不影响到期处理）
    try {
      const fr = await flushViewsLocked(env);
      console.log('[cron] flushViews:', JSON.stringify(fr));
    } catch (e) {
      console.log('[cron] flushViews failed:', e && e.message);
    }
    const idx = await listSlugs(env);
    const now = Date.now();
    const purged = [];
    const blocked = [];
    for (const slug of idx) {
      const m = await getMeta(env, slug);
      // ⚠ 不要用 !m 就删：KV list 是最终一致的，新写入的 key 可能先出现在 list 但 value 还未可读，
      // 误删会丢项目。查不到 meta 直接跳过（真正过期的项目下次 cron 再处理）。
      if (!m) { console.log('[cron] skip(no-meta):', slug); continue; }
      // 保险：永久(expireAt=0/缺省)或外链项目，绝不删除
      if (!m.expireAt) { continue; }
      if (m.expireAt > now) continue;   // 未到期
      // 额外保险：expireAt 异常（非有限正数）一律不删
      if (!isFinite(m.expireAt) || m.expireAt <= 0) { console.log('[cron] skip(bad-expireAt):', slug, m.expireAt); continue; }
      if ((m.expireAction || 'block') === 'delete') {
        console.log('[cron] DELETE:', slug, 'expireAt=', m.expireAt, 'now=', now);
        await deleteProjectData(env, slug);
        await delMeta(env, slug);
        purged.push(slug);
      } else {
        blocked.push(slug);                            // 仅停止访问，文件保留
      }
    }
    console.log(`[cron] purged ${purged.length}: ${purged.join(', ')} | blocked(kept) ${blocked.length}: ${blocked.join(', ')}`);
    return new Response('ok');
  },
};

const RESERVED = new Set(['api', 'upload', 'download', 'admin', 'favicon.ico', '_', 'robots.txt']);

function cookieHeader(token) {
  return `pp_token=${encodeURIComponent(token)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000`;
}

/** 门户根路径鉴权：复用 pp_token Cookie（与 /admin 同一套，登录一次通用） */
function checkPortal(request, env) {
  const want = env.PORTAL_TOKEN || env.ADMIN_TOKEN;
  if (!want) return false;
  const m = (request.headers.get('cookie') || '').match(/(?:^|;\s*)pp_token=([^;]+)/);
  const cval = m ? decodeURIComponent(m[1]) : '';
  return cval === want;
}

function checkAdmin(request, env) {
  const token =
    request.headers.get('x-admin-token') ||
    (request.headers.get('authorization') || '').replace(/^Bearer\s+/i, '') ||
    new URL(request.url).searchParams.get('token') ||
    '';
  return !!env.ADMIN_TOKEN && token === env.ADMIN_TOKEN;
}

/** 把记录的分片拼成字节，用 ReadableStream 回传 */
async function readFileStream(env, slug, rec) {
  const parts = [];
  for (let i = 0; i < rec.chunks; i++) {
    const b64 = await env.KV.get('chunk:' + slug + ':' + pathHash(rec.path) + ':' + i, 'text');
    if (b64 == null) throw new Error('missing chunk ' + i + ' of ' + rec.path);
    parts.push(b64ToBytes(b64));
  }
  let size = 0;
  for (const p of parts) size += p.length;
  const all = new Uint8Array(size);
  let off = 0;
  for (const p of parts) {
    all.set(p, off);
    off += p.length;
  }
  return all;
}

/* ===== 上传处理 ===== */
async function handleUpload(request, env, url) {
  const ctype = request.headers.get('content-type') || '';
  if (!ctype.includes('multipart/form-data')) {
    return json({ ok: false, error: '请用 multipart/form-data 上传' }, 400);
  }

  const form = await request.formData();
  const slug = slugify(form.get('slug') || form.get('name') || 'project');
  const name = String(form.get('name') || slug);
  const desc = String(form.get('desc') || '');
  const rawTtl = form.get('ttl');
  const ttlStr = rawTtl == null ? '' : String(rawTtl).trim().toLowerCase();
  const permanent = ttlStr === 'forever' || ttlStr === '0' || ttlStr === 'perm';
  const hoursRaw = permanent ? 0 : Number(ttlStr || url.searchParams.get('ttl') || 0);
  const hours = (!permanent && (!hoursRaw || hoursRaw <= 0)) ? (Number(env.DEFAULT_TTL_H) || DEFAULT_TTL_H) : hoursRaw;
  const expireAction = (String(form.get('expireAction') || 'block') === 'delete') ? 'delete' : 'block';
  const allowDownload = String(form.get('allowDownload') || '') === '1' || String(form.get('allowDownload') || '') === 'true';
  const zipRaw = form.get('zip');
  const zip = (zipRaw && typeof zipRaw === 'object' && 'arrayBuffer' in zipRaw) ? zipRaw : null;
  const files = form.getAll('files').filter((f) => f && typeof f === 'object' && 'arrayBuffer' in f);
  // 外链项目：不传文件，只给一个 URL，点击直接跳转（用于把外部站点登记进门户）
  const linkRaw = String(form.get('link') || '').trim();
  const isLink = !!linkRaw && !zip && !files.length;
  const link = isLink ? normalizeUrl(linkRaw) : '';
  if (!zip && !files.length && !link) return json({ ok: false, error: '没有收到文件' }, 400);

  // 覆盖式重建：先清掉旧数据
  await deleteProjectData(env, slug);

  let totalSize = 0;
  let fileCount = 0;
  let zipName = null;

  const saveOne = async (rel, ab, overrideType) => {
    const bytes = new Uint8Array(ab);
    const key = 'file:' + slug + ':' + pathHash(rel);
    const chunkBase = 'chunk:' + slug + ':' + pathHash(rel) + ':';
    const chunks = Math.max(1, Math.ceil(bytes.length / CHUNK_MAX));
    for (let i = 0; i < chunks; i++) {
      const slice = bytes.subarray(i * CHUNK_MAX, (i + 1) * CHUNK_MAX);
      await env.KV.put(chunkBase + i, bytesToB64(slice));
    }
    const etag = 'W/"' + pathHash(rel) + '-' + bytes.length.toString(36) + '"';
    const rec = {
      path: rel,
      size: bytes.length,
      type: overrideType || guessType(rel),
      chunks,
      etag,
      displayName: rel,
    };
    await env.KV.put(key, JSON.stringify(rec));
    totalSize += bytes.length;
    return rec;
  };

  if (zip) {
    const zrec = await saveOne('__zip__', await zip.arrayBuffer(), 'application/zip');
    zrec.displayName = zip.name || slug + '.zip';
    await env.KV.put('file:' + slug + ':' + pathHash('__zip__'), JSON.stringify(zrec));
    zipName = zip.name || slug + '.zip';
  }

  for (const f of files) {
    const rel = (f.webkitRelativePath || f.name || '').replace(/^\/+/, '');
    if (!rel || rel.endsWith('/')) continue;
    await saveOne(rel, await f.arrayBuffer());
    fileCount++;
  }

  const meta = {
    slug,
    name,
    desc,
    files: fileCount,
    size: totalSize,
    zipName,
    allowDownload,
    expireAction,
    createdAt: Date.now(),
    updatedAt: Date.now(),
    expireAt: permanent ? 0 : Date.now() + hours * 3600e3,
  };
  if (isLink) meta.link = link;
  await putMeta(env, slug, meta);

  return json({
    ok: true,
    slug,
    url: isLink ? link : `/${slug}/`,
    link: isLink ? link : null,
    download: (allowDownload && zipName) ? `/download/${slug}` : null,
    allowDownload,
    permanent,
    expireAction,
    expireAt: meta.expireAt,
    files: fileCount,
    size: totalSize,
  });
}

/* ---------------- 门户页 ---------------- */

function portalHTML(title) {
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title>
<style>
*{box-sizing:border-box}
body{margin:0;min-height:100vh;font:15px/1.5 -apple-system,"PingFang SC","Microsoft YaHei",system-ui,sans-serif;
background:linear-gradient(160deg,#f6f8fc,#eef2f9 60%,#e9eef7);color:#0f172a;
display:flex;align-items:flex-start;justify-content:center;padding:14px 18px 60px}
.wrap{width:100%;max-width:1080px}
/* 搜索以上区域滚动时固定 */
.stickytop{position:sticky;top:0;z-index:50;margin:0 -14px;padding:12px 14px 14px;
background:linear-gradient(160deg,rgba(246,248,252,.92),rgba(238,242,249,.92) 60%,rgba(233,238,247,.92));
backdrop-filter:blur(14px) saturate(160%);border-bottom:1px solid rgba(148,163,184,.2);
box-shadow:0 8px 24px -18px rgba(15,23,42,.25);border-radius:0 0 16px 16px}
/* 顶部 */
.hdr{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:14px}
.hdr .title{display:flex;align-items:center;gap:12px}
.hdr .logo{width:40px;height:40px;border-radius:12px;display:flex;align-items:center;justify-content:center;
background:linear-gradient(135deg,#2563eb,#7c3aed);color:#fff;font-size:19px;box-shadow:0 8px 18px -8px rgba(37,99,235,.55);flex:0 0 auto}
.hdr h1{font-size:22px;margin:0;letter-spacing:-.02em;line-height:1.15}
.hdr .sub0{color:#94a3b8;font-size:12.5px;margin-top:3px}
.hdr .gear{margin-left:auto;font-size:16px;text-decoration:none;color:#64748b;padding:8px 11px;border-radius:11px;
line-height:1;transition:.2s;background:rgba(255,255,255,.7);border:1px solid rgba(148,163,184,.3)}
.hdr .gear:hover{color:#0f172a;background:#fff;border-color:#2563eb}
@media(max-width:620px){.hdr h1{font-size:18px}.hdr .logo{width:34px;height:34px;font-size:16px}}
/* 统计条 */
.stats{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.stat{display:flex;align-items:center;gap:7px;padding:8px 13px;background:rgba(255,255,255,.72);
border:1px solid rgba(148,163,184,.28);border-radius:11px;font-size:12.5px;color:#475569;font-weight:600}
.stat .dot{width:7px;height:7px;border-radius:50%;background:#059669;flex:0 0 auto}
.stat .num{font-size:14px;color:#0f172a;font-weight:700}
.stat.muted{color:#94a3b8}
/* 工具栏 */
.tools{display:flex;gap:8px;align-items:center;margin-bottom:0;flex-wrap:wrap}
.searchwrap{position:relative;flex:0 1 240px;min-width:170px}
.searchwrap .sic{position:absolute;left:11px;top:50%;transform:translateY(-50%);font-size:13px;color:#94a3b8;pointer-events:none}
.searchwrap input{width:100%;padding:8px 12px 8px 32px;border-radius:10px;border:1px solid rgba(148,163,184,.45);
background:rgba(255,255,255,.9);font-size:13px;outline:none}
.searchwrap input:focus{border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.12)}
.tools select{padding:8px 11px;border-radius:10px;border:1px solid rgba(148,163,184,.45);background:rgba(255,255,255,.9);font-size:12.5px;outline:none;cursor:pointer}
.viewbtn{display:flex;border:1px solid rgba(148,163,184,.45);border-radius:10px;overflow:hidden;background:rgba(255,255,255,.9)}
.viewbtn button{border:0;background:transparent;padding:7px 10px;cursor:pointer;font-size:13px;color:#64748b;line-height:1}
.viewbtn button.on{background:#0f172a;color:#fff}
/* 快捷标签：与搜索同一行，挤不下时自动换行 */
.chips{display:flex;gap:7px;flex-wrap:wrap;align-items:center}
.chip{padding:6px 12px;border-radius:999px;font-size:12px;font-weight:600;cursor:pointer;user-select:none;
background:rgba(255,255,255,.75);color:#64748b;border:1px solid rgba(148,163,184,.4);transition:.15s}
.chip:hover{border-color:#2563eb;color:#2563eb}
.chip.on{background:#0f172a;color:#fff;border-color:#0f172a}
.chip .n{opacity:.7;font-weight:500;margin-left:3px}
/* 卡片 */
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));margin-top:16px}
.card{display:block;position:relative;padding:14px 16px;background:rgba(255,255,255,.72);backdrop-filter:blur(18px) saturate(180%);
border:1px solid rgba(255,255,255,.9);border-radius:16px;text-decoration:none;color:inherit;cursor:pointer;
box-shadow:0 6px 22px -10px rgba(15,23,42,.22);transition:.22s}
.card:hover{transform:translateY(-2px);box-shadow:0 14px 30px -12px rgba(15,23,42,.3);border-color:rgba(37,99,235,.35)}
.card:focus-visible{outline:2px solid #2563eb;outline-offset:2px}
.card.dying{opacity:.85;border-color:rgba(251,146,60,.55)}
.card .open{font-size:12.5px;color:#2563eb;margin-top:8px;display:inline-flex;align-items:center;gap:4px;font-weight:500}
.card:hover .open{text-decoration:underline}
.name{font-weight:600;font-size:15px;display:flex;align-items:center;gap:8px;min-width:0}
.badge{font-size:10.5px;font-weight:600;line-height:1;padding:3px 6px;border-radius:999px;background:#eef2ff;color:#4f46e5;border:1px solid #c7d2fe;white-space:nowrap}
.path{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;color:#2563eb;margin:3px 0 8px;word-break:break-all}
.desc{font-size:12.5px;color:#475569;margin:0 0 8px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.meta{display:flex;gap:12px;font-size:12px;color:#64748b;flex-wrap:wrap;align-items:center}
.ttl{color:#b45309;font-weight:600}
.ttl.hot{color:#dc2626}
.ttl.cold{color:#059669}
.ttl.perm{color:#059669}
.row{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.rowL{min-width:0;flex:1 1 auto}
.rowR{flex:0 0 auto;display:flex;flex-direction:column;align-items:flex-end;gap:8px}
.dl{font-size:12px;padding:5px 11px;border-radius:999px;background:#0f172a;color:#fff;white-space:nowrap;
text-decoration:none;display:inline-block}
.dl:hover{background:#1e293b}
.cp{font:inherit;font-size:12px;padding:5px 11px;border-radius:999px;background:rgba(255,255,255,.92);color:#334155;
border:1px solid rgba(148,163,184,.5);white-space:nowrap;cursor:pointer;transition:.15s}
.cp:hover{border-color:#2563eb;color:#2563eb}
.cp.ok{background:#059669;color:#fff;border-color:#059669}
.bar{height:4px;border-radius:99px;background:rgba(148,163,184,.25);margin-top:10px;overflow:hidden}
.bar>i{display:block;height:100%;background:linear-gradient(90deg,#2563eb,#7c3aed);transition:width .5s}
.bar.hot>i{background:linear-gradient(90deg,#f97316,#dc2626)}
.empty{padding:40px;text-align:center;color:#94a3b8;background:rgba(255,255,255,.6);border-radius:18px;
border:1px dashed rgba(148,163,184,.5)}
.foot{margin-top:22px;font-size:12px;color:#94a3b8;text-align:center}
a.plain{color:#2563eb;text-decoration:none}
/* 列表视图 */
.grid.list{display:flex;flex-direction:column;gap:8px}
.list .card{padding:10px 14px;border-radius:13px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.list .card .row{flex:1 1 320px;align-items:center;gap:10px}
.list .card .name{font-size:14px;display:inline}
.list .card .path{margin:0;display:inline;font-size:11.5px}
.list .card .desc,.list .card .open,.list .card .bar{display:none}
.list .card .meta{gap:10px}
.list .card .rowR{flex-direction:row;align-items:center;gap:10px}
.list .ttlwrap{margin-left:auto;text-align:right;font-size:12.5px;font-weight:600;white-space:nowrap}
@media(max-width:620px){.grid:not(.list){grid-template-columns:1fr!important}}
</style></head><body><div class="wrap">
<div class="stickytop">
<div class="hdr">
  <div class="title">
    <div class="logo">◪</div>
    <div>
      <h1>${esc(title)}</h1>
      <div class="sub0">到期自动处理 · 实时倒计时</div>
    </div>
  </div>
  <a class="gear" href="/admin" title="管理">⚙ 管理</a>
</div>
<div class="stats" id="stats"></div>
<div class="tools">
  <div class="searchwrap"><span class="sic">🔍</span><input id="q" placeholder="搜索项目名 / 说明 / 路径…" oninput="window.__pf()"></div>
  <select id="flt" onchange="window.__pf()">
    <option value="all">全部时长</option>
    <option value="perm">永久</option>
    <option value="day">24 小时内到期</option>
    <option value="week">7 天内到期</option>
    <option value="dl">可下载</option>
  </select>
  <select id="sortby" onchange="window.__psort()" title="排序方式">
    <option value="views">按访问次数</option>
    <option value="time">按创建时间</option>
  </select>
  <div class="viewbtn">
    <button id="vgrid" class="on" onclick="window.__pv('grid')" title="网格视图">▦</button>
    <button id="vlist" onclick="window.__pv('list')" title="列表视图">☰</button>
  </div>
  <div class="chips" id="chips"></div>
</div>
</div>
<div class="grid" id="grid"><div class="empty">正在读取项目清单…</div></div>
<div class="foot">到期项目自动处理 · 实时倒计时</div>
</div>
<script>
(function(){
  var grid=document.getElementById('grid'), stats=document.getElementById('stats'), chipsEl=document.getElementById('chips');
  var data=null, tick=0, activeTag='';
  function pad(n){return String(n).padStart(2,'0');}
  function fmt(ms){
    if(ms<=0) return '已到期';
    var d=Math.floor(ms/86400000), h=Math.floor(ms%86400000/3600000),
        m=Math.floor(ms%3600000/60000), s=Math.floor(ms%60000/1000);
    if(d>0) return d+'天'+h+'小时';
    if(h>0) return h+'h'+pad(m)+'m'+pad(s)+'s';
    return m+'m'+pad(s)+'s';
  }
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function ago(ts){
    if(!ts) return '';
    var d=Date.now()-ts; if(d<0) d=0;
    var m=Math.floor(d/60000), h=Math.floor(d/3600000), day=Math.floor(d/86400000);
    if(day>0) return day+' 天前';
    if(h>0) return h+' 小时前';
    if(m>0) return m+' 分钟前';
    return '刚刚';
  }
  function absTime(ts){
    if(!ts) return '';
    var d=new Date(ts);
    function p(n){return String(n).padStart(2,'0');}
    return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())+' '+p(d.getHours())+':'+p(d.getMinutes());
  }
  function matchTag(p,tag){
    var hay=((p.name||'')+' '+(p.desc||'')+' '+(p.path||'')+' '+(p.slug||'')+' '+(p.link||'')).toLowerCase();
    return hay.indexOf(tag)>=0;
  }
  function renderStats(){
    if(!data) return;
    var now=Date.now()+(tick*1000);
    var alive=data.projects.filter(function(p){ return p.permanent || p.expireAt>now; });
    var perm=alive.filter(function(p){return p.permanent||!p.expireAt;}).length;
    var links=alive.filter(function(p){return !!p.isLink;}).length;
    var exp=alive.length-perm;
    stats.innerHTML='<span class="stat"><span class="dot"></span><span class="num">'+alive.length+'</span> 在线项目</span>'+
      (perm?'<span class="stat"><span class="num">'+perm+'</span> 永久</span>':'')+
      (exp?'<span class="stat"><span class="num">'+exp+'</span> 限时</span>':'')+
      (links?'<span class="stat muted"><span class="num">'+links+'</span> 外链</span>':'');
  }
  function renderChips(){
    if(!data) return;
    var now=Date.now()+(tick*1000);
    var alive=data.projects.filter(function(p){ return p.permanent || p.expireAt>now; });
    // 从项目名高频提取一些快捷标签（按出现次数排序，取前 8 个有意义的词）
    var freq={};
    alive.forEach(function(p){
      var parts=((p.name||'')+' '+(p.desc||'')).toLowerCase().split(/[\s\/\-_\.·、，,]+/);
      parts.forEach(function(w){
        w=(w||'').trim(); if(w.length<2||w.length>16) return;
        if(/^[0-9]+$/.test(w)) return;
        freq[w]=(freq[w]||0)+1;
      });
      if(p.isLink) freq['外链']=(freq['外链']||0)+1;
      if(p.permanent||!p.expireAt) freq['永久']=(freq['永久']||0)+1;
    });
    var tags=Object.keys(freq).sort(function(a,b){return freq[b]-freq[a];}).slice(0,10);
    var hasLink=alive.some(function(p){return p.isLink;});
    var hasPerm=alive.some(function(p){return p.permanent||!p.expireAt;});
    var hasExp=alive.some(function(p){return !(p.permanent||!p.expireAt);});
    var chipList=[];
    if(hasLink) chipList.push({t:'外链',kind:'link'});
    if(hasPerm) chipList.push({t:'永久',kind:'perm'});
    if(hasExp) chipList.push({t:'限时',kind:'exp'});
    tags.forEach(function(t){ if(!['外链','永久','限时'].includes(t) && freq[t]>=2) chipList.push({t:t,kind:'tag'}); });
    chipsEl.innerHTML=chipList.slice(0,12).map(function(c){
      var on=(activeTag===c.t);
      var n=c.kind==='link'?alive.filter(function(p){return p.isLink;}).length
        :c.kind==='perm'?alive.filter(function(p){return p.permanent||!p.expireAt;}).length
        :c.kind==='exp'?alive.filter(function(p){return !(p.permanent||!p.expireAt);}).length
        :alive.filter(function(p){return matchTag(p,c.t);}).length;
      return '<span class="chip'+(on?' on':'')+'" data-tag="'+esc(c.t)+'" data-kind="'+c.kind+'">'+esc(c.t)+'<span class="n">'+n+'</span></span>';
    }).join('');
  }
  chipsEl.addEventListener('click',function(e){
    var c=e.target.closest('.chip'); if(!c) return;
    activeTag=(activeTag===c.dataset.tag)?'':c.dataset.tag;
    // 标签选：清掉文本搜索，避免双重过滤；点已选标签可取消
    if(activeTag){ document.getElementById('q').value=''; }
    render();
  });
  function render(){
    if(!data) return;
    var now=Date.now()+(tick*1000);
    var q=(document.getElementById('q').value||'').trim().toLowerCase();
    var flt=document.getElementById('flt').value;
    var alive=data.projects.filter(function(p){ return p.permanent || p.expireAt>now; });
    var shown=alive.filter(function(p){
      var perm=p.permanent||!p.expireAt;
      var remain=perm?0:(p.expireAt-now);
      // 标签快捷过滤优先
      if(activeTag){
        if(activeTag==='外链' && !p.isLink) return false;
        else if(activeTag==='永久' && !perm) return false;
        else if(activeTag==='限时' && perm) return false;
        else if(!['外链','永久','限时'].includes(activeTag) && !matchTag(p,activeTag)) return false;
      } else if(q){
        var hay=((p.name||'')+' '+(p.desc||'')+' '+(p.path||'')+' '+(p.slug||'')+' '+(p.link||'')).toLowerCase();
        if(hay.indexOf(q)<0) return false;
      }
      if(flt==='perm') return perm;
      if(flt==='day') return !perm && remain<=86400000;
      if(flt==='week') return !perm && remain<=7*86400000;
      if(flt==='dl') return !!p.download;
      return true;
    });
    renderStats();
    renderChips();
    var sm=window.__sort||'views';
    shown.sort(function(a,b){
      if(sm==='time') return (b.createdAt||0)-(a.createdAt||0);
      var dv=(b.views||0)-(a.views||0);
      return dv ? dv : ((b.createdAt||0)-(a.createdAt||0));
    });
    if(!shown.length){ grid.innerHTML='<div class="empty">'+(alive.length?'没有符合条件的项目':'暂无在线项目')+'</div>'; return; }
    grid.innerHTML=shown.map(function(p){
      var perm=p.permanent||!p.expireAt;
      var remain=perm?0:(p.expireAt-now);
      var total=perm?1:(p.expireAt-p.createdAt||1);
      var pct=perm?100:Math.max(0,Math.min(100, remain/total*100));
      var hot=!perm&&remain<6*3600e3, cold=perm||remain>36*3600e3;
      var cls=perm?'ttl perm':(hot?'ttl hot':(cold?'ttl cold':'ttl'));
      var ttlTxt=perm?'永久':('剩余 '+fmt(remain));
      var dlBtn=p.download?'<a class="dl" href="'+esc(p.download)+'" onclick="event.stopPropagation()">下载 zip</a>':'';
      var isLink=!!p.isLink;
      var href=isLink?esc(p.link):esc(p.path);
      var copyTarget=isLink?(p.link||''):(location.origin+p.path);
      var cpBtn='<button class="cp" data-copy="'+esc(copyTarget)+'" title="复制链接">📋 复制</button>';
      var pathTxt=isLink?esc(p.link):esc(p.path);
      var openTxt=isLink?'点击跳转外部站 →':'点击查看 →';
      var nameBadge=isLink?'<span class="badge">外部链接</span>':'';
      var metaCount=isLink?'<span>外链</span>':('<span>'+(p.files||0)+' 文件</span><span>'+esc(p.sizeText)+'</span>');
      var viewsTxt=isLink?'<span title="外链不统计访问">👁 —</span>':'<span title="访问次数">👁 '+(p.views||0)+'</span>';
      var timeTxt='<span title="创建于 '+absTime(p.createdAt)+'">🕒 '+ago(p.createdAt)+'</span>';
      return '<div class="card'+(!perm&&hot?' dying':'')+'" role="link" tabindex="0" data-href="'+href+'" data-ext="'+(isLink?'1':'0')+'" data-card="1">'+
        '<div class="row"><div class="rowL">'+
        '<div class="name">'+esc(p.name)+nameBadge+'</div>'+
        '<div class="path">'+pathTxt+'</div>'+
        (p.desc?'<div class="desc">'+esc(p.desc)+'</div>':'')+
        '<div class="meta"><span class="'+cls+'">'+ttlTxt+'</span>'+metaCount+viewsTxt+timeTxt+'</div>'+
        '<span class="open">'+openTxt+'</span></div>'+
        '<div class="rowR">'+cpBtn+dlBtn+'</div>'+
        '</div><div class="bar'+(!perm&&hot?' hot':'')+'"><i style="width:'+pct.toFixed(1)+'%"></i></div></div>';
    }).join('');
  }
  window.__pf=function(){ activeTag=''; render(); };
  window.__psort=function(){
    window.__sort=document.getElementById('sortby').value;
    try{localStorage.setItem('pv_sort', window.__sort);}catch(e){}
    render();
  };
  window.__pv=function(v){
    var g=document.getElementById('grid');
    g.classList.toggle('list', v==='list');
    g.style.gridTemplateColumns=(v==='list')?'':'repeat(auto-fill,minmax(300px,1fr))';
    document.getElementById('vgrid').classList.toggle('on', v!=='list');
    document.getElementById('vlist').classList.toggle('on', v==='list');
    try{localStorage.setItem('pv_view', v);}catch(e){}
  };
  // 卡片点击/回车跳转（卡片是 div，靠事件委托）。下载按钮单独处理，不触发跳转。
  function goCard(card){
    if(!card) return;
    var href=card.getAttribute('data-href');
    if(!href) return;
    window.open(href,'_blank','noopener');   // 一律新窗口/新标签打开
  }
  function fallbackCopy(txt,done){
    try{
      var ta=document.createElement('textarea'); ta.value=txt; ta.style.position='fixed'; ta.style.opacity='0';
      document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta); done();
    }catch(e){ alert('复制失败：'+txt); }
  }
  function doCopy(btn){
    var txt=btn.getAttribute('data-copy')||'';
    var done=function(){ btn.textContent='✅ 已复制'; btn.classList.add('ok');
      setTimeout(function(){ btn.textContent='📋 复制'; btn.classList.remove('ok'); },1200); };
    if(navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(txt).then(done).catch(function(){ fallbackCopy(txt,done); });
    } else { fallbackCopy(txt,done); }
  }
  grid.addEventListener('click',function(e){
    var cp=e.target.closest('.cp');
    if(cp){ e.stopPropagation(); doCopy(cp); return; }
    if(e.target.closest('.dl')) return;   // 点下载按钮不跳转
    goCard(e.target.closest('.card[data-card]'));
  });
  grid.addEventListener('keydown',function(e){
    if(e.key!=='Enter' && e.key!==' ') return;
    var card=e.target.closest('.card[data-card]');
    if(!card) return;
    e.preventDefault();
    goCard(card);
  });
  fetch('/api/projects').then(function(r){return r.json();}).then(function(d){
    try{ var ss=localStorage.getItem('pv_sort'); if(ss==='time'){ window.__sort='time'; var sb=document.getElementById('sortby'); if(sb) sb.value='time'; } }catch(e){}
    data=d; render();
    try{ var sv=localStorage.getItem('pv_view'); if(sv==='list') window.__pv('list'); else window.__pv('grid'); }catch(e){ window.__pv('grid'); }
    setInterval(function(){ tick++; renderStats(); render(); },1000);
  }).catch(function(e){
    grid.innerHTML='<div class="empty">加载失败：'+e.message+'</div>';
  });
})();
</script></body></html>`;
}

/* ---------------- 门户密码页 ---------------- */

function gateHTML(title, err) {
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title>
<style>
*{box-sizing:border-box}
body{margin:0;min-height:100vh;font:15px/1.5 -apple-system,"PingFang SC","Microsoft YaHei",system-ui,sans-serif;
background:linear-gradient(160deg,#f6f8fc,#eef2f9 60%,#e9eef7);color:#0f172a;
display:flex;align-items:center;justify-content:center;padding:20px}
.box{width:100%;max-width:360px;background:rgba(255,255,255,.85);backdrop-filter:blur(18px);
border:1px solid rgba(255,255,255,.9);border-radius:18px;padding:28px 26px;
box-shadow:0 20px 50px -24px rgba(15,23,42,.35);text-align:center}
.logo{width:48px;height:48px;border-radius:14px;margin:0 auto 14px;display:flex;align-items:center;justify-content:center;
background:linear-gradient(135deg,#2563eb,#7c3aed);color:#fff;font-size:22px;box-shadow:0 8px 18px -8px rgba(37,99,235,.55)}
h1{font-size:18px;margin:0 0 6px;letter-spacing:-.01em}
p{color:#94a3b8;font-size:12.5px;margin:0 0 18px}
input{width:100%;padding:11px 13px;border-radius:11px;border:1px solid rgba(148,163,184,.5);
background:#fff;font-size:14px;outline:none;margin-bottom:12px}
input:focus{border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.12)}
button{width:100%;padding:11px;border:0;border-radius:11px;cursor:pointer;font-size:14px;font-weight:600;color:#fff;
background:linear-gradient(135deg,#2563eb,#7c3aed)}
button:hover{filter:brightness(1.05)}
.err{color:#dc2626;font-size:12.5px;margin:-4px 0 12px}
</style></head><body>
<div class="box">
  <div class="logo">🔒</div>
  <h1>${esc(title)}</h1>
  <p>请输入访问密码</p>
  ${err ? `<div class="err">${esc(err)}</div>` : ''}
  <form method="POST" action="/api/portal/login">
    <input type="password" name="password" placeholder="密码" autofocus autocomplete="current-password">
    <button type="submit">进入</button>
  </form>
</div></body></html>`;
}

function html404(msg, base) {
  return new Response(
    `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>404 Not Found</title>
<style>body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
font:15px/1.6 -apple-system,"PingFang SC",system-ui,sans-serif;background:#f6f8fc;color:#0f172a}
.box{text-align:center;padding:40px 48px;background:#fff;border-radius:20px;
box-shadow:0 10px 40px -20px rgba(15,23,42,.3)}h1{font-size:44px;margin:0;color:#2563eb}
p{color:#64748b;margin:10px 0 20px}a{color:#2563eb;text-decoration:none;font-weight:600}</style>
</head><body><div class="box"><h1>404</h1><p>${esc(msg)}</p><a href="${esc(base)}">← 返回项目列表</a></div></body></html>`,
    { status: 404, headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' } }
  );
}

function html410(msg, base) {
  return new Response(
    `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>项目已到期</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;font:15px/1.6 -apple-system,"PingFang SC",system-ui,sans-serif;background:#f6f8fc;color:#0f172a}
a{color:#2563eb;text-decoration:none;font-weight:600}</style>
</head><body><div style="text-align:center"><h1 style="font-size:40px;margin:0;color:#f97316">已到期</h1>
<p style="color:#64748b">${esc(msg || '这个项目已超过存活时限。')}</p>${base ? `<a href="${esc(base)}">← 返回项目列表</a>` : ''}</div></body></html>`,
    { status: 410, headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' } }
  );
}
