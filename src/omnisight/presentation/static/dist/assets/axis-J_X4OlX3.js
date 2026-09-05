import { H as on, K as require_react, W as require_jsx_runtime, f as hide, h as formatCount, p as show, v as formatDurationShort } from "./degraded-qMnijys5.js";
//#region frontend/src/charts/canvas.ts
var import_react = require_react();
/** 从 CSS 变量取色。主题切换后重新取一次，JS 因此不需要知道当前是深色还是浅色。 */
function cssColor(name, fallback = "#888") {
	return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}
/**
* canvas 的字体串。轴标签必须与全站同源：现状写死 `10px sans-serif`，字号低于 11px
* 下限、字族在 Windows 上落到 Arial，与 Segoe 不同源（14 文档 §2.7）。
*
* `--font-small` 是 ≤12px 的光学尺寸档（14 文档 §3.3），轴标签正属于这一档。
*/
function cssFont(size = 11, weight = 400) {
	return `${weight} ${size}px ${cssColor("--font-small", "system-ui, sans-serif")}`;
}
/**
* 只有数据端有圆角的柱子。基线端保持方角——柱子是从基线"长"出来的，
* 两端都圆会让它看起来是漂浮的胶囊（14 文档 §5.1）。
*/
function bar(ctx, x, y, w, h, radius = 4) {
	if (h <= 0) return;
	const r = Math.min(radius, w / 2, h);
	ctx.beginPath();
	ctx.moveTo(x, y + h);
	ctx.lineTo(x, y + r);
	ctx.quadraticCurveTo(x, y, x + r, y);
	ctx.lineTo(x + w - r, y);
	ctx.quadraticCurveTo(x + w, y, x + w, y + r);
	ctx.lineTo(x + w, y + h);
	ctx.closePath();
	ctx.fill();
}
function setupCanvas(canvas) {
	const dpr = window.devicePixelRatio || 1;
	const rect = canvas.getBoundingClientRect();
	const width = Math.max(1, Math.round(rect.width));
	const height = Math.max(1, Math.round(rect.height));
	canvas.width = Math.round(width * dpr);
	canvas.height = Math.round(height * dpr);
	const ctx = canvas.getContext("2d");
	ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
	ctx.clearRect(0, 0, width, height);
	return {
		ctx,
		width,
		height
	};
}
/** 斜纹填充：能力缺失区间的唯一视觉编码（06 文档 §4.2 规则 1）。 */
function hatchPattern(ctx, color) {
	const tile = document.createElement("canvas");
	tile.width = 6;
	tile.height = 6;
	const tileCtx = tile.getContext("2d");
	tileCtx.strokeStyle = color;
	tileCtx.lineWidth = 1.2;
	tileCtx.beginPath();
	tileCtx.moveTo(-1, 7);
	tileCtx.lineTo(7, -1);
	tileCtx.moveTo(2, 8);
	tileCtx.lineTo(8, 2);
	tileCtx.stroke();
	return ctx.createPattern(tile, "repeat");
}
/** 一次取齐所有会用到的颜色，避免在绘制循环里反复读 computed style。 */
function palette() {
	const color = cssColor;
	return {
		accent: color("--accent", "#2f7cf6"),
		accentSubtle: color("--accent-subtle", "#e8f1fe"),
		text: color("--text-primary", "#1d1d1f"),
		muted: color("--text-secondary", "#5f5f66"),
		faint: color("--text-tertiary", "#6b6b73"),
		grid: color("--border-subtle", "rgba(0,0,0,.1)"),
		strong: color("--border-strong", "rgba(0,0,0,.28)"),
		surface: color("--surface-card", "#fff"),
		sunken: color("--surface-sunken", "#eee"),
		time: color("--data-time", "#2f7cf6"),
		keys: color("--data-keys", "#7e438c"),
		heat: [
			color("--heat-0", "#eeeef1"),
			color("--heat-1", "#cf8fde"),
			color("--heat-2", "#b375c2"),
			color("--heat-3", "#995ba6"),
			color("--heat-4", "#7e438c"),
			color("--heat-5", "#652a72")
		],
		categories: {
			development: color("--cat-development", "#be2038"),
			productivity: color("--cat-productivity", "#2f7cf6"),
			communication: color("--cat-communication", "#16a394"),
			entertainment: color("--cat-entertainment", "#d37819"),
			system: color("--cat-system", "#57575c"),
			uncategorized: color("--cat-uncategorized", "#919197")
		}
	};
}
/**
* 轴刻度：只取 3 到 5 个整齐的值，不做通用的 nice-number 算法。
*/
function niceMax(value) {
	if (value <= 0) return 1;
	const magnitude = 10 ** Math.floor(Math.log10(value));
	const scaled = value / magnitude;
	return (scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10) * magnitude;
}
//#endregion
//#region frontend/src/charts/Chart.tsx
var import_jsx_runtime = require_jsx_runtime();
function Chart({ data, draw, describe, height = 150, label = "图表", onSelect = null, onHover = null, onLeave = null, className }) {
	const canvasRef = (0, import_react.useRef)(null);
	const hitsRef = (0, import_react.useRef)([]);
	const hoveredRef = (0, import_react.useRef)(-1);
	const latest = (0, import_react.useRef)({
		data,
		draw
	});
	latest.current = {
		data,
		draw
	};
	const render = (0, import_react.useCallback)(() => {
		const canvas = canvasRef.current;
		const { data: current, draw: drawNow } = latest.current;
		if (!canvas || current === null || current === void 0) return;
		const box = {
			...setupCanvas(canvas),
			hits: [],
			hover: hoveredRef.current
		};
		try {
			drawNow(box.ctx, box, current, palette());
		} catch (error) {
			console.error("图表绘制失败", error);
		}
		hitsRef.current = box.hits;
	}, []);
	(0, import_react.useEffect)(render, [
		render,
		data,
		draw
	]);
	(0, import_react.useEffect)(() => {
		const canvas = canvasRef.current;
		if (!canvas) return;
		const observer = new ResizeObserver(render);
		observer.observe(canvas);
		const offTheme = on("theme:changed", render);
		return () => {
			observer.disconnect();
			offTheme();
		};
	}, [render]);
	/** 命中区下标，没命中则 -1。返回下标而不是对象：`box.hover` 要的就是下标。 */
	const hitIndexAt = (event) => {
		const canvas = canvasRef.current;
		if (!canvas) return -1;
		const rect = canvas.getBoundingClientRect();
		const x = event.clientX - rect.left;
		const y = event.clientY - rect.top;
		return hitsRef.current.findIndex((hit) => x >= hit.x && x <= hit.x + hit.w && y >= hit.y && y <= hit.y + hit.h);
	};
	/** 悬停的桶变了才重画。同一个桶里移动时准线没动，重画一次是纯白干。 */
	const setHovered = (index) => {
		if (index === hoveredRef.current) return;
		hoveredRef.current = index;
		render();
	};
	const handleMove = (event) => {
		const index = hitIndexAt(event);
		if (index >= 0) {
			setHovered(index);
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
	const spec = describe && data !== null && data !== void 0 ? describe(data) : null;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className,
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("canvas", {
			ref: canvasRef,
			role: "img",
			"aria-label": spec?.summary || label,
			style: {
				height: `${height}px`,
				cursor: onSelect ? "pointer" : void 0
			},
			onPointerMove: handleMove,
			onPointerLeave: handleLeave,
			onClick: (event) => {
				if (!onSelect) return;
				const index = hitIndexAt(event);
				if (index >= 0) onSelect(hitsRef.current[index].payload);
			}
		}), spec ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "sr-only",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", { children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("caption", { children: spec.caption || "" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tr", { children: spec.columns.map((name) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { children: name }, name)) }) }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: spec.rows.map((row, index) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tr", { children: row.map((cell, cellIndex) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { children: String(cell) }, cellIndex)) }, index)) })
			] })
		}) : null]
	});
}
//#endregion
//#region frontend/src/components/chart-hover.ts
function showChartTooltip(payload, x, y) {
	if (!payload) return;
	const data = payload;
	const rows = [];
	if (data.seconds !== void 0) rows.push(["时长", formatDurationShort(data.seconds)]);
	if (data.total !== void 0) rows.push(["时长", formatDurationShort(data.total)]);
	if (data.presses !== void 0) rows.push(["按键", formatCount(data.presses)]);
	if (data.kpm !== void 0) rows.push(["输入强度", `${(Number(data.kpm) || 0).toFixed(1)} KPM`]);
	if (data.reading) rows.push([data.reading.label, data.reading.text]);
	if (data.value !== void 0 && data.percent !== void 0) {
		rows.push(["时长", formatDurationShort(data.value)]);
		rows.push(["占比", `${(data.percent || 0).toFixed(1)}%`]);
	}
	for (const part of data.parts || []) {
		if (!(Number(part.seconds) > 0)) continue;
		rows.push([part.name || part.category, formatDurationShort(part.seconds)]);
	}
	show({
		title: data.label || data.name || data.bucket || "",
		rows,
		note: data.gap ? "该时段没有采集记录（不是 0）" : "",
		x,
		y
	});
}
function hideChartTooltip() {
	hide();
}
//#endregion
//#region frontend/src/charts/axis.ts
/** 相邻标签之间至少留这么多空白。低于 6px 时两个日期读起来像一个长词。 */
var LABEL_GAP = 10;
/**
* 该画哪些标签、画在哪。
*
* `measure` 由调用方注入（真实实现是 `ctx.measureText(t).width`），于是这个函数是纯的
* ——`tests/frontend/axis.test.ts` 用一个"每字符 7px"的假尺子就能钉住抽稀与保号规则，
* 不需要 canvas。
*/
function timeAxisTicks(labels, plot, measure) {
	const count = labels.length;
	if (!count || plot.w <= 0) return [];
	const widths = labels.map((text) => Math.max(0, measure(text)));
	const minGap = Math.max(1, Math.max(...widths) + LABEL_GAP);
	const slot = plot.w / count;
	const capacity = Math.max(2, Math.floor(plot.w / minGap));
	const stride = Math.max(1, Math.ceil(count / capacity));
	const centre = (index) => plot.x + slot * (index + .5);
	const chosen = [];
	for (let index = 0; index < count; index += stride) chosen.push(index);
	const last = count - 1;
	if (chosen[chosen.length - 1] !== last) {
		const previous = chosen[chosen.length - 1];
		if (centre(last) - centre(previous) < minGap) chosen.pop();
		chosen.push(last);
	}
	const right = plot.x + plot.w;
	return chosen.map((index) => {
		const half = widths[index] / 2;
		const middle = centre(index);
		if (middle - half < plot.x) return {
			index,
			text: labels[index],
			x: plot.x,
			align: "left"
		};
		if (middle + half > right) return {
			index,
			text: labels[index],
			x: right,
			align: "right"
		};
		return {
			index,
			text: labels[index],
			x: middle,
			align: "center"
		};
	});
}
/**
* 画一根时间轴的标签。`baseline` 是文字顶沿的 y（三个调用点都用 `textBaseline: 'top'`）。
*
* **字体必须在调用前设好**：抽稀要量文字宽度，而宽度取决于当前的 `ctx.font`。三个调用点
* 本来就在画 y 轴刻度时设过 `cssFont(11)`，所以这里不再设一次——重复设置会掩盖"某处忘了
* 设"这件事（`stacked-bar` 就曾经漏成 `10px sans-serif`）。
*/
function drawTimeAxis(ctx, labels, plot, baseline, color) {
	const ticks = timeAxisTicks(labels, plot, (text) => ctx.measureText(text).width);
	if (!ticks.length) return;
	ctx.fillStyle = color;
	ctx.textBaseline = "top";
	for (const tick of ticks) {
		ctx.textAlign = tick.align;
		ctx.fillText(tick.text, tick.x, baseline);
	}
}
//#endregion
export { bar as a, niceMax as c, Chart as i, hideChartTooltip as n, cssFont as o, showChartTooltip as r, hatchPattern as s, drawTimeAxis as t };
