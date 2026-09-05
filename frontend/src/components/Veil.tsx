// 全屏加载遮罩（17 文档 §4.2）。前身在每次取数时把整页蒙一层半透明纱 + 5px 模糊，
// 转圈在正中。
//
// **只在"这一屏还什么都没有"时出现**，这是它与骨架屏的分工：
//
//   首次进入一个视图   纱（没有任何旧内容可保留，骨架屏此时只是一堆灰条）
//   之后的刷新         骨架屏 + 卡片顶沿进度条，旧数据留在原位（06 文档 §10.1 第二态）
//
// 判据因此是"有请求在飞 **且** 它还没有过任何数据"，而不是"有请求在飞"——后者会让每
// 一次 SSE 触发的重取都闪一层纱，那正是前身最吵的地方（它每秒 `loadData()` 一次）。
import { useSlice } from '../core/useStore.ts';
import type { DataMap } from '../types/api.d.ts';

export function Veil() {
  const loading = useSlice('loading');
  const data = useSlice('data');
  const keys = Object.keys(loading) as (keyof DataMap)[];
  const cold = keys.some((key) => loading[key] && data[key] === undefined);

  return (
    <div className="veil" data-visible={cold ? 'true' : undefined} aria-hidden="true">
      <div className="veil__spinner" />
    </div>
  );
}
