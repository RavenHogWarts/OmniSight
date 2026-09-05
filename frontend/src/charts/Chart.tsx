// Canvas 图表的 React 外壳（15 文档 方案 A 批 4）。
//
// 原先是 `charts/canvas.js` 里的 `Chart` 类。拆开的界线：**几何与取色留在 canvas.ts，
// DOM 与生命周期归这里**。绘制函数一行没改，因此 14 文档 §5.1 那套记号规格不必重新
// 验收——画的是同一份代码（用户选的"先包 React，再换 ECharts"，这一步只换外壳）。
//
// 三件 React 里必须显式处理、而类版本里是构造函数副作用的事：
//   1. **ResizeObserver**：容器尺寸变了要重绘（现状是固定 width="720"，窗口一窄就压扁）。
//   2. **主题订阅**：CSS 变量变了 canvas 不会自己跟着变（06 文档 §11 第 2 点）。
//   3. **命中区**：canvas 没有 DOM 节点，悬停要自己算。命中区存在 ref 里而不是 state
//      ——它每帧重算，进 state 会引发一次无意义的重渲染。
//   4. **悬停重绘**：准线（14 文档 §4.3）画在 canvas 上，所以指针跨过一个桶时得重画一
//      次。走的仍然是 ref + 直接调 `render()`，不进 state——进 state 会让整棵子树跟着
//      指针重渲染，而变的只有 canvas 里的一条线。
import { useCallback, useEffect, useRef } from 'react';
import { on as busOn } from '../core/bus.ts';
import { palette, setupCanvas } from './canvas.ts';
import type { ChartDescription, DrawBox, DrawFn, HitArea } from './canvas.ts';

export interface ChartProps<T> {
  /** 画什么。`null` / `undefined` 时不画（视图那边通常已经显示骨架屏了）。 */
  data: T | null | undefined;
  draw: DrawFn<T>;
  /** sr-only 表格的内容。省略则不生成表格。 */
  describe?: (data: T) => ChartDescription | null;
  height?: number;
  /** canvas 的 aria-label。`describe` 给了 summary 时用 summary 覆盖它。 */
  label?: string;
  onSelect?: ((payload: unknown) => void) | null;
  /** 悬停：命中区的 payload + 屏幕坐标。视图把它接给单例 tooltip。 */
  onHover?: ((payload: unknown, x: number, y: number) => void) | null;
  onLeave?: (() => void) | null;
  className?: string;
}

export function Chart<T>({
  data,
  draw,
  describe,
  height = 150,
  label = '图表',
  onSelect = null,
  onHover = null,
  onLeave = null,
  className,
}: ChartProps<T>) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const hitsRef = useRef<HitArea[]>([]);
  const hoveredRef = useRef(-1);
  // 绘制函数与数据放进 ref：重绘发生在 ResizeObserver / 总线回调里，那些闭包不该
  // 因为 props 变化而重建（重建就要重新 observe，于是每次渲染都多一次绘制）。
  const latest = useRef({ data, draw });
  latest.current = { data, draw };

  const render = useCallback(() => {
    const canvas = canvasRef.current;
    const { data: current, draw: drawNow } = latest.current;
    if (!canvas || current === null || current === undefined) return;
    const box: DrawBox = { ...setupCanvas(canvas), hits: [], hover: hoveredRef.current };
    try {
      drawNow(box.ctx, box, current, palette());
    } catch (error) {
      console.error('图表绘制失败', error);
    }
    hitsRef.current = box.hits;
  }, []);

  // 数据或绘制函数变了就重画。**同步在提交后画**（useEffect 而不是 useMemo）：
  // canvas 的尺寸要等布局完成才读得到。
  useEffect(render, [render, data, draw]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const observer = new ResizeObserver(render);
    observer.observe(canvas);
    const offTheme = busOn('theme:changed', render);
    return () => {
      observer.disconnect();
      offTheme();
    };
  }, [render]);

  /** 命中区下标，没命中则 -1。返回下标而不是对象：`box.hover` 要的就是下标。 */
  const hitIndexAt = (event: { clientX: number; clientY: number }): number => {
    const canvas = canvasRef.current;
    if (!canvas) return -1;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    return hitsRef.current.findIndex(
      (hit) => x >= hit.x && x <= hit.x + hit.w && y >= hit.y && y <= hit.y + hit.h,
    );
  };

  /** 悬停的桶变了才重画。同一个桶里移动时准线没动，重画一次是纯白干。 */
  const setHovered = (index: number): void => {
    if (index === hoveredRef.current) return;
    hoveredRef.current = index;
    render();
  };

  const handleMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const index = hitIndexAt(event);
    if (index >= 0) {
      setHovered(index);
      // 浮层跟着指针走，所以这一行每次移动都要调，不能并进 setHovered 的判断里。
      onHover?.(hitsRef.current[index].payload, event.clientX, event.clientY);
      return;
    }
    if (hoveredRef.current >= 0) {
      setHovered(-1);
      onLeave?.();
    }
  };

  const handleLeave = () => {
    setHovered(-1);
    onLeave?.();
  };

  const spec = describe && data !== null && data !== undefined ? describe(data) : null;

  return (
    <div className={className}>
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={spec?.summary || label}
        style={{ height: `${height}px`, cursor: onSelect ? 'pointer' : undefined }}
        onPointerMove={handleMove}
        onPointerLeave={handleLeave}
        onClick={(event) => {
          if (!onSelect) return;
          const index = hitIndexAt(event);
          if (index >= 0) onSelect(hitsRef.current[index].payload);
        }}
      />
      {/* 详细数据在紧邻的 sr-only 表格里，canvas 的 aria-label 只给摘要（06 文档 §11）。 */}
      {spec ? (
        <div className="sr-only">
          <table>
            <caption>{spec.caption || ''}</caption>
            <thead>
              <tr>
                {spec.columns.map((name) => (
                  <th key={name}>{name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {spec.rows.map((row, index) => (
                <tr key={index}>
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex}>{String(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
