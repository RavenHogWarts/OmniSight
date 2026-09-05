import { C as useSlice, E as setState, S as useResource, W as require_jsx_runtime, b as formatPercent, h as formatCount, m as formatClock, n as capabilityOf, r as noticeFor, v as formatDurationShort, w as getState } from "./degraded-qMnijys5.js";
import { o as gapSet, r as Updated, s as periodParams, t as fetchInto } from "./main-BgBdqxK5.js";
import { n as Section, t as Card } from "./Card-CwX6lTXj.js";
import { a as SkeletonRows, n as EmptyState, r as ErrorState, t as CapabilityNotice } from "./states-BInd1nRj.js";
import { a as bar, c as niceMax, i as Chart, n as hideChartTooltip, o as cssFont, r as showChartTooltip, s as hatchPattern, t as drawTimeAxis } from "./axis-J_X4OlX3.js";
//#region frontend/src/charts/panel-pair.ts
var PAD$1 = {
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
	const plotX = PAD$1.left;
	const plotW = Math.max(1, box.width - PAD$1.left - PAD$1.right);
	const totalH = Math.max(1, box.height - PAD$1.top - PAD$1.bottom);
	const slot = plotW / buckets.length;
	const hover = box.hover >= 0 && box.hover < buckets.length ? box.hover : -1;
	if (mode === "kpm") {
		const plot = {
			x: plotX,
			y: PAD$1.top,
			w: plotW,
			h: totalH
		};
		if (hover >= 0) drawCrosshair(ctx, palette, plot, slot, hover);
		drawKpm(ctx, box, buckets, palette, plot, slot, hover);
		drawXAxis(ctx, buckets, palette, plotX, plotW, PAD$1.top + totalH);
		return;
	}
	const both = mode === "both";
	const topH = both ? Math.max(1, (totalH - SPLIT) * .56) : totalH;
	const bottomH = both ? Math.max(1, totalH - SPLIT - topH) : totalH;
	const topPanel = {
		x: plotX,
		y: PAD$1.top,
		w: plotW,
		h: topH
	};
	const bottomPanel = {
		x: plotX,
		y: PAD$1.top + topH + SPLIT,
		w: plotW,
		h: bottomH
	};
	const width = Math.max(1, Math.min(slot - 2, 24));
	const hatch = hatchPattern(ctx, palette.strong);
	if (hover >= 0) drawCrosshair(ctx, palette, {
		x: plotX,
		y: PAD$1.top,
		w: plotW,
		h: totalH
	}, slot, hover);
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
			y: PAD$1.top,
			w: slot,
			h: totalH,
			payload: item
		});
	});
	drawXAxis(ctx, buckets, palette, plotX, plotW, PAD$1.top + totalH);
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
function drawKpm(ctx, box, buckets, palette, plot, slot, hover) {
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
	if (hover >= 0 && !buckets[hover].gap) {
		const cx = plot.x + slot * (hover + .5);
		const cy = plot.y + plot.h - (max ? kpm[hover] / max * plot.h : 0);
		ctx.beginPath();
		ctx.arc(cx, cy, 4.5, 0, Math.PI * 2);
		ctx.fillStyle = palette.surface;
		ctx.fill();
		ctx.beginPath();
		ctx.arc(cx, cy, 2.5, 0, Math.PI * 2);
		ctx.fillStyle = palette.keys;
		ctx.fill();
	}
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
/**
* 十字准线（14 文档 §4.3）：一条竖线，贯穿上下两个面板与中间那道留白。
*
* 用 `--border-strong` 而不是度量色——它是参考线，不是数据。半像素偏移让这 1px 落在设备
* 像素上，否则在 150% 缩放的 Windows 上会糊成两像素宽的灰带（同 canvas.ts 的格线）。
*/
function drawCrosshair(ctx, palette, plot, slot, index) {
	const x = Math.round(plot.x + slot * (index + .5)) + .5;
	ctx.strokeStyle = palette.strong;
	ctx.lineWidth = 1;
	ctx.beginPath();
	ctx.moveTo(x, plot.y);
	ctx.lineTo(x, plot.y + plot.h);
	ctx.stroke();
}
function drawXAxis(ctx, buckets, palette, x, w, baseline) {
	ctx.font = cssFont(11);
	drawTimeAxis(ctx, buckets.map((item) => String(item.label ?? "")), {
		x,
		w
	}, baseline + 4, palette.faint);
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
//#region frontend/src/charts/stacked-bar.ts
var PAD = {
	top: 8,
	right: 8,
	bottom: 16,
	left: 52
};
var drawStackedBar = (ctx, box, data, palette) => {
	const buckets = data.buckets || [];
	if (!buckets.length) return;
	const plot = {
		x: PAD.left,
		y: PAD.top,
		w: Math.max(1, box.width - PAD.left - PAD.right),
		h: Math.max(1, box.height - PAD.top - PAD.bottom)
	};
	const max = niceMax(Math.max(...buckets.map((item) => item.total || 0)));
	ctx.font = cssFont(11);
	ctx.strokeStyle = palette.grid;
	ctx.fillStyle = palette.faint;
	ctx.textAlign = "right";
	ctx.textBaseline = "middle";
	for (let step = 0; step <= 2; step += 1) {
		const y = plot.y + plot.h - plot.h * step / 2;
		ctx.beginPath();
		ctx.moveTo(plot.x, Math.round(y) + .5);
		ctx.lineTo(plot.x + plot.w, Math.round(y) + .5);
		ctx.stroke();
		ctx.fillText(formatDurationShort(max * step / 2), plot.x - 6, y);
	}
	const slot = plot.w / buckets.length;
	const width = Math.max(1, Math.min(slot * .72, 30));
	const hatch = hatchPattern(ctx, palette.strong);
	buckets.forEach((item, index) => {
		const centre = plot.x + slot * (index + .5);
		const x = centre - width / 2;
		box.hits.push({
			x: centre - slot / 2,
			y: plot.y,
			w: slot,
			h: plot.h,
			payload: item
		});
		if (item.gap) {
			if (hatch) ctx.fillStyle = hatch;
			ctx.fillRect(x, plot.y, width, plot.h);
			return;
		}
		let cursor = plot.y + plot.h;
		for (const part of item.parts || []) {
			const partHeight = max ? (part.seconds || 0) / max * plot.h : 0;
			if (partHeight <= 0) continue;
			ctx.fillStyle = palette.categories[part.category] || palette.categories.uncategorized;
			ctx.fillRect(x, cursor - partHeight, width, partHeight);
			cursor -= partHeight;
		}
	});
	drawTimeAxis(ctx, buckets.map((item) => String(item.label ?? "")), plot, plot.y + plot.h + 4, palette.faint);
};
function describeStackedBar(data) {
	const buckets = data?.buckets || [];
	if (!buckets.length) return null;
	return {
		caption: data.caption || "每小时使用时长",
		summary: data.summary || "按类别分层的每小时使用时长",
		columns: ["时间", "时长"],
		rows: buckets.map((item) => [String(item.label ?? ""), item.gap ? "无记录" : formatDurationShort(item.total || 0)])
	};
}
//#endregion
//#region frontend/src/components/Highlights.tsx
var import_jsx_runtime = require_jsx_runtime();
function Highlights({ items }) {
	const list = items || [];
	if (!list.length) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "dim text-sm",
		children: "数据还不够多，暂时得不出结论"
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(import_jsx_runtime.Fragment, { children: list.map((item, index) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("details", {
		className: "highlight",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("summary", { children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "highlight__mark",
				"aria-hidden": "true",
				children: "◈"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: item.text }),
			item.basis ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "highlight__toggle",
				"aria-hidden": "true",
				children: "口径"
			}) : null
		] }), item.basis ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "highlight__basis",
			children: ["口径：", item.basis]
		}) : null]
	}, `${index}-${item.text}`)) });
}
//#endregion
//#region frontend/src/components/StackBar.tsx
function StackBar({ segments, label = "构成", onSelect = null }) {
	const items = (segments || []).filter((item) => (Number(item.percent) || 0) > 0);
	const summary = items.length ? `${label}：${items.map((item) => `${item.name} ${formatPercent(item.percent)}`).join("，")}` : `${label}：暂无数据`;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: onSelect ? "stackbar stackbar--clickable" : "stackbar",
		role: "img",
		"aria-label": summary,
		onClick: onSelect ? (event) => {
			const id = event.target.closest(".stackbar__seg")?.dataset.id;
			if (id) onSelect(id);
		} : void 0,
		children: items.map((item) => {
			const percent = Number(item.percent) || 0;
			return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "stackbar__seg",
				"data-category": item.id,
				"data-id": item.id,
				style: { flexGrow: percent },
				title: `${item.name}：${item.formatted ?? ""}（${formatPercent(percent)}）`,
				children: percent >= 9 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "stackbar__label",
					children: item.name
				}) : null
			}, item.id);
		})
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "sr-only",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", { children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("caption", { children: label }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", { children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { children: "类别" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { children: "占比" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { children: "数值" })
			] }) }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: items.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", { children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { children: item.name ?? "" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { children: formatPercent(item.percent) }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { children: item.formatted ?? "" })
			] }, item.id)) })
		] })
	})] });
}
//#endregion
//#region frontend/src/views/insights.tsx
var title = "洞察";
/** 键位选择器最多列几个高频键。太多就失去了"挑一个看看"的意义。 */
var KEY_CHOICES_LIMIT = 12;
/** 周期切换后，已选键位可能在本周期一次都没被按——仍然查询它，让空态自己说明。 */
function keyIdFor(state) {
	if (state.selectedKeyId) return state.selectedKeyId;
	const top = (state.data.insightHeatmap?.keys || []).filter((key) => (Number(key.press_count) || 0) > 0).sort((left, right) => (Number(right.press_count) || 0) - (Number(left.press_count) || 0))[0];
	return top ? top.id : "space";
}
function needs(state) {
	const period = periodParams(state.period);
	return [
		{
			key: "insightOverview",
			path: "/overview",
			params: {
				...period,
				include: "categories,highlights"
			}
		},
		{
			key: "insightKeyboard",
			path: "/insights/app-keyboard",
			params: {
				...period,
				limit: 20
			}
		},
		{
			key: "insightRhythm",
			path: "/insights/rhythm",
			params: period
		},
		{
			key: "insightTimeline",
			path: "/usage/timeline",
			params: {
				...period,
				top: 10
			}
		},
		{
			key: "insightHeatmap",
			path: "/keyboard/heatmap",
			params: period
		},
		{
			key: "insightKey",
			path: `/keyboard/keys/${keyIdFor(state)}`,
			params: period
		}
	];
}
function reload() {
	const state = getState();
	for (const request of needs(state)) fetchInto(request.key, request.path, request.params);
}
function Bar({ ratio, profile }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "bar",
		"data-profile": profile,
		style: { "--fill": Math.max(0, Math.min(1, ratio || 0)) },
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("i", {})
	});
}
/** 下钻：同一张键盘热力图换一个范围（06 文档 §7 的"范围切换"）。 */
function drillTo(appId) {
	setState("scopeAppId", appId);
	setState("route", "keyboard");
}
function View() {
	const capabilities = useSlice("capabilities");
	const degraded = useSlice("degraded");
	const keyboard = useResource("insightKeyboard");
	const rhythm = useResource("insightRhythm");
	const error = keyboard.error || rhythm.error;
	const foregroundOk = capabilityOf(capabilities, "foreground");
	const notice = noticeFor(degraded, "foreground");
	if (!foregroundOk) return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", {
		className: "view__title sr-only",
		tabIndex: -1,
		id: "view-title",
		children: "洞察"
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
		title: "输入强度排行",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CapabilityNotice, {
			title: notice?.title || "当前环境不支持识别前台应用",
			detail: notice?.detail || "交叉分析需要把按键归到应用上，键盘总量统计不受影响。",
			hint: notice?.hint || ""
		})
	})] });
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", {
			className: "view__title sr-only",
			tabIndex: -1,
			id: "view-title",
			children: "洞察"
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Section, {
			title: "构成与结论",
			right: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Updated, {}),
			lead: true,
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "grid grid--2",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
					title: "构成",
					children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "stacks",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
							className: "stacks__label",
							children: "时间去了哪些类别"
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Categories, {})] }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
							className: "stacks__label",
							children: "其中多少是在真的输入"
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Intensity, {})] })]
					})
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
					title: "结论",
					children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "highlights",
						children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Conclusions, {})
					})
				})]
			})
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
			title: "输入强度排行",
			footer: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "card__hint",
				children: rankNote(keyboard.data)
			}),
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(AttributionNotice, {}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "data-table__scroll",
				children: error ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ErrorState, {
					message: error.message,
					onRetry: reload
				}) : !keyboard.data ? keyboard.loading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 5 }) : null : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Ranking, { payload: keyboard.data })
			})] })
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KeySplitCard, {}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
			title: "节奏对比",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(RhythmContrast, {
				rhythm: rhythm.data,
				loading: rhythm.loading
			})
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
			title: "每小时时间去向",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Hourly, {})
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "grid grid--2",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
				title: "专注度",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Focus, {
					rhythm: rhythm.data,
					loading: rhythm.loading
				})
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
				title: "作息",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Rhythm, {
					rhythm: rhythm.data,
					loading: rhythm.loading
				})
			})]
		})
	] });
}
function rankNote(payload) {
	if (!payload) return "";
	const parts = [payload.kpm_basis ? `KPM 口径：${payload.kpm_basis}` : ""];
	if (payload.unattributed_presses) parts.push(`另有 ${formatCount(payload.unattributed_presses)} 次按键没有应用归因`);
	return parts.filter(Boolean).join("。");
}
/**
* 无应用归因的时段必须明说，不能让用户把"测不到"当成"没按键"（M4 判据 3）。
* 两种来源：coverage.gaps 里 missing=foreground 的段（能力缺失/迁移数据），
* 以及响应里单列的 unattributed_presses（空闲、锁屏、被排除应用期间的按键）。
*/
function AttributionNotice() {
	const unattributed = (useSlice("coverage")?.gaps || []).filter((gap) => gap?.missing === "foreground");
	if (!unattributed.length) return null;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(import_jsx_runtime.Fragment, { children: unattributed.map((gap) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "card__hint",
		children: [
			gap.from === gap.to ? gap.from : `${gap.from} 至 ${gap.to}`,
			" 无应用归因： 该时段的按键不计入任何应用（",
			gap.message || "该环境不支持应用归因",
			"），不是零"
		]
	}, `${gap.from}-${gap.to}`)) });
}
function Ranking({ payload }) {
	const apps = payload.apps || [];
	if (!apps.length) {
		const unattributed = Number(payload.unattributed_presses) || 0;
		return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(EmptyState, {
			title: unattributed ? "该时段的按键没有应用归因" : "这段时间没有可分析的应用",
			detail: unattributed ? `${formatCount(unattributed)} 次按键发生在无法识别前台应用的时段，未计入任何应用` : "",
			mark: "·"
		});
	}
	const maxKpm = Math.max(1, ...apps.map((app) => Number(app.kpm) || 0));
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", {
		className: "data-table",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("caption", {
				className: "sr-only",
				children: "各应用的输入强度"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", { children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { children: "应用" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
					className: "numeric",
					children: "前台时长"
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
					className: "numeric",
					children: "按键"
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
					className: "numeric",
					children: "KPM"
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
					className: "numeric",
					children: "修饰键"
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { children: "画像" })
			] }) }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: apps.map((app) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", { children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("td", {
					className: "wide",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
						className: "link rank__app",
						type: "button",
						title: `在键盘中查看 ${app.display_name}`,
						onClick: () => drillTo(app.app_id),
						children: app.display_name
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "rank__keys text-xs dim",
						children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(TopKeysLine, { keys: app.top_keys })
					})]
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
					className: "numeric",
					children: app.seconds_formatted
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
					className: "numeric",
					children: formatCount(app.presses)
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
					className: "numeric",
					children: (Number(app.kpm) || 0).toFixed(1)
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
					className: "numeric",
					children: formatPercent(app.modifier_percent)
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
					className: "profile-tag",
					"data-profile": app.profile,
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "profile-tag__bar",
						children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Bar, {
							ratio: (Number(app.kpm) || 0) / maxKpm,
							profile: app.profile
						})
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: app.profile_name })]
				}) })
			] }, app.app_id)) })
		]
	});
}
/** 常用键一行小字：Space 980 · E 820 · 左Ctrl 610（M4 应用 × 键盘交付物）。 */
function TopKeysLine({ keys }) {
	const list = keys || [];
	if (!list.length) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "没有按键记录" });
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: list.slice(0, 3).map((key, index) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
		index ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: " · " }) : null,
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("b", { children: key.label }),
		/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [" ", formatCount(key.press_count)] })
	] }, key.id || key.label)) });
}
/** 每小时时间去向：按应用类别堆叠的 24 小时柱（stacked-bar 的第一个消费者，M3-5）。 */
function Hourly() {
	const coverage = useSlice("coverage");
	const { data: payload, loading } = useResource("insightTimeline");
	if (!payload) return loading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 3 }) : null;
	const hours = payload.hours || [];
	const gaps = gapSet(coverage, ["foreground"]);
	const data = {
		buckets: hours.map((hour) => ({
			bucket: String(hour.hour),
			label: `${hour.hour}:00`,
			seconds: hour.total_seconds,
			presses: hour.presses,
			categories: hour.categories || {},
			total: hour.total_seconds,
			parts: Object.entries(hour.categories || {}).map(([category, seconds]) => ({
				category,
				seconds,
				name: category
			}))
		})),
		caption: "每小时时间去向",
		summary: "按应用类别分层的每小时前台时长，共 24 个小时"
	};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "chart chart--medium",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Chart, {
			data,
			draw: drawStackedBar,
			describe: describeStackedBar,
			height: 170,
			label: "每小时时间去向",
			onHover: showChartTooltip,
			onLeave: hideChartTooltip
		})
	}), gaps.size ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "card__hint",
		children: [gaps.size, " 天无应用归因，这些天的时长未计入各小时"]
	}) : null] });
}
/**
* 节奏对比（M4）：一天中打字最密集的时段 vs 屏幕时间最长的时段。
* 上面一条 24 小时的 KPM 柱给"密度长什么样"，下面两行结论给出两个峰值的答案。
*/
function RhythmContrast({ rhythm, loading }) {
	if (!rhythm) return loading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 2 }) : null;
	const data = {
		buckets: (rhythm.hourly || []).map((item) => ({
			bucket: String(item.hour).padStart(2, "0"),
			label: `${item.hour}:00`,
			seconds: item.seconds,
			presses: item.presses,
			categories: {}
		})),
		mode: "kpm",
		caption: "每小时输入强度",
		summary: "一天 24 小时的输入强度（KPM）"
	};
	const peaks = rhythm.hour_peaks;
	const typing = peaks?.typing;
	const screen = peaks?.screen;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "chart chart--medium",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Chart, {
			data,
			draw: drawPanelPair,
			describe: describePanelPair,
			height: 150,
			label: "每小时输入强度",
			onHover: showChartTooltip,
			onLeave: hideChartTooltip
		})
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "stack",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("dl", {
			className: "kv-list",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "打字最密集" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: typing ? `${typing.hour}:00（${(Number(typing.kpm) || 0).toFixed(1)} KPM）` : "—" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "屏幕时间最长" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: screen ? `${screen.hour}:00（${formatDurationShort(screen.seconds)}）` : "—" }),
				typing && screen ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "是否同一时段" }) : null,
				typing && screen ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: peaks?.same_hour ? "是——这段时间真正用在了输入上" : "否——屏幕最长的那小时更多在阅读或观看" }) : null
			]
		}), typing || screen ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "card__hint",
			children: ["口径：", peaks?.typing_basis || rhythm.hourly_basis || ""]
		}) : null]
	})] });
}
function Focus({ rhythm, loading }) {
	if (!rhythm) return loading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 2 }) : null;
	const blocks = rhythm.focus_blocks || [];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "stack",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("dl", {
				className: "kv-list",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "应用切换" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("dd", { children: [formatCount(rhythm.switch_count), " 次"] }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "每小时切换" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: (Number(rhythm.switches_per_hour) || 0).toFixed(1) }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "最长专注" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("dd", { children: [(Number(rhythm.longest_focus_minutes) || 0).toFixed(0), " 分钟"] })
				]
			}),
			rhythm.switches_basis ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "card__hint",
				children: ["口径：", rhythm.switches_basis]
			}) : null,
			blocks.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "focus-blocks",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "text-sm muted",
					children: "最长的几段专注"
				}), blocks.slice(0, 6).map((block) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "focus-block",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
							formatClock(block.start),
							"-",
							formatClock(block.end)
						] }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "truncate",
							children: block.display_name
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
							className: "numeric",
							children: [(Number(block.minutes) || 0).toFixed(0), " 分钟"]
						})
					]
				}, `${block.start}-${block.display_name}`))]
			}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "card__hint",
				children: "这段时间没有足够长的连续使用"
			})
		]
	});
}
function Rhythm({ rhythm, loading }) {
	if (!rhythm) return loading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 2 }) : null;
	const active = rhythm.active_hours;
	const peak = rhythm.peak_kpm;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "stack",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("dl", {
			className: "kv-list",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "首次活动" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: active?.first || "-" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "末次活动" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: active?.last || "-" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "活跃跨度" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("dd", { children: [(Number(active?.span_hours) || 0).toFixed(1), " 小时"] }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "峰值 KPM" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: formatCount(peak?.value || 0) }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "峰值时刻" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: peak?.at ? formatClock(peak.at) : "-" })
			]
		})
	});
}
/**
* 键位 × 应用。选择器按当前周期的高频键动态生成（M3-6），不再硬编码 6 个键。
*
* 选择器长在**这张卡的卡头**上（17 文档 §4.1）：它只决定这一块看哪个键，不影响别的
* 面板。原先它 portal 到周期栏右段，读起来像是一个整屏筛选。
*/
function KeySplitCard() {
	const selectedKeyId = useSlice("selectedKeyId");
	const heatmap = useResource("insightHeatmap");
	const detail = useResource("insightKey");
	const choices = (heatmap.data?.keys || []).filter((key) => (Number(key.press_count) || 0) > 0).sort((left, right) => (Number(right.press_count) || 0) - (Number(left.press_count) || 0)).slice(0, KEY_CHOICES_LIMIT).map((key) => ({
		id: key.id,
		label: `${key.label} · ${formatCount(key.press_count)}`
	}));
	if (selectedKeyId && !choices.some((choice) => choice.id === selectedKeyId)) {
		const known = (heatmap.data?.keys || []).find((key) => key.id === selectedKeyId);
		choices.push({
			id: selectedKeyId,
			label: known?.label || selectedKeyId
		});
	}
	const current = selectedKeyId || choices[0]?.id || "";
	const selector = choices.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("select", {
		className: "control",
		"aria-label": "选择键位",
		value: current,
		onChange: (event) => {
			setState("selectedKeyId", event.target.value);
			fetchInto("insightKey", `/keyboard/keys/${event.target.value}`, periodParams(getState().period));
		},
		children: choices.map((choice) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
			value: choice.id,
			children: choice.label
		}, choice.id))
	}) : null;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
		title: "键位与应用",
		controls: selector,
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "key-app-split",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(KeyAppRows, {
				payload: detail.data,
				loading: detail.loading
			})
		})
	});
}
/**
* 类别构成（从总览下沉）。槽位顺序 = 后端下发的顺序，不按大小排：相邻关系因此确定、
* 可事先校验，且同一个类别在每个周期都在同一个位置（14 文档 §2.10）。
*/
function Categories() {
	const { data, loading } = useResource("insightOverview");
	if (!data) return loading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 3 }) : null;
	const categories = data.categories || [];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StackBar, {
		label: "类别构成",
		segments: categories.map((item) => ({
			id: item.id,
			name: item.name,
			percent: item.percent,
			formatted: item.seconds_formatted
		}))
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "category-list",
		children: [categories.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CategoryRow, {
			item,
			percent: item.percent
		}, item.id)), categories.length ? null : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(EmptyState, {
			title: "这段时间没有应用记录",
			detail: "换一个日期，或确认采集正在运行"
		})]
	})] });
}
/** 输入强度构成：与类别构成上下对齐、共用同一条 100% 宽度基准（14 文档 §4.3）。 */
function Intensity() {
	const { data: payload, loading } = useResource("insightKeyboard");
	if (!payload) return loading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 2 }) : null;
	const distribution = payload.distribution;
	const buckets = distribution?.buckets || [];
	const total = Number(distribution?.total_seconds) || 0;
	const share = (seconds) => total ? (seconds || 0) / total * 100 : 0;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StackBar, {
		label: "输入强度构成",
		segments: buckets.map((item) => ({
			id: item.id,
			name: item.name,
			percent: share(item.seconds),
			formatted: item.seconds_formatted
		}))
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "category-list",
		children: [buckets.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CategoryRow, {
			item,
			percent: share(item.seconds),
			kind: "profile"
		}, item.id)), payload.unattributed_presses ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "card__hint",
			children: [
				"另有 ",
				formatCount(payload.unattributed_presses),
				" 次按键没有应用归因"
			]
		}) : null]
	})] });
}
function CategoryRow({ item, percent, kind = "category" }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "category-row",
		"data-category": kind === "category" ? item.id : void 0,
		"data-profile": kind === "profile" ? item.id : void 0,
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "swatch",
				"aria-hidden": "true"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "truncate",
				children: item.name
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "category-row__percent",
				children: formatPercent(percent)
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "category-row__value",
				children: item.seconds_formatted
			})
		]
	});
}
/** 结论（从总览下沉）。文案与计算口径都由后端给，前端不编（06 文档 §5.3）。 */
function Conclusions() {
	const { data, loading } = useResource("insightOverview");
	if (!data) return loading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 3 }) : null;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Highlights, { items: data.highlights });
}
function KeyAppRows({ payload, loading }) {
	if (!payload) return loading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 2 }) : null;
	const byApp = payload.by_app || [];
	const totals = payload.totals;
	if (!byApp.length) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(EmptyState, {
		title: `${payload.key.label} 没有按应用拆分的数据`,
		detail: "这个键在本周期内没有被按下，或按键发生在无法识别前台应用的时段",
		mark: "·"
	});
	const top = Math.max(1, ...byApp.map((item) => Number(item.press_count) || 0));
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "text-sm muted",
		children: [
			payload.key.label,
			" 的 ",
			formatCount(totals?.press_count || 0),
			" 次按下来自："
		]
	}), byApp.slice(0, 10).map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "top-key",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "rank" }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "truncate",
				children: item.display_name
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Bar, { ratio: (Number(item.press_count) || 0) / top }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "top-key__count",
				children: formatCount(item.press_count)
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "top-key__percent",
				children: formatPercent(item.percent)
			})
		]
	}, item.app_id))] });
}
//#endregion
export { View, needs, title };
