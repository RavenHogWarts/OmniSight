// 用无头浏览器读仪表盘：截图 + 可量化的版面报告（14 文档 §8.3）。
//
// 为什么需要它：14 文档 §8.3 那张"只能用眼睛确认的"清单里，有一半其实是可量化的——
// 「键面数值要么 ≥11px 要么不印」「不横向溢出」「主列不超过 1240px」「1024/1280/1440/1920
// 四档」「深浅两色」「强制颜色模式」「prefers-reduced-motion」。这些判据不需要眼睛，
// 需要的是一个能读到 computed style 与 getBoundingClientRect 的浏览器。
//
// PROGRESS:1444 曾以"Node 依赖树 + 数百 MB 浏览器下载"否掉 Playwright。这里两条都不成立：
// 用的是 playwright-core（**1 个包、0 个传递依赖**）驱动**机器上已装的 Edge**
// （channel: 'msedge'，不下载任何浏览器），且它是 devDependency——产物里依然没有 npm 包。
// 15 文档 §5 末要求"Node 依赖树进仓库后重新评估"，这就是那次评估的结果。
//
// 用法（一般由 tools/page.py 调起，它会先把开发服务器准备好）::
//
//     node tools/page.mjs --view keyboard --width 1280 --theme dark
//     node tools/page.mjs --all                      # 四视图 × 四宽度 × 深浅
//     node tools/page.mjs --view overview --forced-colors --reduced-motion

import { chromium } from 'playwright-core';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DEV_DIR = path.join(ROOT, '.dev');

/** 报告里的路径一律用正斜杠：它要被贴进 Markdown 与终端，反斜杠在两处都要再转义一次。 */
const rel = (target) => path.relative(ROOT, target).split(path.sep).join('/');

const VIEWS = ['overview', 'apps', 'keyboard', 'insights'];
/** 14 文档 §8.3 点名的四档，外加 2560（§2.20 P3-5 的超宽屏判据）。 */
const WIDTHS = [1024, 1280, 1440, 1920];
/** 14 文档 §2.5 P1-2：键面数字在常见窗口宽度下只有 7–9px，判据是"≥11px 或不印"。 */
const MIN_FONT_PX = 11;
/** 14 文档 §4.1 / §2.20：主列不该无限拉宽，正文行长会失控。 */
const MAX_MAIN_PX = 1240;

function parseArgs(argv) {
  const args = {
    views: [], widths: [], themes: [], range: 'week',
    all: false, forcedColors: false, reducedMotion: false,
    fullPage: false, outDir: path.join(DEV_DIR, 'shots'),
    settings: false, onboarding: false, timeout: 15000, quiet: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = () => argv[i += 1];
    if (arg === '--view') args.views.push(next());
    else if (arg === '--width') args.widths.push(Number(next()));
    else if (arg === '--theme') args.themes.push(next());
    else if (arg === '--range') args.range = next();
    else if (arg === '--all') args.all = true;
    else if (arg === '--settings') args.settings = true;
    else if (arg === '--onboarding') args.onboarding = true;
    else if (arg === '--forced-colors') args.forcedColors = true;
    else if (arg === '--reduced-motion') args.reducedMotion = true;
    else if (arg === '--full-page') args.fullPage = true;
    else if (arg === '--out') args.outDir = path.resolve(next());
    else if (arg === '--timeout') args.timeout = Number(next());
    else if (arg === '--quiet') args.quiet = true;
    else throw new Error(`未知参数：${arg}`);
  }
  if (args.all) {
    args.views = VIEWS;
    args.widths = WIDTHS;
    args.themes = ['light', 'dark'];
  }
  if (!args.views.length) args.views = ['overview'];
  if (!args.widths.length) args.widths = [1440];
  if (!args.themes.length) args.themes = ['light'];
  for (const view of args.views) {
    if (!VIEWS.includes(view)) throw new Error(`--view 只能是 ${VIEWS.join(' / ')}，收到 ${view}`);
  }
  return args;
}

/** 端口与令牌由开发服务器写进 .dev/runtime.json（与生产同一个文件、同一个写法）。 */
async function readRuntime() {
  const file = path.join(DEV_DIR, 'runtime.json');
  try {
    const raw = JSON.parse(await readFile(file, 'utf8'));
    if (!raw.port || !raw.token) throw new Error('字段不全');
    return raw;
  } catch (error) {
    throw new Error(
      `读不到 ${file}（${error.message}）。先起开发服务器：\n`
      + '  .venv/Scripts/python tools/devserver.py\n'
      + '或者直接用 tools/page.py，它会自己把服务器准备好。',
    );
  }
}

/**
 * 在页面里跑的审计。**必须自包含**：它被序列化后在浏览器里执行，拿不到这个文件的作用域。
 *
 * 只报"能拿去改代码"的东西，不报整棵 DOM——一份 3000 行的 DOM 转成文本对判断版面
 * 毫无帮助，而 40 个带尺寸的盒子有。
 */
function auditInPage({ minFontPx, maxMainPx }) {
  const label = (el) => {
    if (el.id) return `#${el.id}`;
    const cls = (el.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean);
    const tag = el.tagName.toLowerCase();
    return cls.length ? `${tag}.${cls.slice(0, 2).join('.')}` : tag;
  };
  const selectorFor = (el) => {
    const parts = [];
    for (let node = el, depth = 0; node && node !== document.body && depth < 3; depth += 1) {
      parts.unshift(label(node));
      if (node.id) break;
      node = node.parentElement;
    }
    return parts.join(' > ');
  };
  const box = (el) => {
    const r = el.getBoundingClientRect();
    return {
      x: Math.round(r.x), y: Math.round(r.y),
      w: Math.round(r.width), h: Math.round(r.height),
    };
  };
  const shown = (el) => {
    const style = getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none' || style.opacity === '0') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  /** `.sr-only` 是 1px + clip-path 的屏幕阅读器专用文字（base.css:57）。它当然"被裁"、
   *  当然"字号异常"——把它算进版面问题会让每一份报告都带两条固定的假警报。 */
  const screenReaderOnly = (el) => {
    const style = getComputedStyle(el);
    if (style.clipPath && style.clipPath !== 'none') return true;
    const r = el.getBoundingClientRect();
    return r.width <= 2 || r.height <= 2;
  };
  /** 自己有文字、且没有带文字的子元素——避免同一段文字被父子各报一次。 */
  const isTextLeaf = (el) => {
    const own = Array.from(el.childNodes)
      .filter((n) => n.nodeType === 3)
      .map((n) => n.textContent.trim())
      .join('');
    return own.length > 0;
  };
  const text = (el) => el.textContent.trim().replace(/\s+/g, ' ').slice(0, 48);

  /** 内容区是否真的分成了两列。只看 grid 的列模板，比数子元素靠得住。 */
  const hasSideColumn = () => {
    const host = document.querySelector('.main') || document.querySelector('main');
    if (!host) return false;
    const columns = getComputedStyle(host).gridTemplateColumns.trim().split(/\s+/);
    return columns.length > 1;
  };

  const all = Array.from(document.querySelectorAll('body *')).filter(
    (el) => !['SCRIPT', 'STYLE', 'SVG', 'PATH', 'DEFS', 'SYMBOL', 'USE'].includes(el.tagName)
      && shown(el),
  );

  const tinyText = [];
  const clipped = [];
  for (const el of all) {
    if (!isTextLeaf(el) || screenReaderOnly(el)) continue;
    const size = Number.parseFloat(getComputedStyle(el).fontSize);
    if (size && size < minFontPx) {
      tinyText.push({ selector: selectorFor(el), fontSize: Math.round(size * 10) / 10, text: text(el) });
    }
    // 文字被容器裁掉。ellipsis 是刻意设计，但 overflow:hidden 直接切字不是。
    if (el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflowX !== 'visible') {
      clipped.push({
        selector: selectorFor(el),
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
        ellipsis: getComputedStyle(el).textOverflow === 'ellipsis',
        text: text(el),
      });
    }
  }

  const vw = window.innerWidth;
  const offscreen = all
    .filter((el) => {
      const r = el.getBoundingClientRect();
      return r.width > 1 && (r.right > vw + 1 || r.left < -1);
    })
    .map((el) => ({ selector: selectorFor(el), ...box(el) }));

  // 版面骨架：卡片与区块级容器。这是 agent 真正要看的那份结构。
  const OUTLINE = '.app > header, .periodbar, main, #view-root > *, .card, section, .drawer, .modal';
  const outline = Array.from(document.querySelectorAll(OUTLINE))
    .filter(shown)
    .slice(0, 80)
    .map((el) => ({
      selector: selectorFor(el),
      ...box(el),
      heading: (el.querySelector('h1, h2, h3, .card__title') || {}).textContent?.trim().slice(0, 40) || null,
    }));

  const main = document.querySelector('#view-root') || document.querySelector('main');
  const mainWidth = main ? Math.round(main.getBoundingClientRect().width) : 0;
  const doc = document.scrollingElement || document.documentElement;
  // 外壳宽度判据**读令牌，不写死数字**：14 文档 §4.1 把 --layout-max 从 1240 提到 1440，
  // 而 §4.1 的 ≥1790px 双列档（主列 1240 + 副列 ≥660）是否已实现要由页面自己回答。
  const layoutMax = Number.parseFloat(
    getComputedStyle(document.documentElement).getPropertyValue('--layout-max'),
  ) || 0;

  return {
    title: document.title,
    pageTheme: document.documentElement.dataset.theme || 'system',
    resolvedDark: matchMedia('(prefers-color-scheme: dark)').matches,
    viewport: { width: vw, height: window.innerHeight },
    document: { scrollWidth: doc.scrollWidth, scrollHeight: doc.scrollHeight },
    horizontalOverflow: doc.scrollWidth > vw + 1,
    mainWidth,
    layoutMax,
    // 超宽档：14 文档 §4.1 要求 ≥1790px 时内容区变两列（主列 ≤1240 + 副列 ≥660）。
    // 窄于 1790 时单列铺满 --layout-max 是**正确行为**，不是问题。
    ultrawide: vw >= 1790
      ? { expectedMainPx: maxMainPx, mainOverWide: mainWidth > maxMainPx, twoColumn: hasSideColumn() }
      : null,
    counts: { elements: all.length, cards: document.querySelectorAll('.card').length },
    tinyText: tinyText.slice(0, 40),
    clipped: clipped.slice(0, 40),
    offscreen: offscreen.slice(0, 40),
    outline,
    emptyStates: Array.from(document.querySelectorAll('.empty-state, .error-state'))
      .filter(shown).map((el) => ({ selector: selectorFor(el), text: text(el) })),
    banners: Array.from(document.querySelectorAll('#banners .banner'))
      .filter(shown).map((el) => ({ severity: el.dataset.severity || '', text: text(el) })),
  };
}

/** 等页面真正画完。骨架屏消失 + 视图根有内容，比 networkidle 可靠（30 秒轮询会让它永不静默）。 */
async function waitForRender(page, timeout) {
  await page.waitForFunction(
    () => {
      const root = document.getElementById('view-root');
      return !!root && root.children.length > 0 && document.querySelectorAll('.skeleton').length === 0;
    },
    null,
    { timeout },
  );
  // canvas 的绘制合并在 rAF 里（07 文档 §6.5），骨架屏没了不等于图画完了。
  await page.waitForTimeout(300);
}

async function capture(context, { base, view, width, theme, args }) {
  const page = await context.newPage();
  const console_ = [];
  const failed = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error' || msg.type() === 'warning') {
      console_.push({ type: msg.type(), text: msg.text().slice(0, 300) });
    }
  });
  page.on('pageerror', (error) => console_.push({ type: 'pageerror', text: String(error).slice(0, 300) }));
  page.on('requestfailed', (req) => failed.push({ url: req.url(), error: req.failure()?.errorText || '' }));
  page.on('response', (res) => {
    if (res.status() >= 400) failed.push({ url: res.url(), status: res.status() });
  });

  await page.setViewportSize({ width, height: Math.round(width * 0.6) });
  const url = `${base}/?token=${args.token}#/${view}?range=${args.range}`;
  await page.goto(url, { waitUntil: 'load', timeout: args.timeout });
  await waitForRender(page, args.timeout);
  // 首启说明是必须点掉的模态（08 文档 §6.1：不能随手划掉）。devserver.py 默认已经替它
  // 按过"我看过了"，这里再兜一次——page.mjs 也可能被指向一个手工起的服务器。
  if (!args.onboarding) {
    const primary = page.locator('.onboarding__foot .button--primary');
    if (await primary.count()) {
      await primary.first().click();
      await page.waitForSelector('.onboarding', { state: 'detached', timeout: args.timeout });
      await page.waitForTimeout(200);
    }
  }
  if (args.settings) {
    await page.click('[data-action="settings:open"]');
    await page.waitForSelector('.drawer', { timeout: args.timeout });
    await page.waitForTimeout(200);
  }

  const report = await page.evaluate(auditInPage, { minFontPx: MIN_FONT_PX, maxMainPx: MAX_MAIN_PX });
  const media = [args.forcedColors && 'forced', args.reducedMotion && 'motion'].filter(Boolean);
  const stem = [view, width, theme, ...media, args.settings && 'settings',
    args.onboarding && 'onboarding'].filter(Boolean).join('-');
  const shot = path.join(args.outDir, `${stem}.png`);
  await page.screenshot({ path: shot, fullPage: args.fullPage });
  await page.close();

  return {
    view, width, theme, url,
    screenshot: rel(shot),
    media: { forcedColors: args.forcedColors, reducedMotion: args.reducedMotion },
    console: console_,
    failedRequests: failed,
    ...report,
  };
}

/** 一行一个结论，只讲能拿去改代码的。stdout 是 agent 真正会读的东西。 */
function summarize(result) {
  const lines = [];
  const head = `${result.view} @ ${result.width}px ${result.theme}`
    + ` (page=${result.pageTheme}, dark=${result.resolvedDark})`
    + (result.media.forcedColors ? ' +forced-colors' : '')
    + (result.media.reducedMotion ? ' +reduced-motion' : '');
  lines.push(`── ${head}  →  ${result.screenshot}`);
  const problems = [];
  if (result.horizontalOverflow) {
    problems.push(`横向溢出：document 宽 ${result.document.scrollWidth} > 视口 ${result.viewport.width}`);
  }
  if (result.ultrawide) {
    // 只在 ≥1790px 档判：那是 14 文档 §4.1 唯一要求双列的一档。
    if (!result.ultrawide.twoColumn) {
      problems.push(`超宽屏仍是单列（14 §4.1 要求 ≥1790px 分主列 + 副列）`);
    }
    if (result.ultrawide.mainOverWide) {
      problems.push(`主列 ${result.mainWidth}px 超过 ${result.ultrawide.expectedMainPx}px`);
    }
  }
  for (const item of result.offscreen.slice(0, 5)) {
    problems.push(`出屏：${item.selector} 右边缘 ${item.x + item.w}`);
  }
  for (const item of result.tinyText.slice(0, 8)) {
    problems.push(`字号 ${item.fontSize}px < ${MIN_FONT_PX}px：${item.selector}「${item.text}」`);
  }
  for (const item of result.clipped.slice(0, 5)) {
    if (item.ellipsis) continue;
    problems.push(`文字被裁：${item.selector} ${item.clientWidth}/${item.scrollWidth}「${item.text}」`);
  }
  for (const item of result.console) problems.push(`控制台 ${item.type}：${item.text}`);
  for (const item of result.failedRequests) {
    problems.push(`请求失败 ${item.status || item.error}：${item.url}`);
  }
  for (const item of result.emptyStates) problems.push(`空态：${item.selector}「${item.text}」`);
  if (problems.length === 0) {
    lines.push(`   无异常（${result.counts.cards} 张卡、${result.counts.elements} 个可见元素）`);
  } else {
    for (const problem of problems) lines.push(`   ! ${problem}`);
  }
  return lines.join('\n');
}

async function main(argv) {
  const args = parseArgs(argv);
  const runtime = await readRuntime();
  args.token = runtime.token;
  const base = `http://127.0.0.1:${runtime.port}`;
  await mkdir(args.outDir, { recursive: true });

  // channel: 'msedge' —— 用机器上已装的 Edge，不下载任何浏览器（见文件头）。
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const results = [];
  try {
    for (const theme of args.themes) {
      // 主题**只用 colorScheme 模拟**，不写 localStorage：main.js 的 loadPrefs() 会拿
      // 后端的 ui.theme（默认 'system'）覆盖本地值，写 localStorage 撑不过首屏。
      // 而 'system' 那一档正好由 tokens.css:146 的 prefers-color-scheme 媒体查询接住。
      const context = await browser.newContext({
        colorScheme: theme,
        deviceScaleFactor: 1,
        forcedColors: args.forcedColors ? 'active' : 'none',
        reducedMotion: args.reducedMotion ? 'reduce' : 'no-preference',
      });
      try {
        for (const view of args.views) {
          for (const width of args.widths) {
            const result = await capture(context, { base, view, width, theme, args });
            results.push(result);
            if (!args.quiet) console.log(summarize(result));
          }
        }
      } finally {
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }

  const reportPath = path.join(args.outDir, 'report.json');
  await writeFile(reportPath, JSON.stringify({ base, results }, null, 2), 'utf8');
  if (!args.quiet) {
    console.log(`\n完整报告（含版面骨架与全部测量值）：${rel(reportPath)}`);
  }
  // 有问题不返回非零：这是个观测工具，不是门禁。判断"这算不算问题"是调用方的事。
  return 0;
}

main(process.argv.slice(2)).then(
  (code) => process.exit(code),
  (error) => {
    console.error(error.message || error);
    process.exit(1);
  },
);
