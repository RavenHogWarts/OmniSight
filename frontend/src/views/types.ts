// 视图模块的契约（07 文档 §5.2）。
//
// 三样东西，一样不多：**标题**（写进 document.title）、**需要哪些数据**、**怎么画**。
// `needs` 是函数而不是常量：需求里有视图内部状态（应用视图的"显示已排除"、键盘视图的
// 选中键位），那些不在 store 里也不该在 store 里（07 文档 §4.3）。
//
// React 化之后契约反而更短了：原先还有 `render()` / `destroy()` / `filters()` 三个方法，
// 现在渲染与卸载由 React 负责。视图级控件各自就位（17 文档 §4.1）：键盘的指标分段器
// portal 到居中的指标带（`METRIC_SLOT_ID`），其余筛选控件长在它们作用的那张卡的卡头上。
import type { ComponentType } from 'react';
import type { State } from '../core/store.ts';
import type { DataRequest } from '../types/api.d.ts';

export interface ViewModule {
  title: string;
  needs: (state: State) => DataRequest[];
  View: ComponentType;
}
