// 前端构建（15 文档 §3.1、方案 A 批 1）。
//
// **为什么是"后端集成"模式而不是 Vite 的默认 HTML 入口**：页面外壳是 Jinja 模板
// （`templates/dashboard.html`），它要注入令牌（08 文档 §3.2b）；Vite 若自己产出 HTML，
// 就会有两份外壳。所以这里只让它产出 JS 资产 + `manifest.json`，由 Flask 读清单拿到
// 入口文件名（`presentation/web.py:read_bundle`）。Django/Rails/Laravel 的 Vite 集成
// 都是这个形状。
//
// **产物提交进版本库**：`pip install` 路径上没有 Node（15 文档 §3.2），wheel 必须自带
// 打包好的前端。`tools/check_bundle.py --check` 负责发现"改了源码忘了重新构建"。
//
// **没有 HMR**：CSP 是 `script-src 'self'`（08 文档 §3），HMR 要连 dev server 的
// websocket 并注入内联脚本，两条都撞。开发期用 `pnpm dev`（= `vite build --watch`），
// 改完刷新页面。保留 CSP 的单一真相比省一次刷新重要（15 文档 §3.3）。
import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const here = (path: string) => fileURLToPath(new URL(path, import.meta.url));

export default defineConfig({
  root: here('frontend'),
  // 浏览器按这个前缀请求分包与动态导入的视图模块；Flask 用 /static 托管整个目录。
  base: '/static/dist/',
  plugins: [react()],
  resolve: {
    // **迁移期必须显式列出**：`frontend/src` 里 .js 与 .ts 并存（15 文档 §8 的分批
    // 原则），而相对导入一律写成无后缀——只有这样，把某个模块从 .js 改名成 .ts 时
    // 才不必同时改所有导入方。Vite 8 默认不为 .js 导入方补 .ts 后缀，所以写在这里。
    extensions: ['.ts', '.tsx', '.js', '.jsx', '.mjs', '.json'],
  },
  build: {
    outDir: here('src/omnisight/presentation/static/dist'),
    emptyOutDir: true,
    // 清单放在 dist 根而不是默认的 dist/.vite/：setuptools 的 `**/*` 对点开头的目录
    // 不保证展开，而这份清单必须进 wheel——少了它页面就只有"产物缺失"那张卡。
    manifest: 'manifest.json',
    // 浏览器基线是 Safari 15.4（07 文档 §2：pywebview 下的 WebKitGTK 最旧）。
    target: ['es2022', 'safari15.4'],
    // 本机加载，压缩省下的字节没有意义；可读的产物在排查"页面白屏"时值钱得多。
    minify: false,
    cssMinify: false,
    // **一份 CSS，不按视图分包，也不按页面分包。** 默认的 true 会把 keyboard/insights 的
    // 样式挂到各自的动态 chunk 上，于是首次进某个视图时样式比 DOM 晚到一帧——本机加载省下
    // 的那几 KB 换来一次可见的重排，不值。三个入口因此共用产物里的同一份样式表，`read_bundle`
    // 那半条"扫所有 .css 记录"的兜底路径也仍然成立（入口记录上没有 `css` 字段）。
    cssCodeSplit: false,
    // **不产 sourcemap**：产物提交进版本库并随 EXE 分发，而 map 比 JS 本身还大
    // （1.28 MB vs 0.71 MB）。既然没压缩，产物本身就是可读的；而 map 指回的
    // frontend/src/*.tsx 只有开发者手上有——他随时能自己开着 map 重新构建。
    sourcemap: false,
    rollupOptions: {
      // **三个页面各一个入口**（18 文档 批 1）：仪表盘、设置、关于。设置与关于是真的页面
      // （`/settings`、`/about`）而不是仪表盘里的一个 hash 路由——理由见 pages/shell.tsx。
      //
      // 键名（main / settings / about）只影响产物文件名；后端按**清单里的源码路径**取入口
      // （`src/settings.tsx` 这样的键，见 `web.py:read_bundle`），因此改这里的键名不会让
      // 后端找不到它，而改文件路径会——那一处也有一条注释指着这里。
      input: {
        main: here('frontend/src/main.tsx'),
        settings: here('frontend/src/settings.tsx'),
        about: here('frontend/src/about.tsx'),
      },
    },
  },
});
