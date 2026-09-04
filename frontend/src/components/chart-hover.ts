// 图表悬停 -> 单例浮层的内容映射（06 文档 §10）。
//
// 原先在 main.js 里监听冒泡上来的 `chart:hover` 自定义事件；React 化之后 `Chart` 直接
// 收 `onHover`，但**内容映射仍然只有一份**：命中区的 payload 是各图表自己的桶对象，
// 哪些字段该显示成哪一行由这里统一决定。散到各个视图去写，同一个字段就会有几种写法。
import { formatCount, formatDurationShort } from '../domain/format.ts';
import { hide, show } from './tooltip.tsx';
import type { TooltipRow } from './tooltip.tsx';

/** 命中区 payload 里可能出现的字段。各图表按需填一部分。 */
interface HoverPayload {
  label?: string;
  name?: string;
  bucket?: string;
  seconds?: number;
  total?: number;
  presses?: number;
  kpm?: number;
  value?: number;
  percent?: number;
  gap?: boolean;
  parts?: readonly { category: string; name?: string; seconds: number }[];
}

export function showChartTooltip(payload: unknown, x: number, y: number): void {
  if (!payload) return;
  const data = payload as HoverPayload;
  const rows: TooltipRow[] = [];
  if (data.seconds !== undefined) rows.push(['时长', formatDurationShort(data.seconds)]);
  if (data.total !== undefined) rows.push(['时长', formatDurationShort(data.total)]);
  if (data.presses !== undefined) rows.push(['按键', formatCount(data.presses)]);
  if (data.kpm !== undefined) rows.push(['输入强度', `${(Number(data.kpm) || 0).toFixed(1)} KPM`]);
  if (data.value !== undefined && data.percent !== undefined) {
    rows.push(['时长', formatDurationShort(data.value)]);
    rows.push(['占比', `${(data.percent || 0).toFixed(1)}%`]);
  }
  // 堆叠柱：段的高度只能看出相对大小，具体是哪一类多少必须能读到（14 文档 §4.3
  // 的"一个悬停浮层同时报两个值"推到堆叠这一层）。名字由数据带来，前端不查表。
  for (const part of data.parts || []) {
    if (!(Number(part.seconds) > 0)) continue;
    rows.push([part.name || part.category, formatDurationShort(part.seconds)]);
  }
  show({
    title: data.label || data.name || data.bucket || '',
    rows,
    // 缺口必须在 tooltip 里说明原因，光有斜纹用户不知道那是什么（06 文档 §4.2）。
    note: data.gap ? '该时段没有采集记录（不是 0）' : '',
    x,
    y,
  });
}

export function hideChartTooltip(): void {
  hide();
}
