// 主题切换。三态 system / light / dark，另有热力色蓝/暖两选（06 文档 §3.1、§3.2）。
//
// 双写：localStorage 供下次启动前的阻塞脚本（static/js/theme.js）用，配置供跨浏览器
// 保持一致用。写配置失败不影响本地生效——设置服务不可用时主题仍然可切。
import { emit } from './bus.js';
import { getState, setState } from './store.js';

const THEME_KEY = 'omnisight.theme';
const HEAT_KEY = 'omnisight.heat';
export const THEMES = ['system', 'light', 'dark'];

export function apply(theme, heat) {
  const root = document.documentElement;
  if (theme === 'light' || theme === 'dark') root.dataset.theme = theme;
  else delete root.dataset.theme;
  if (heat === 'warm') root.dataset.heat = 'warm';
  else delete root.dataset.heat;
  try {
    localStorage.setItem(THEME_KEY, theme);
    localStorage.setItem(HEAT_KEY, heat === 'warm' ? 'warm' : 'blue');
  } catch (error) {
    // 隐私模式：本次会话仍然生效，只是下次启动会闪一下。
  }
  // 图表颜色取自 CSS 变量，主题变了必须重绘（06 文档 §11 第 2 点）。
  emit('theme:changed', { theme, heat });
}

export function set(theme) {
  const next = THEMES.includes(theme) ? theme : 'system';
  setState('theme', next);
  apply(next, getState().heat);
  return next;
}

export function setHeat(heat) {
  const next = heat === 'warm' ? 'warm' : 'blue';
  setState('heat', next);
  apply(getState().theme, next);
  return next;
}

export function cycle() {
  const order = ['system', 'light', 'dark'];
  const index = order.indexOf(getState().theme);
  return set(order[(index + 1) % order.length]);
}

/** 启动时读回本地偏好；随后 /settings 的值到位会覆盖它。 */
export function restore() {
  let theme = 'system';
  let heat = 'blue';
  try {
    theme = localStorage.getItem(THEME_KEY) || 'system';
    heat = localStorage.getItem(HEAT_KEY) || 'blue';
  } catch (error) {
    // 读不到就跟随系统。
  }
  setState('theme', THEMES.includes(theme) ? theme : 'system');
  setState('heat', heat === 'warm' ? 'warm' : 'blue');
  apply(getState().theme, getState().heat);
}

/** 跟随系统时，系统切换深浅要重绘图表——CSS 会自己换色，canvas 不会。 */
export function watchSystem() {
  const query = window.matchMedia('(prefers-color-scheme: dark)');
  query.addEventListener('change', () => {
    if (getState().theme === 'system') emit('theme:changed', { theme: 'system', heat: getState().heat });
  });
}

export function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}
