// 应用范围选择器（06 文档 §7 改进 3）。
//
// "全部应用 / 某个应用"是同一张热力图的两种范围，不是两个功能。原 KeyTrace 把它放在
// 页面最下方一个独立面板里，还需要另外连上 TimeLens——合并后这只是一个下拉框。
import { h } from '../core/dom.js';
import { getState, setState } from '../core/store.js';

export function appPicker({ onChange } = {}) {
  const select = h('select', { class: 'control', attrs: { 'aria-label': '应用范围' } });
  select.addEventListener('change', () => {
    const id = Number.parseInt(select.value, 10);
    const next = Number.isInteger(id) && id > 0 ? id : null;
    setState('scopeAppId', next);
    if (onChange) onChange(next);
  });
  const root = h('label', { class: 'row' }, h('span', { class: 'muted text-sm', text: '范围' }), select);

  return {
    root,
    /** apps: [{app_id, display_name}]，一般取当周期内有数据的那些。 */
    update(apps) {
      const current = getState().scopeAppId;
      const options = [h('option', { value: '', text: '全部应用' })];
      for (const app of apps || []) {
        options.push(
          h('option', {
            value: String(app.app_id),
            text: app.display_name || `应用 ${app.app_id}`,
          }),
        );
      }
      select.replaceChildren(...options);
      select.value = current ? String(current) : '';
      // 选中的应用在新周期里没有数据：如实回落到全部，而不是显示一个空的过滤。
      if (current && select.value !== String(current)) {
        setState('scopeAppId', null);
        select.value = '';
      }
    },
  };
}
