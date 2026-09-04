import { T as formatCount, Y as require_react, i as show, k as formatDurationShort, q as require_jsx_runtime, r as hide, z as on } from "./main-DA_wrxiB.js";
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
	const hoveredRef = (0, import_react.useRef)(null);
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
			hits: []
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
	const hitAt = (event) => {
		const canvas = canvasRef.current;
		if (!canvas) return null;
		const rect = canvas.getBoundingClientRect();
		const x = event.clientX - rect.left;
		const y = event.clientY - rect.top;
		for (const hit of hitsRef.current) if (x >= hit.x && x <= hit.x + hit.w && y >= hit.y && y <= hit.y + hit.h) return hit;
		return null;
	};
	const handleMove = (event) => {
		const hit = hitAt(event);
		if (hit) {
			hoveredRef.current = hit;
			onHover?.(hit.payload, event.clientX, event.clientY);
			return;
		}
		if (hoveredRef.current) {
			hoveredRef.current = null;
			onLeave?.();
		}
	};
	const handleLeave = () => {
		hoveredRef.current = null;
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
				const hit = hitAt(event);
				if (hit) onSelect(hit.payload);
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
//#region frontend/src/charts/panel-pair.ts
var PAD = {
	top: 10,
	right: 8,
	bottom: 18,
	left: 52
};
/** 两个面板之间的留白。共享 x 轴，所以中间只需要一条呼吸缝。 */
var SPLIT = 14;
var drawPanelPair = (ctx, box, data, palette) => {
	const buckets = data.buckets || [];
	if (!buckets.length) return;
	const mode = data.mode || "both";
	const plotX = PAD.left;
	const plotW = Math.max(1, box.width - PAD.left - PAD.right);
	const totalH = Math.max(1, box.height - PAD.top - PAD.bottom);
	if (mode === "kpm") {
		drawKpm(ctx, box, buckets, palette, {
			x: plotX,
			y: PAD.top,
			w: plotW,
			h: totalH
		});
		drawXAxis(ctx, buckets, palette, plotX, plotW, PAD.top + totalH);
		return;
	}
	const both = mode === "both";
	const topH = both ? Math.max(1, (totalH - SPLIT) * .56) : totalH;
	const bottomH = both ? Math.max(1, totalH - SPLIT - topH) : totalH;
	const topPanel = {
		x: plotX,
		y: PAD.top,
		w: plotW,
		h: topH
	};
	const bottomPanel = {
		x: plotX,
		y: PAD.top + topH + SPLIT,
		w: plotW,
		h: bottomH
	};
	const slot = plotW / buckets.length;
	const width = Math.max(1, Math.min(slot - 2, 24));
	const hatch = hatchPattern(ctx, palette.strong);
	if (both || mode === "seconds") drawPanel(ctx, buckets, palette, topPanel, {
		value: (item) => item.seconds || 0,
		format: formatDurationShort,
		color: palette.time,
		parts: true,
		slot,
		width,
		hatch
	});
	if (both || mode === "presses") drawPanel(ctx, buckets, palette, both ? bottomPanel : topPanel, {
		value: (item) => item.presses || 0,
		format: formatCount,
		color: palette.keys,
		parts: false,
		slot,
		width,
		hatch
	});
	buckets.forEach((item, index) => {
		box.hits.push({
			x: plotX + slot * index,
			y: PAD.top,
			w: slot,
			h: totalH,
			payload: item
		});
	});
	drawXAxis(ctx, buckets, palette, plotX, plotW, PAD.top + totalH);
};
/** 一个面板：自己的 y 刻度 + 柱。刻度只取 0 / 半 / 满三档，避免与另一面板争视觉。 */
function drawPanel(ctx, buckets, palette, plot, spec) {
	const max = niceMax(Math.max(...buckets.map(spec.value)));
	ctx.strokeStyle = palette.grid;
	ctx.lineWidth = 1;
	ctx.fillStyle = palette.faint;
	ctx.font = cssFont(11);
	ctx.textAlign = "right";
	ctx.textBaseline = "middle";
	for (let step = 0; step <= 2; step += 1) {
		const y = plot.y + plot.h - plot.h * step / 2;
		ctx.beginPath();
		ctx.moveTo(plot.x, Math.round(y) + .5);
		ctx.lineTo(plot.x + plot.w, Math.round(y) + .5);
		ctx.stroke();
		ctx.fillText(spec.format(max * step / 2), plot.x - 6, y);
	}
	buckets.forEach((item, index) => {
		const x = plot.x + spec.slot * (index + .5) - spec.width / 2;
		if (item.gap) {
			if (spec.hatch) ctx.fillStyle = spec.hatch;
			ctx.fillRect(x, plot.y, spec.width, plot.h);
			return;
		}
		const value = spec.value(item);
		const barHeight = max ? value / max * plot.h : 0;
		if (barHeight <= 0) return;
		const parts = spec.parts ? item.parts || [] : [];
		if (parts.length) {
			let cursor = plot.y + plot.h;
			parts.forEach((part, partIndex) => {
				const partHeight = max ? (part.seconds || 0) / max * plot.h : 0;
				if (partHeight <= 0) return;
				ctx.fillStyle = palette.categories[part.category] || palette.categories.uncategorized;
				const isTop = partIndex === parts.length - 1;
				const gap = partIndex === 0 ? 0 : 2;
				if (isTop) bar(ctx, x, cursor - partHeight, spec.width, partHeight - gap);
				else ctx.fillRect(x, cursor - partHeight, spec.width, Math.max(0, partHeight - gap));
				cursor -= partHeight;
			});
			return;
		}
		ctx.fillStyle = spec.color;
		bar(ctx, x, plot.y + plot.h - barHeight, spec.width, barHeight);
	});
}
function kpmOf(item) {
	const minutes = (item.seconds || 0) / 60;
	return minutes > 0 ? (item.presses || 0) / minutes : 0;
}
/** 输入强度：一条 KPM 折线，一套刻度。 */
function drawKpm(ctx, box, buckets, palette, plot) {
	const kpm = buckets.map(kpmOf);
	const max = niceMax(Math.max(...kpm));
	ctx.strokeStyle = palette.grid;
	ctx.lineWidth = 1;
	ctx.fillStyle = palette.faint;
	ctx.font = cssFont(11);
	ctx.textAlign = "right";
	ctx.textBaseline = "middle";
	for (let step = 0; step <= 2; step += 1) {
		const y = plot.y + plot.h - plot.h * step / 2;
		ctx.beginPath();
		ctx.moveTo(plot.x, Math.round(y) + .5);
		ctx.lineTo(plot.x + plot.w, Math.round(y) + .5);
		ctx.stroke();
		ctx.fillText(formatCount(Math.round(max * step / 2)), plot.x - 6, y);
	}
	const slot = plot.w / buckets.length;
	ctx.strokeStyle = palette.keys;
	ctx.lineWidth = 2;
	ctx.lineJoin = "round";
	ctx.lineCap = "round";
	ctx.beginPath();
	let started = false;
	buckets.forEach((item, index) => {
		const centre = plot.x + slot * (index + .5);
		if (item.gap) {
			started = false;
			return;
		}
		const y = plot.y + plot.h - (max ? kpm[index] / max * plot.h : 0);
		if (!started) {
			ctx.moveTo(centre, y);
			started = true;
		} else ctx.lineTo(centre, y);
	});
	ctx.stroke();
	buckets.forEach((item, index) => {
		box.hits.push({
			x: plot.x + slot * index,
			y: plot.y,
			w: slot,
			h: plot.h,
			payload: {
				...item,
				kpm: kpm[index]
			}
		});
	});
}
function drawXAxis(ctx, buckets, palette, x, w, baseline) {
	ctx.fillStyle = palette.faint;
	ctx.font = cssFont(11);
	ctx.textAlign = "center";
	ctx.textBaseline = "top";
	const slot = w / buckets.length;
	const stride = Math.max(1, Math.ceil(buckets.length / Math.max(2, Math.floor(w / 48))));
	buckets.forEach((item, index) => {
		if (index % stride) return;
		ctx.fillText(String(item.label ?? ""), x + slot * (index + .5), baseline + 4);
	});
}
function describePanelPair(data) {
	const buckets = data?.buckets || [];
	if (!buckets.length) return null;
	const mode = data.mode || "both";
	if (mode === "kpm") return {
		caption: data.caption || "输入强度",
		summary: data.summary || `${buckets.length} 个时间桶的输入强度`,
		columns: ["时间", "KPM"],
		rows: buckets.map((item) => [String(item.label ?? item.bucket ?? ""), item.gap ? "无记录" : formatCount(Math.round(kpmOf(item)))])
	};
	const columns = ["时间"];
	if (mode !== "presses") columns.push("屏幕时间");
	if (mode !== "seconds") columns.push("按键");
	return {
		caption: data.caption || "活动带",
		summary: data.summary || `${buckets.length} 个时间桶的活动数据`,
		columns,
		rows: buckets.map((item) => {
			const row = [String(item.label ?? item.bucket ?? "")];
			if (mode !== "presses") row.push(item.gap ? "无记录" : formatDurationShort(item.seconds || 0));
			if (mode !== "seconds") row.push(item.gap ? "无记录" : formatCount(item.presses || 0));
			return row;
		})
	};
}
//#endregion
export { Chart as a, showChartTooltip as i, drawPanelPair as n, hatchPattern as o, hideChartTooltip as r, niceMax as s, describePanelPair as t };
