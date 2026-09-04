// 主题切换。三态 system / light / dark，另有热力色蓝/暖两选（06 文档 §3.1、§3.2）。
//
// **首屏那一帧不由这里负责**：服务端按 `ui.theme` 直接渲染 `<html data-theme>`
// （web.py:index）。这里管的是切换与本地偏好的回读——它跑在首次绘制之后，因此
// 不需要、也不可能防闪白。原先那个职责在 `static/js/theme.js`（一个阻塞的普通脚本），
// 15 文档 §11.3 把它换掉了。
//
// 双写仍然保留：localStorage 是**本浏览器**的偏好，配置是跨浏览器一致的那份。写配置
// 失败不影响本地生效——设置服务不可用时主题仍然可切。
import { emit } from './bus.ts';
import { getState, setState } from './store.ts';

const THEME_KEY = 'omnisight.theme';
const HEAT_KEY = 'omnisight.heat';
export const THEMES = ['system', 'light', 'dark'] as const;
export type Theme = (typeof THEMES)[number];
export type Heat = 'blue' | 'warm';

function isTheme(value: string): value is Theme {
  return (THEMES as readonly string[]).includes(value);
}

export function apply(theme: string, heat: string): void {
  const root = document.documentElement;
  if (theme === 'light' || theme === 'dark') root.dataset.theme = theme;
  else delete root.dataset.theme;
  if (heat === 'warm') root.dataset.heat = 'warm';
  else delete root.dataset.heat;
  try {
    localStorage.setItem(THEME_KEY, theme);
    localStorage.setItem(HEAT_KEY, heat === 'warm' ? 'warm' : 'blue');
  } catch {
    // 隐私模式：本次会话仍然生效，只是下次启动会闪一下。
  }
  // 图表颜色取自 CSS 变量，主题变了必须重绘（06 文档 §11 第 2 点）。
  emit('theme:changed', { theme, heat });
}

export function set(theme: string): Theme {
  const next = isTheme(theme) ? theme : 'system';
  setState('theme', next);
  apply(next, getState().heat);
  return next;
}

export function setHeat(heat: string): Heat {
  const next: Heat = heat === 'warm' ? 'warm' : 'blue';
  setState('heat', next);
  apply(getState().theme, next);
  return next;
}

export function cycle(): Theme {
  const index = THEMES.indexOf(getState().theme as Theme);
  return set(THEMES[(index + 1) % THEMES.length]);
}

/**
 * 启动时读回本地偏好；随后 /settings 的值到位会覆盖它。
 *
 * **服务端渲染的那一档是回退值，不是被覆盖的值。** 优先级是
 * localStorage（本浏览器）> `<html data-theme>`（服务端按配置渲染）> 跟随系统。
 * 少了中间那一档，换一个浏览器首次打开时会从深色闪回跟随系统——服务端刚渲染对的
 * 东西被前端第一件事擦掉，比不渲染更糟。
 *
 * `data-heat` 没有对应的配置字段，所以它只有 localStorage 一个来源。这不会闪：
 * 热力色令牌只被 `.heat-cell` 与键帽用（tokens.css 里 `[data-heat="warm"]` 是唯一
 * 的选择器），而那些元素本来就要等 JS 才存在。
 */
export function restore(): void {
  const rendered = document.documentElement.dataset.theme || 'system';
  let theme = rendered;
  let heat = 'blue';
  try {
    theme = localStorage.getItem(THEME_KEY) || rendered;
    heat = localStorage.getItem(HEAT_KEY) || 'blue';
  } catch {
    // 读不到就沿用服务端渲染的那一档。
  }
  setState('theme', isTheme(theme) ? theme : 'system');
  setState('heat', heat === 'warm' ? 'warm' : 'blue');
  apply(getState().theme, getState().heat);
}

/** 跟随系统时，系统切换深浅要重绘图表——CSS 会自己换色，canvas 不会。 */
export function watchSystem(): void {
  const query = window.matchMedia('(prefers-color-scheme: dark)');
  query.addEventListener('change', () => {
    if (getState().theme === 'system') {
      emit('theme:changed', { theme: 'system', heat: getState().heat });
    }
  });
}

export function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}
