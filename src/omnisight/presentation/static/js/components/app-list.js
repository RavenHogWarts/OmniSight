// 应用列表行（06 文档 §6，07 文档 §6.2）。
//
// keyed 更新以 app_id 复用 DOM 节点。现状两个项目都用 innerHTML = rows.join('') 全量
// 重建，代价是：图标每次刷新都重新发请求并闪烁、滚动位置重置、无法做展开态。
import { assetUrl } from '../core/api.js';
import { h, renderKeyed, setText, setVar } from '../core/dom.js';
import { formatCount, formatDuration, initialOf } from '../domain/format.js';

/**
 * 只负责"一行长什么样"。展开详情、行菜单由调用方通过 data-action 委托处理，
 * 因此动态生成的行不需要逐行 addEventListener（07 文档 §7）。
 */
/**
 * @param {Element} container
 * @param {readonly any[]} apps 周期行与 /apps 元数据合并后的结果（见 views/apps.js 的 joinApps）
 * @param {{ maxSeconds?: number, maxKpm?: number, expandedId?: number | null }} [options]
 */
export function renderAppRows(container, apps, { maxSeconds = 0, maxKpm = 0, expandedId = null } = {}) {
  renderKeyed(
    container,
    apps || [],
    (app) => app.app_id,
    createRow,
    (node, app) => updateRow(node, app, { maxSeconds, maxKpm, expandedId }),
  );
}

function createRow() {
  const icon = h('span', { class: 'app-row__initial' });
  const name = h('span', { class: 'truncate' });
  const running = h('span', { class: 'app-row__running', hidden: true, attrs: { title: '正在运行' } });
  const meta = h('span', { class: 'app-row__meta' });
  const bar = h('div', { class: 'bar app-row__bar' }, h('i'));
  const duration = h('span', { class: 'app-row__duration' });
  const percent = h('span', { class: 'app-row__percent' });
  const presses = h('span', { class: 'app-row__presses' });
  const kpmBar = h('div', { class: 'bar bar--kpm' }, h('i'));
  const kpmText = h('span', { class: 'text-xs muted numeric' });

  return h(
    'div',
    {
      class: 'app-row',
      dataset: { action: 'app:toggle' },
      attrs: { role: 'button', tabindex: '0', 'aria-expanded': 'false' },
    },
    icon,
    h(
      'div',
      { class: 'app-row__main' },
      h('div', { class: 'app-row__name' }, name, running),
      meta,
      bar,
    ),
    h('div', { class: 'app-row__stats' }, duration, percent, presses, kpmBar, kpmText),
  );
}

function updateRow(node, app, { maxSeconds, maxKpm, expandedId }) {
  const [icon, main, stats] = node.children;
  const [nameWrap, meta, bar] = main.children;
  const [name, running] = nameWrap.children;
  const [duration, percent, presses, kpmBar, kpmText] = stats.children;

  node.dataset.appId = String(app.app_id);
  node.dataset.category = app.category || 'uncategorized';
  node.setAttribute('aria-expanded', String(expandedId === app.app_id));

  const label = app.user_alias || app.display_name || app.process_name || `应用 ${app.app_id}`;
  setText(name, label);
  running.hidden = !app.is_running;

  applyIcon(icon, app, label);

  const parts = [app.process_name, app.category_name || null].filter(Boolean);
  setText(meta, parts.join(' \u00b7 '));

  const seconds = Number(app.seconds ?? app.total_seconds ?? 0);
  setVar(bar, '--fill', maxSeconds ? seconds / maxSeconds : 0);
  setText(duration, app.seconds_formatted || app.total_seconds_formatted || formatDuration(seconds));
  setText(percent, app.percent === undefined || app.percent === null ? '' : `${app.percent.toFixed(1)}%`);
  const pressCount = Number(app.presses ?? app.total_presses ?? 0);
  setText(presses, `${formatCount(pressCount)} 次`);
  const kpm = Number(app.kpm || 0);
  setVar(kpmBar, '--fill', maxKpm ? kpm / maxKpm : 0);
  setText(kpmText, kpm ? `${kpm.toFixed(0)} KPM` : '');
}

/**
 * 图标：`icon_url` 由后端给，204 表示"没有图标"（不是 404，应用是存在的）。
 * 取不到就显示首字母色块——这条路径在 icons 能力缺失的机器上是常态。
 */
function applyIcon(node, app, label) {
  const url = app.icon_url ? assetUrl(app.icon_url) : '';
  if (!url) {
    toInitial(node, label);
    return;
  }
  if (node.tagName === 'IMG' && node.dataset.src === url) return;
  const img = h('img', {
    class: 'app-row__icon',
    src: url,
    dataset: { src: url },
    attrs: { alt: '', loading: 'lazy', decoding: 'async' },
  });
  img.addEventListener('error', () => toInitial(img, label));
  node.replaceWith(img);
}

function toInitial(node, label) {
  const span = h('span', { class: 'app-row__initial', text: initialOf(label) });
  node.replaceWith(span);
}
