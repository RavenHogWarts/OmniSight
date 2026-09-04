// 图标（14 文档 §3.5、15 文档 方案 A 批 5）。
//
// **从内联精灵表换成 lucide-react。** 换掉的是"生成 + 提交一份 <symbol> 片段"那套
// 机制（tools/icons.py），换来的是三件事：加图标只写一行 import、名字由类型系统检查
// （拼错 `Setttings` 编译期就红，而 `<use href="#i-typo">` 在浏览器里是静默空白）、
// 以及 tree-shaking——2057 个图标里只有用到的那十几个进产物。
//
// 规格一行没变，仍然是 14 文档 §3.5 定的那套：24×24 视框、`currentColor`、1.5 笔重、
// 圆头端点。**笔重与尺寸仍然由 base.css 的 `.icon` 控制**，所以这里刻意不传
// `strokeWidth`/`size` 给 lucide——它默认给 2 与 24，属性会盖过外部样式表。
//
// 默认 aria-hidden：图标几乎总是配着文字出现；只有纯图标按钮才需要名字，那时名字
// 应该写在按钮的 aria-label 上，不是写在图标里。
import {
  ChartColumn,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Contrast,
  Download,
  EllipsisVertical,
  House,
  Info,
  Keyboard,
  LayoutGrid,
  Pause,
  Search,
  Settings,
  TriangleAlert,
  X,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

/**
 * 我们的 id → lucide 组件。
 *
 * **保留这张映射表而不是直接用 lucide 的名字**：`theme` 用 `Contrast`（圆 + 半填充）
 * 而不是 `SunMoon`，因为主题按钮是三态循环（跟随系统 / 浅 / 深），日月图标会暗示
 * 只有两态。这类"为什么是这个图标"的决定需要一个落脚处，而调用点写 `<Icon name="theme" />`
 * 读起来也比 `<Contrast />` 更贴近它在界面上的角色。
 */
const ICONS = {
  gear: Settings,
  theme: Contrast,
  left: ChevronLeft,
  right: ChevronRight,
  // 弹层触发器的下箭头（应用范围选择器，14 文档 §4.6）。用 chevron 而不是 caret：
  // 与左右两个翻页箭头同族，三个箭头因此是同一套笔画。
  down: ChevronDown,
  info: Info,
  keyboard: Keyboard,
  apps: LayoutGrid,
  insights: ChartColumn,
  overview: House,
  download: Download,
  pause: Pause,
  more: EllipsisVertical,
  search: Search,
  close: X,
  warning: TriangleAlert,
} satisfies Record<string, LucideIcon>;

export type IconName = keyof typeof ICONS;

export const ICON_NAMES = Object.keys(ICONS) as IconName[];

export interface IconProps {
  name: IconName;
  /** 覆盖 `.icon` 的 16px。只在需要更大的装饰性图标时传（空态的图标是 28px）。 */
  size?: number;
  className?: string;
  /** 极少数场合图标是唯一内容且没有 aria-label 的按钮包着它，此时给它一个名字。 */
  title?: string;
}

export function Icon({ name, size, className = 'icon', title }: IconProps) {
  const Glyph = ICONS[name];
  return (
    <Glyph
      className={className}
      aria-hidden={title ? undefined : true}
      aria-label={title}
      role={title ? 'img' : undefined}
      focusable="false"
      // lucide 会写 width/height/stroke-width/stroke/fill 四个**表现属性**（默认 24 与 2）。
      // 它们不需要在这里清掉：CSS 声明的优先级高于 SVG 表现属性，因此 base.css 的
      // `.icon { width: 16px; stroke-width: 1.5; stroke: currentColor; fill: none }` 照样生效
      // ——14 文档 §3.5 那套规格仍然只有一处真源。
      //
      // 只有显式传 size 时才覆盖，且走行内 style（它同样压得住表现属性）。
      style={size ? { width: size, height: size } : undefined}
    />
  );
}
