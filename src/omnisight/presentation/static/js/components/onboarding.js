// 首次运行说明（08 文档 §6.1）。一屏读完的事实，不是 EULA 式的长文。
//
// 三条设计约束：
//   1. **内容全部来自后端**。"记录什么 / 不记录什么"两张清单由后端按当前能力与配置
//      算出来，前端只负责排版——写死在前端就等于承诺一件自己无从保证的事。
//   2. **它不是可以随手划掉的横幅**。首次运行必须点"开始使用"才关闭（那一下就是
//      `POST /onboarding/ack`），因此用 scrim + 对话框而不是 banner。
//   3. **之后仍然找得到**。托盘「关于与隐私说明」与 URL 的 `#about` 都会重新打开它，
//      此时它是普通对话框，Esc 与遮罩点击都能关。
import { get as apiGet, post as apiPost } from '../core/api.js';
import { focusables, h, mount, mountPoint } from '../core/dom.js';
import { fail } from './toast.js';

let openInstance = null;

/** 首屏调用：只在后端说 `required` 时弹出。取数失败一律安静跳过，不挡住仪表盘。 */
export async function maybeShowOnboarding() {
  let payload;
  try {
    payload = await apiGet('/onboarding');
  } catch (error) {
    return null;
  }
  if (!payload || !payload.required) return null;
  return showOnboarding(payload, { mandatory: true });
}

/** 托盘「关于与隐私说明」与 `#about` 的入口：随时可看，随时可关。 */
export async function openAbout() {
  try {
    const payload = await apiGet('/onboarding');
    return showOnboarding(payload, { mandatory: false });
  } catch (error) {
    fail('无法读取隐私说明');
    return null;
  }
}

export function showOnboarding(payload, { mandatory = false } = {}) {
  if (openInstance) openInstance.close();
  const host = mountPoint('overlays');
  const opener = /** @type {HTMLElement | null} */ (document.activeElement);

  const dialog = h('div', {
    class: 'onboarding',
    attrs: {
      role: 'dialog',
      'aria-modal': 'true',
      'aria-labelledby': 'onboarding-title',
      tabindex: '-1',
    },
  });
  const scrim = h('div', { class: 'scrim' });

  const close = () => {
    document.removeEventListener('keydown', onKeydown, true);
    scrim.remove();
    dialog.remove();
    openInstance = null;
    if (opener && typeof opener.focus === 'function') opener.focus();
  };

  /** @param {KeyboardEvent} event */
  function onKeydown(event) {
    if (event.key === 'Escape' && !mandatory) {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== 'Tab') return;
    const items = focusables(dialog, 'button, a[href]');
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    } else if (!dialog.contains(document.activeElement)) {
      event.preventDefault();
      first.focus();
    }
  }

  const accept = async () => {
    if (mandatory) {
      try {
        await apiPost('/onboarding/ack', {});
      } catch (error) {
        // 记不住也让用户进得去——下次再问一遍，比把人锁在门外好。
        fail('无法记录你的确认，下次启动可能再次显示这份说明');
      }
    }
    close();
  };

  mount(dialog, ...content(payload, { mandatory, accept, close }));
  // 遮罩点击只在非强制时关闭：首次运行必须走完"我看到了"这一步。
  if (!mandatory) scrim.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown, true);
  host.append(scrim, dialog);
  const firstButton = dialog.querySelector('button');
  if (firstButton) firstButton.focus();
  else dialog.focus();

  openInstance = { close, dialog };
  return openInstance;
}

function content(payload, { mandatory, accept, close }) {
  const platform = payload.platform || {};
  const paths = payload.paths || {};
  const pause = payload.pause || {};
  return [
    h('div', { class: 'onboarding__head' },
      h('h2', { id: 'onboarding-title', text: mandatory ? 'OmniSight 记录什么' : '关于与隐私说明' }),
      h('p', { class: 'muted', text: '本机运行，无账号、不联网、无遥测。' })),

    h('div', { class: 'onboarding__lists' },
      factList('会记录', payload.records || [], 'onboarding__item--yes', '✓'),
      factList('不记录', payload.not_records || [], 'onboarding__item--no', '✗')),

    // 平台承诺（12 文档 M6 判据 5）：这句话必须出现，且不暗示已支持跨平台。
    h('div', { class: 'onboarding__notice', attrs: { role: 'note' } },
      h('strong', { text: '平台支持' }),
      h('p', { text: platform.notice || '' }),
      platform.tier_label ? h('p', { class: 'muted', text: platform.tier_label }) : null),

    h('div', { class: 'onboarding__section' },
      h('h3', { text: '数据在哪' }),
      pathRow('数据库', paths.database),
      pathRow('数据目录', paths.data_dir),
      pathRow('日志目录', paths.logs_dir),
      pathRow('配置文件', paths.config),
      h('p', { class: 'muted', text: '托盘菜单里的「打开数据目录」直接跳到这里；卸载时删掉它就没有残留。' })),

    h('div', { class: 'onboarding__section' },
      h('h3', { text: '如何暂停' }),
      h('p', { text: pause.detail || '' })),

    h('div', { class: 'onboarding__foot' },
      h('button', {
        class: 'button button--primary', type: 'button',
        text: mandatory ? '开始使用' : '知道了',
        on: { click: accept },
      }),
      mandatory
        ? h('button', {
            class: 'button', type: 'button', text: '稍后再说',
            attrs: { title: '这份说明会在下次启动时再次出现' },
            on: { click: close },
          })
        : null),
  ];
}

function factList(title, items, itemClass, mark) {
  return h('section', { class: 'onboarding__list' },
    h('h3', { text: title }),
    h('ul', {},
      ...items.map((item) => h('li', { class: `onboarding__item ${itemClass}` },
        h('span', { class: 'onboarding__mark', attrs: { 'aria-hidden': 'true' }, text: mark }),
        h('div', {},
          h('span', { text: item.text || '' }),
          item.detail ? h('p', { class: 'muted', text: item.detail }) : null)))));
}

function pathRow(label, value) {
  if (!value) return null;
  return h('div', { class: 'onboarding__path' },
    h('span', { class: 'onboarding__path-label', text: label }),
    // 路径用 code 而不是普通文本：Windows 路径里的反斜杠在等宽字体下才不易读错。
    h('code', { text: value }));
}
