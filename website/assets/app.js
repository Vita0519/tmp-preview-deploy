/* tmp-preview 官网：中英切换 + 目录高亮 + 移动端菜单 */
(function () {
  const EN = {
    'nav.why': 'Why', 'nav.install': 'Install', 'nav.agent': 'For agents', 'nav.api': 'API', 'nav.faq': 'FAQ',

    'side.start': 'Get started', 'side.intro': 'Overview', 'side.why': 'What it solves', 'side.screens': 'Screens',
    'side.install': 'Install', 'side.docker': 'Docker Compose', 'side.fnos': 'fnOS package', 'side.source': 'From source', 'side.public': 'Public access',
    'side.usage': 'Usage', 'side.projects': 'Projects & links', 'side.members': 'Members & keys', 'side.agent': 'For agents', 'side.portal': 'Portal & folders',
    'side.ref': 'Reference', 'side.features': 'Features', 'side.arch': 'Architecture', 'side.api': 'API', 'side.faq': 'FAQ', 'side.release': 'Releases', 'side.license': 'License',

    'hero.kicker': 'SELF-HOSTED · AGPL-3.0',
    'hero.title': 'Turn any folder into a preview link that expires',
    'hero.lead': 'Upload a folder or a zip and get a shareable preview URL immediately. When it expires, access stops or files are deleted — no cleanup later. Multiple members share one instance, each seeing only their own projects; admins see everything.',
    'hero.cta1': 'Get started', 'hero.cta2': 'Download fnOS package',
    'hero.m1': 'Stack', 'hero.m1v': 'One container: FastAPI + SQLite + local disk + Vue 3 console',
    'hero.m2': 'Image', 'hero.m3': 'Default port', 'hero.m3v': 'Compose 8080 · fnOS app 519',
    'hero.m4': 'Data', 'hero.m4v': 'Everything on local <code>/data</code>: SQLite + project files + zips',
    'hero.cap': 'Console: project list, traffic numbers, category and folder filters',

    'why.title': 'What it solves',
    'why.p1': 'Front-end work, prototypes, client reviews — there is always something temporary to share: a build artifact for acceptance, a one-off dashboard, a demo for a colleague. Cloud drives are heavy, object storage never expires, and months later a pile of links is still live.',
    'why.p2': 'tmp-preview reduces it to one action: upload → get a link → it expires. It is also built for several agents on one machine — each agent gets its own API key and only sees its own projects.',
    'why.c1t': 'Upload and preview', 'why.c1d': 'Folders or zips. Entry point is detected automatically; static sites, single pages and PDFs all open directly.',
    'why.c2t': 'Automatic expiry', 'why.c2d': 'Lifetime derives from visibility. On expiry, access stops or files are deleted — with a live countdown.',
    'why.c3t': 'Member isolation', 'why.c3d': 'Admin / publisher / viewer roles, one key per agent, no cross-visibility.',
    'why.c4t': 'Data stays local', 'why.c4d': 'SQLite plus local disk. A backup is a single zip, no cloud dependency.',

    'screens.title': 'Screens',
    'screens.c1': 'Project detail: visibility, expiry, file list, destructive actions',
    'screens.c2': 'Settings: color series, site icon, default lifetimes, upload limit',
    'screens.c3': 'Public portal: card wall, browsable by category and tags',

    'docker.title': 'Install · Docker Compose',
    'docker.p1': 'Recommended. Images are published on ghcr, so there is nothing to build locally.',
    'docker.p2': 'Open <code>http://&lt;host-ip&gt;:8080</code> and sign in with the admin account from <code>.env</code>.',
    'docker.th1': 'Variable', 'docker.th2': 'Default', 'docker.th3': 'Notes',
    'docker.v1': 'Published port', 'docker.v2': 'Initial admin password; ignored once an account exists',
    'docker.v3': 'Image version; set to latest to track upstream, pull before upgrading', 'docker.v4': 'Allow anonymous access to the portal',
    'docker.v5': 'Per-project size limit',
    'docker.note': 'Cannot reach ghcr? Comment out <code>image:</code>, uncomment the <code>build:</code> block and run <code>docker compose up -d --build</code> to build locally.',

    'fnos.title': 'Install · 飞牛 fnOS package',
    'fnos.p1': 'A native .fpk package is available. Install it from the app center; data lives in the app data directory and survives uninstall.',
    'fnos.s1': 'Download <a href="https://github.com/Vita0519/tmp-preview-deploy/releases/latest/download/tmp-preview.fpk">tmp-preview.fpk</a> (latest)',
    'fnos.s2': 'Make sure the NAS can pull the image: <code>docker pull ghcr.io/vita0519/tmp-preview:2.0.1</code>. Private repos need the package set to Public or a <code>docker login ghcr.io</code>',
    'fnos.s3': 'App Center → Manual install → pick the fpk, fill in the admin account',
    'fnos.s4': 'Open <code>http://&lt;nas-ip&gt;:519</code>',
    'fnos.warn': 'Port 519 is privileged. If the app center starts the container as a normal user and binding fails, change all three port references to 10519.',

    'source.title': 'Install · From source',
    'source.p1': 'For machines without Docker, or when you want to modify the code. The backend serves the built front-end directly.',

    'public.title': 'Public access',
    'public.p1': 'No public IP? Expose the service with Cloudflare Tunnel — no router port forwarding required.',
    'public.warn': 'Do not drop <code>--protocol http2</code>. Home connections often throttle UDP; with the default QUIC uploads drop to tens of KB/s and large files hit 524.',
    'public.p2': 'Cloudflare Free caps a single request at 100 seconds of origin response time. Depending on your uplink, uploads beyond roughly 30–50MB will hit 524 — compress to a zip first, or upload over the LAN. Behind your own reverse proxy, keep <code>client_max_body_size</code> at or above the upload limit and <code>proxy_read_timeout</code> / <code>proxy_send_timeout</code> at 300s or more.',

    'proj.title': 'Projects & links',
    'proj.p1': 'Every upload yields three kinds of URLs, each with one job:',
    'proj.th1': 'Path', 'proj.th2': 'Purpose',
    'proj.r1': 'Visitor shell: title, live countdown, download button, copy link',
    'proj.r2': 'Raw project files; embeddable in an iframe or referenced as sub-resources',
    'proj.r3': 'Zip download (only when downloads are enabled)',
    'proj.h3': 'Entry point rules',
    'proj.l1': 'Exactly one file: that file is the entry — <code>report.html</code>, <code>menu.pdf</code>, anything opens directly',
    'proj.l2': 'Multiple files with a root <code>index.html</code>: it becomes the entry',
    'proj.l3': 'Multiple files without <code>index.html</code>: the upload is rejected with a hint to rename, split, or use a zip',
    'proj.h4': 'Visibility and lifetime',
    'proj.th3': 'Visibility', 'proj.th4': 'Default lifetime', 'proj.th5': 'Who can see it',
    'proj.v1': 'Portal', 'proj.v1d': 'Listed on the public portal, anyone can browse',
    'proj.v2': 'Link only', 'proj.v2d': 'Anyone with the URL; not listed on the portal',
    'proj.v3': 'Private', 'proj.v3d': 'Only you (and admins)',
    'proj.forever': 'forever',
    'proj.p2': 'All three defaults are configurable in settings; on expiry the action is either stop access or delete files.',

    'mem.title': 'Members & keys',
    'mem.p1': 'One account binds to one agent, with one <code>pv_...</code> API key. Members cannot see each other; admins see everything and can filter by member.',
    'mem.th1': 'Role', 'mem.th2': 'Can do',
    'mem.r1': 'Admin', 'mem.r1d': 'All projects, members and settings, backup and restore',
    'mem.r2': 'Publisher', 'mem.r2d': 'Own projects only; admins can assign ownership',
    'mem.r3': 'Viewer', 'mem.r3d': 'Portal browsing only, no console access',
    'mem.note': 'After creating a member, click “Copy for agent” — the clipboard holds one sentence with the skill URL, site URL, API key and upload method. Paste it into another agent and it can take over.',

    'agent.title': 'For agents',
    'agent.p1': 'The <code>agentctl</code> CLI is agent-facing: log in once to store the key, then deploy and health-check in one command.',
    'agent.p2': 'Or call the HTTP API directly: <code>POST /api/projects</code> with <code>Authorization: Bearer &lt;key&gt;</code>, sending multipart <code>files[]</code> or <code>zip</code>.',
    'agent.h3': 'Install the skill',
    'agent.skill1': 'Hand the skill folder <code>skills/tmp-preview-agent/</code> to your agent (or let it read <a href="https://github.com/Vita0519/tmp-preview-deploy/blob/main/skills/tmp-preview-agent/SKILL.md">SKILL.md</a>). It documents the commands, flags and permission boundaries; <code>scripts/agentctl.py</code> is the implementation and also works as a plain CLI.',
    'agent.skill2': 'Or open Members, create an account and click “Copy for agent”. The clipboard holds one sentence with the skill URL, site URL, API key and upload method — paste it into any agent and it can take over with no extra setup.',
    'agent.skill3': 'That sentence is generated by your instance: the skill guide is a fixed URL hosted by the project, while the <b>site</b> and <b>API key</b> come from your deployment — paste it into another agent and it connects to your instance.',

    'portal.title': 'Portal & folders',
    'portal.p1': 'The portal is a card wall of every portal-visible project, filterable by category, tag and kind, with RSS. Folders add a second level of grouping and support nesting; the admin sidebar groups them by member.',
    'portal.l1': 'Tags: up to 6 per project, with a tag bar at the top of the portal',
    'portal.l2': 'Traffic: daily trend, total views, download counts',
    'portal.l3': 'RSS: <code>/rss.xml</code>, 404 when the portal is private and you are anonymous',

    'feat.title': 'Feature list',
    'feat.th1': 'Area', 'feat.th2': 'Capabilities',
    'feat.m1': 'Upload', 'feat.d1': 'Folders or zips, automatic entry detection, path traversal checks, on-demand zip packaging',
    'feat.m2': 'Lifecycle', 'feat.d2': 'Default lifetime per visibility, renewal, stop access or delete on expiry, countdown',
    'feat.m3': 'Members', 'feat.d3': 'Three roles, API key rotation, ownership assignment, member search and filtering',
    'feat.m4': 'Organization', 'feat.d4': 'Tags, folders (nested), portal, RSS, bulk actions',
    'feat.m5': 'Appearance', 'feat.d5': 'Six color series, site icon, about-page tip QR codes (WeChat / Alipay)',
    'feat.m6': 'Operations', 'feat.d6': 'Full backup and overwrite restore, traffic stats, activity log, orphan cleanup',

    'arch.title': 'Architecture & data',
    'arch.th1': 'Path', 'arch.th2': 'Contents',
    'arch.r1': 'Projects, members, tags, folders, view counters',
    'arch.r2': 'Project files',
    'arch.r3': 'Uploaded zips or on-demand archives',
    'arch.r4': 'Site icon and about-page QR codes',
    'arch.warn': 'Keep a single worker: view counting and expiry sweeps run in-process. Horizontal scaling requires external counters and locking first.',

    'api.title': 'API reference',
    'api.p1': 'Everything lives under <code>/api</code>. Authenticate with a cookie session or <code>Authorization: Bearer &lt;api key&gt;</code>.',
    'api.th1': 'Method', 'api.th2': 'Path', 'api.th3': 'Description',
    'api.r1': 'Upload (multipart: files[] or zip)',
    'api.r2': 'List with q / tag / kind / status / sort',
    'api.r3': 'Update title, visibility, lifetime, tags, folder',
    'api.r4': 'Delete the project and its files',
    'api.r5': 'Site info, theme, upload limits (public)',
    'api.r6': 'Health check',
    'api.p2': 'The full list and field reference live in <a href="https://github.com/Vita0519/tmp-preview-deploy/blob/main/docs/api.md">docs/api.md</a>.',

    'faq.title': 'FAQ',
    'faq.q1': 'Large uploads keep returning 524?',
    'faq.a1': 'Cloudflare Free allows 100 seconds for the origin to respond; combined with your uplink, roughly 30–50MB is the practical ceiling. First make sure the tunnel uses <code>--protocol http2</code>, then compress to a zip or upload over the LAN.',
    'faq.q2': 'Can several people use it?',
    'faq.a2': 'Yes — multiple members, three roles, one API key each, and no cross-visibility. It is single-tenant by design: one instance serves one team, it is not a SaaS platform.',
    'faq.q3': 'Where is the data, and how do I back it up?',
    'faq.a3': 'Everything is under <code>data/</code> (<code>/data</code> in the container). The settings page can package an online snapshot without stopping the service; restore previews the archive first, and old data is kept under <code>data/.backup-before-restore-*</code>.',
    'faq.q4': 'The fnOS app installs but will not open?',
    'faq.a4': 'Check <code>docker logs tmp-preview</code> first. The usual causes are an image that could not be pulled (set the ghcr package to Public) or no permission to bind port 519 (use 10519).',
    'faq.q5': 'Will upgrading lose data?',
    'faq.a5': 'No. <code>data/</code> is left untouched and the new version fills in schema changes at startup; migrations are idempotent. Upgrade with <code>docker compose pull &amp;&amp; docker compose up -d</code>.',

    'rel.title': 'Versions & releases',
    'rel.p1': 'Versioning is SemVer. Git tags map one-to-one to image tags and are immutable; <code>latest</code> always points at the newest release.',
    'rel.p2': 'The release script validates the working tree, syncs the version, tags, waits for the image build, packages the fpk and creates the release. See <a href="https://github.com/Vita0519/tmp-preview-deploy/blob/main/docs/release.md">docs/release.md</a>.',

    'lic.title': 'License & attribution',
    'lic.p1': 'Released under AGPL-3.0-only. Under the additional terms of section 7(b), any redistribution, modified version or publicly served instance must keep LICENSE and NOTICE, keep the attribution and links in the “About / License” page, the login page and the portal footer, and state prominently that it is “based on tmp-preview, modified” with the modification date. You may not imply endorsement by the original author.',
    'lic.p2': 'Closed-source commercial use and white-labeling require a written exemption from the author.',

    'foot.home': 'Overview', 'foot.install': 'Install', 'foot.api': 'API', 'foot.release': 'Releases',
    'foot.contact': 'Contact', 'foot.qq': 'QQ group 154578485', 'foot.issue': 'Issues',
    'foot.support': 'Support', 'foot.wx': 'WeChat', 'foot.ali': 'Alipay',
    'foot.legal': '© 2026 vita0519 · AGPL-3.0-only · attribution required (see NOTICE)',
  };

  const nodes = Array.from(document.querySelectorAll('[data-i18n], [data-i18n-html]'));
  nodes.forEach((el) => {
    el.dataset.zh = el.hasAttribute('data-i18n-html') ? el.innerHTML : el.textContent;
  });

  const buttons = Array.from(document.querySelectorAll('.lang button'));
  const titles = {
    zh: 'tmp-preview · 临时预览站 — 自托管预览与下载服务',
    en: 'tmp-preview — Self-hosted preview & download service',
  };

  function apply(lang) {
    const en = lang === 'en';
    nodes.forEach((el) => {
      const key = el.dataset.i18n || el.dataset.i18nHtml;
      const isHtml = el.hasAttribute('data-i18n-html');
      const val = (en && EN[key]) || el.dataset.zh;
      if (isHtml) el.innerHTML = val;
      else el.textContent = val;
    });
    document.documentElement.lang = en ? 'en' : 'zh-CN';
    document.title = titles[lang];
    buttons.forEach((b) => b.classList.toggle('on', b.dataset.lang === lang));
    try { localStorage.setItem('tp_lang', lang); } catch (e) {}
  }

  buttons.forEach((b) => b.addEventListener('click', () => apply(b.dataset.lang)));

  let saved = 'zh';
  try { saved = localStorage.getItem('tp_lang') || 'zh'; } catch (e) {}
  if (saved === 'en') apply('en');

  // 目录高亮
  const links = Array.from(document.querySelectorAll('.sidebar a'));
  const sections = links
    .map((a) => document.querySelector(a.getAttribute('href')))
    .filter(Boolean);
  if ('IntersectionObserver' in window && sections.length) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (!e.isIntersecting) return;
          const id = e.target.id;
          links.forEach((a) => a.classList.toggle('on', a.getAttribute('href') === '#' + id));
        });
      },
      { rootMargin: '-80px 0px -70% 0px', threshold: 0 }
    );
    sections.forEach((s) => io.observe(s));
  }

  // 移动端菜单
  const sidebar = document.getElementById('sidebar');
  const menuBtn = document.getElementById('menuBtn');
  if (menuBtn && sidebar) {
    menuBtn.addEventListener('click', () => sidebar.classList.toggle('open'));
    sidebar.addEventListener('click', (e) => {
      if (e.target.tagName === 'A') sidebar.classList.remove('open');
    });
  }
})();
