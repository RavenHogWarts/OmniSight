// 服务端下发布局的**遍历工具**。这里没有一个坐标（07 文档 §6.4、06 文档 §7.1）。
//
// 旧 KeyTrace 把 104 个键的 DOM 硬编码在 HTML 里，键定义还与 Python 的 keys.py 重复
// 了一份。改成数据驱动之后：加/改键位只改后端；ISO 105 与 ANSI 104 只是同一份布局
// 数据的两个取值；"两份清单比对"这种脆弱机制不再需要——因为只有一份数据。
//
// **React 化之后这里只剩纯函数**：DOM 那一半搬进了 components/KeyboardView.tsx
// （React 直接按 rows 渲染）。留在这里的两个函数服务方向键导航，且它们是
// tests/frontend/keyboard-render.test.ts 唯一需要的东西——那条用例吃的是**后端现场
// 导出**的布局数据，因此它验证的是真实契约而不是手工快照。
import type { LayoutKey, LayoutResponse } from '../types/api.d.ts';

/** 已知的特殊形状。只有一个，且这就是重点（L 形 ISO 回车无法用宽度倍数表达）。 */
export const KNOWN_SHAPES = new Set(['iso_enter']);
/** 占位槽的 id。它不是键，只占宽度。 */
export const GAP = 'gap';

export function isGap(slot: LayoutKey | null | undefined): boolean {
  return !slot || slot.id === GAP;
}

/**
 * 布局里所有真实键的 id（不含 gap），顺序即视觉顺序——方向键导航用它。
 */
export function keyOrder(layout: LayoutResponse | null | undefined): string[] {
  const ids: string[] = [];
  for (const row of layout?.rows || []) {
    for (const slot of row) {
      if (!isGap(slot)) ids.push(slot.id);
    }
  }
  return ids;
}

/**
 * 按行分组的 id，供上下方向键在行间移动。
 */
export function keyRows(layout: LayoutResponse | null | undefined): string[][] {
  return (layout?.rows || []).map((row) => row.filter((slot) => !isGap(slot)).map((slot) => slot.id));
}
