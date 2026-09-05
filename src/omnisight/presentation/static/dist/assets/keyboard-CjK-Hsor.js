import { C as useSlice, E as setState, G as require_react_dom, H as on, K as require_react, S as useResource, U as Icon, W as require_jsx_runtime, b as formatPercent, f as hide, h as formatCount, n as capabilityOf, o as prefersReducedMotion, p as show, r as noticeFor, w as getState } from "./degraded-qMnijys5.js";
import { i as Segmented } from "./controls-CacwHgpC.js";
import { a as fromISO, c as HEAT_BOUNDS, d as formatMetric, f as heatLevel, h as metricOf, i as bucketCoversGap, l as METRICS, m as isSaturated, n as METRIC_SLOT_ID, o as gapSet, p as heatRatio, r as Updated, s as periodParams, t as fetchInto, u as TIMELINE_VIEWS } from "./main-BgBdqxK5.js";
import { n as Section, t as Card } from "./Card-CwX6lTXj.js";
import { i as Mark, n as AppGrid, t as Quad } from "./Quad-1An0_H8C.js";
import { a as SkeletonRows, i as GapLegend, n as EmptyState, r as ErrorState, t as CapabilityNotice } from "./states-BInd1nRj.js";
import { a as bar, c as niceMax, i as Chart, n as hideChartTooltip, o as cssFont, r as showChartTooltip, s as hatchPattern, t as drawTimeAxis } from "./axis-J_X4OlX3.js";
//#region frontend/src/charts/CalendarHeatmap.tsx
var import_react_dom = require_react_dom();
var import_react = require_react();
var import_jsx_runtime = require_jsx_runtime();
var WEEKDAYS = [
	"一",
	"二",
	"三",
	"四",
	"五",
	"六",
	"日"
];
function CalendarHeatmap({ buckets, scale, gaps, weekStartsOn = 0, metric = "press_count", onSelect = null }) {
	const cells = (0, import_react.useMemo)(() => padToWeeks(buckets || [], weekStartsOn, metric), [
		buckets,
		weekStartsOn,
		metric
	]);
	const months = (0, import_react.useMemo)(() => monthMarks(cells), [cells]);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "calendar",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "weekday-axis",
			children: Array.from({ length: 7 }, (_unused, index) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: index % 2 === 0 ? WEEKDAYS[(index + weekStartsOn) % 7] : "" }, index))
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "calendar__body",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "heatgrid__months",
				"aria-hidden": "true",
				children: months.map((mark) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "heatgrid__month",
					style: { gridColumn: mark.column },
					children: mark.label
				}, mark.column))
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "heatgrid",
				role: "group",
				"aria-label": "每日活跃度",
				onClick: onSelect ? (event) => {
					const bucket = event.target.closest(".heat-cell")?.dataset.bucket;
					if (bucket) onSelect(bucket);
				} : void 0,
				children: cells.map((cell) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(HeatCell, {
					cell,
					scale,
					gap: Boolean(cell.bucket && gaps?.has(cell.bucket))
				}, cell.key))
			})]
		})]
	});
}
function HeatCell({ cell, scale, gap }) {
	if (cell.empty) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "heat-cell",
		"data-empty": "true"
	});
	const ratio = gap ? 0 : heatRatio(cell.value, scale);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "heat-cell",
		"data-bucket": cell.bucket,
		"data-level": heatLevel(ratio),
		"data-gap": gap ? "true" : void 0,
		"aria-label": gap ? `${cell.bucket}：无记录` : `${cell.bucket}：${formatCount(cell.value)} 次`
	});
}
/** 首尾补空格子，让第一列从"周起始日"开始，否则整张图会错位一天。 */
function padToWeeks(buckets, weekStartsOn, metric) {
	if (!buckets.length) return [];
	const read = (item) => Number(item[metric]) || 0;
	const first = fromISO(buckets[0].bucket);
	if (!first) return buckets.map((item) => ({
		key: item.bucket,
		bucket: item.bucket,
		value: read(item)
	}));
	const offset = ((first.getDay() + 6) % 7 - weekStartsOn + 7) % 7;
	const padded = [];
	for (let index = 0; index < offset; index += 1) padded.push({
		key: `pad-${index}`,
		empty: true
	});
	for (const item of buckets) padded.push({
		key: item.bucket,
		bucket: item.bucket,
		value: read(item)
	});
	return padded;
}
/**
* 月份标签落在哪一列。
*
* 格子是按列填的（`grid-auto-flow: column`，每列 7 天），所以第 n 个格子在第
* `floor(n / 7) + 1` 列——每个月的第一天落在哪一列，标签就放在哪一列。
*/
function monthMarks(cells) {
	const marks = [];
	let previous = "";
	cells.forEach((cell, index) => {
		if (cell.empty || !cell.bucket) return;
		const month = cell.bucket.slice(0, 7);
		if (month === previous) return;
		previous = month;
		marks.push({
			column: Math.floor(index / 7) + 1,
			label: `${Number(month.slice(5, 7))} 月`
		});
	});
	return marks.filter((mark, index) => index === 0 || mark.column - marks[index - 1].column >= 4);
}
//#endregion
//#region frontend/src/charts/scale-bars.ts
var PAD = {
	top: 10,
	right: 8,
	bottom: 20,
	left: 52
};
function scaleBarsDraw(options) {
	const { format, accent = "keys" } = options;
	return (ctx, box, data, palette) => draw(ctx, box, data, palette, format, accent);
}
function scaleBarsDescribe(options) {
	const { format } = options;
	return (data) => {
		const buckets = data?.buckets || [];
		if (!buckets.length) return null;
		return {
			caption: data.caption || "",
			summary: data.summary || "",
			columns: ["时间", data.valueLabel],
			rows: buckets.map((item) => [String(item.label ?? item.bucket ?? ""), item.gap ? "无记录" : format(item.value || 0)])
		};
	};
}
function draw(ctx, box, data, palette, format, accent) {
	const buckets = data.buckets || [];
	if (!buckets.length) return;
	const plot = {
		x: PAD.left,
		y: PAD.top,
		w: Math.max(1, box.width - PAD.left - PAD.right),
		h: Math.max(1, box.height - PAD.top - PAD.bottom)
	};
	const max = niceMax(Math.max(...buckets.map((item) => item.value || 0)));
	const slot = plot.w / buckets.length;
	const width = Math.max(1, Math.min(slot - 2, 24));
	const hatch = hatchPattern(ctx, palette.strong);
	const fill = accent === "time" ? palette.time : palette.keys;
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
		ctx.fillText(format(max * step / 2), plot.x - 6, y);
	}
	buckets.forEach((item, index) => {
		const centre = plot.x + slot * (index + .5);
		const x = centre - width / 2;
		box.hits.push({
			x: centre - slot / 2,
			y: plot.y,
			w: slot,
			h: plot.h,
			payload: {
				label: item.label ?? item.bucket,
				gap: item.gap,
				reading: {
					label: data.valueLabel,
					text: format(item.value || 0)
				}
			}
		});
		if (item.gap) {
			if (hatch) ctx.fillStyle = hatch;
			ctx.fillRect(x, plot.y, width, plot.h);
			return;
		}
		const value = item.value || 0;
		if (value <= 0) return;
		const height = Math.max(2, value / max * plot.h);
		ctx.fillStyle = fill;
		bar(ctx, x, plot.y + plot.h - height, width, height);
	});
	drawTimeAxis(ctx, buckets.map((item) => String(item.label ?? "")), plot, plot.y + plot.h + 5, palette.faint);
}
//#endregion
//#region frontend/src/components/AppPicker.tsx
var FOCUSABLE = "button:not([disabled]), input:not([disabled])";
function AppPicker({ apps, runningIds = [], onChange = null }) {
	const scopeAppId = useSlice("scopeAppId");
	const [open, setOpen] = (0, import_react.useState)(false);
	const root = (0, import_react.useRef)(null);
	const panel = (0, import_react.useRef)(null);
	const trigger = (0, import_react.useRef)(null);
	const list = apps || [];
	(0, import_react.useEffect)(() => {
		const current = getState().scopeAppId;
		if (current && list.length && !list.some((app) => app.app_id === current)) setState("scopeAppId", null);
	}, [list]);
	(0, import_react.useEffect)(() => {
		if (!open) return;
		const onKeydown = (event) => {
			if (event.key === "Escape") {
				event.preventDefault();
				setOpen(false);
				trigger.current?.focus();
				return;
			}
			if (event.key !== "Tab") return;
			const host = panel.current;
			if (!host) return;
			const items = [...host.querySelectorAll(FOCUSABLE)].filter((node) => node.offsetParent !== null);
			if (!items.length) return;
			const first = items[0];
			const last = items[items.length - 1];
			if (event.shiftKey && document.activeElement === first) {
				event.preventDefault();
				last.focus();
			} else if (!event.shiftKey && document.activeElement === last) {
				event.preventDefault();
				first.focus();
			}
		};
		const onPointerDown = (event) => {
			if (event.target instanceof Node && root.current?.contains(event.target)) return;
			setOpen(false);
		};
		document.addEventListener("keydown", onKeydown, true);
		document.addEventListener("pointerdown", onPointerDown, true);
		return () => {
			document.removeEventListener("keydown", onKeydown, true);
			document.removeEventListener("pointerdown", onPointerDown, true);
		};
	}, [open]);
	const pick = (appId) => {
		setState("scopeAppId", appId);
		setOpen(false);
		trigger.current?.focus();
		onChange?.(appId);
	};
	const current = list.find((app) => app.app_id === scopeAppId) || null;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "app-picker",
		ref: root,
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "muted text-sm",
				children: "范围"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
				className: "button app-picker__trigger",
				type: "button",
				ref: trigger,
				"aria-haspopup": "dialog",
				"aria-expanded": open,
				onClick: () => setOpen((value) => !value),
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "app-picker__mark",
						children: current ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Mark, { app: current }) : null
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "app-picker__name",
						children: current ? current.user_alias || current.display_name : "全部应用"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, {
						name: "down",
						size: 14
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "app-picker__panel",
				ref: panel,
				hidden: !open,
				role: "dialog",
				"aria-label": "选择应用范围",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(AppGrid, {
					apps: list,
					runningIds,
					selectedId: scopeAppId,
					onPick: pick,
					searchKey: open ? "open" : "closed"
				})
			})
		]
	});
}
//#endregion
//#region frontend/src/domain/keyboard-layout.ts
/** 已知的特殊形状。只有一个，且这就是重点（L 形 ISO 回车无法用宽度倍数表达）。 */
var KNOWN_SHAPES = /* @__PURE__ */ new Set(["iso_enter"]);
function isGap(slot) {
	return !slot || slot.id === "gap";
}
/**
* 按行分组的 id，供上下方向键在行间移动。
*/
function keyRows(layout) {
	return (layout?.rows || []).map((row) => row.filter((slot) => !isGap(slot)).map((slot) => slot.id));
}
//#endregion
//#region frontend/src/components/KeyboardView.tsx
var PRESS_CLEAR_MS = 220;
/** 键面数值的字号地板。低于它宁可不印，也不印成 8px（14 文档 §2.5）。 */
var VALUE_MIN_PX = 11;
/** .key-cap__value 的字号系数，与 key-cap.css 里的 calc() 保持一致。 */
var VALUE_RATIO = .27;
function clamp(value, low, high) {
	if (high < low) return low;
	return Math.min(high, Math.max(low, value));
}
function KeyboardView({ layout, heatmap, metric, density = "standard", onSelectKey = null }) {
	const board = (0, import_react.useRef)(null);
	const root = (0, import_react.useRef)(null);
	const caps = (0, import_react.useRef)(/* @__PURE__ */ new Map());
	const [cursor, setCursor] = (0, import_react.useState)({
		row: 0,
		col: 0
	});
	const [valuesVisible, setValuesVisible] = (0, import_react.useState)(true);
	const rows = (0, import_react.useMemo)(() => keyRows(layout), [layout]);
	const values = (0, import_react.useMemo)(() => new Map((heatmap?.keys || []).map((key) => [key.id, key])), [heatmap]);
	const scale = heatmap?.scale || null;
	const total = Number(heatmap?.totals?.press_count) || 0;
	(0, import_react.useEffect)(() => setCursor({
		row: 0,
		col: 0
	}), [layout]);
	(0, import_react.useEffect)(() => {
		const reduced = prefersReducedMotion();
		return on("key:press", (keys) => {
			for (const keyId of keys) {
				const cap = caps.current.get(keyId);
				if (!cap) continue;
				cap.classList.add("is-pressed");
				window.setTimeout(() => cap.classList.remove("is-pressed"), reduced ? 60 : PRESS_CLEAR_MS);
			}
		});
	}, []);
	/**
	* 键面装不下 11px 的数值就整体藏起来（14 文档 §2.5）。
	*
	* 现状的判据是"窗口 < 1024px"，但真正决定字号的是 --u：1280px 窗口下键面数值只有
	* 8.6px、1100px 下 7.4px，都低于全站 11px 的下限，而窗口宽度那条规则一个都拦不住。
	* 这里改成按实际 --u 算，同一条规则管所有宽度。值印不下时，表格视图仍然给得出。
	*/
	(0, import_react.useEffect)(() => {
		const node = board.current;
		if (!node) return;
		const measure = () => {
			const host = root.current;
			if (!host) return;
			const unit = Number.parseFloat(getComputedStyle(host).getPropertyValue("--u")) || 0;
			setValuesVisible(unit * VALUE_RATIO >= VALUE_MIN_PX);
		};
		measure();
		const observer = new ResizeObserver(measure);
		observer.observe(node);
		return () => observer.disconnect();
	}, [layout, density]);
	(0, import_react.useEffect)(() => () => hide(), []);
	const currentKey = rows[cursor.row]?.[cursor.col] || null;
	const handleKeydown = (event) => {
		const moves = {
			ArrowLeft: [0, -1],
			ArrowRight: [0, 1],
			ArrowUp: [-1, 0],
			ArrowDown: [1, 0]
		};
		if (event.key === "Enter" || event.key === " ") {
			if (currentKey && onSelectKey) {
				onSelectKey(currentKey);
				event.preventDefault();
			}
			return;
		}
		const move = moves[event.key];
		if (!move) return;
		event.preventDefault();
		const nextRow = clamp(cursor.row + move[0], 0, rows.length - 1);
		const rowKeys = rows[nextRow] || [];
		setCursor({
			row: nextRow,
			col: clamp(cursor.col + move[1], 0, rowKeys.length - 1)
		});
	};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "keyboard-tray-scroll",
			ref: board,
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "keyboard-tray",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "keyboard",
					ref: root,
					"data-family": layout?.family || "unknown",
					"data-density": density === "compact" ? "compact" : void 0,
					"data-values": valuesVisible ? "on" : "off",
					role: "group",
					"aria-label": `键盘热力图（${layout?.name || "未知布局"}）`,
					tabIndex: 0,
					"aria-activedescendant": currentKey ? `key-${currentKey}` : void 0,
					onKeyDown: handleKeydown,
					children: (layout?.rows || []).map((row, rowIndex) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "keyboard__row",
						children: row.map((slot, slotIndex) => isGap(slot) ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Spacer, { width: slot?.w }, `gap-${slotIndex}`) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(KeyCap, {
							slot,
							entry: values.get(slot.id),
							metric,
							scale,
							total,
							current: slot.id === currentKey,
							register: (node) => {
								if (node) caps.current.set(slot.id, node);
								else caps.current.delete(slot.id);
							},
							onActivate: onSelectKey
						}, slot.id))
					}, rowIndex))
				})
			})
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Orphans, {
			keys: heatmap?.orphan_keys,
			metric
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KeyTable, {
			values,
			metric
		})
	] });
}
function Spacer({ width }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
		className: "key-spacer",
		"aria-hidden": "true",
		style: { "--w": width ?? 1 }
	});
}
function KeyCap({ slot, entry, metric, scale, total, current, register, onActivate }) {
	const shape = slot.shape && KNOWN_SHAPES.has(slot.shape) ? slot.shape : void 0;
	if (slot.shape && !shape) console.warn(`未知键形 ${slot.shape}（${slot.id}），按矩形渲染`);
	const definition = metricOf(metric);
	const value = entry ? Number(entry[metric]) || 0 : 0;
	const ratio = heatRatio(value, scale);
	const label = slot.label || slot.id;
	const share = total && metric === "press_count" ? `，占比 ${formatPercent(value / total * 100)}` : "";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		role: "img",
		id: `key-${slot.id}`,
		ref: register,
		className: current ? "key-cap is-current" : "key-cap",
		"data-key-id": slot.id,
		"data-level": heatLevel(ratio),
		"data-saturated": isSaturated(value, scale) ? "true" : void 0,
		"data-shape": shape,
		"aria-label": `${label}，${definition.name} ${definition.format(value)}${share}`,
		style: {
			"--w": slot.w ?? 1,
			"--h": slot.h ?? 1
		},
		onPointerEnter: (event) => show({
			title: label,
			rows: entry ? [
				["次数", formatCount(entry.press_count)],
				["占比", formatPercent(entry.percent)],
				["均时长", formatMetric("duration_avg_ms", entry.duration_avg_ms)]
			] : [["次数", "0"]],
			x: event.clientX,
			y: event.clientY
		}),
		onPointerLeave: () => hide(),
		onClick: onActivate ? () => onActivate(slot.id) : void 0,
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: "key-cap__label",
			children: label
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: "key-cap__value",
			children: value ? definition.format(value) : ""
		})]
	});
}
/**
* 色阶图例。**长在键盘卡头右侧**（17 文档 §4.3，TimeLens 的做法）而不是键盘下方——
* 读者是先看到图例再去读键面的，图例在下面等于让人回头找。因此它导出给视图用，
* 而不是由 KeyboardView 自己渲染在板子底下。
*/
function HeatLegend({ metric, scale }) {
	const definition = metricOf(metric);
	const top = Number(scale?.p95) || 0;
	const max = Number(scale?.max) || 0;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "heat-legend",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "未按过" }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "heat-legend__scale",
				"aria-hidden": "true",
				children: [
					0,
					1,
					2,
					3,
					4,
					5
				].map((level) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "heat-legend__step",
					"data-level": level,
					title: level ? `≤ ${definition.format(top * HEAT_BOUNDS[level])}` : "未按过"
				}, level))
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: definition.format(top) }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
				className: "card__hint",
				title: `色阶按 p95（${definition.format(top)}）归一，超出的键饱和到最深并在右上角切一个缺口。最大值 ${definition.format(max)}。`,
				"aria-label": `色阶按 p95 归一，最大值 ${definition.format(max)}`,
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "p95 归一 " }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, {
					name: "info",
					size: 13
				})]
			})
		]
	});
}
/** 布局里没有的键（后端的 orphan_keys）。不渲染它们，键盘总数就与指标卡不一致。 */
function Orphans({ keys, metric }) {
	if (!keys?.length) return null;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "orphans",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "orphans__title",
			children: [
				"不在当前布局中的键（",
				keys.length,
				"）"
			]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "orphans__list",
			children: keys.map((key) => {
				const record = key;
				return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
					className: "key-chip",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("b", { children: key.label || key.id }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: formatMetric(metric, Number(record[metric] ?? key.press_count ?? 0)) })]
				}, key.id);
			})
		})]
	});
}
/**
* 表格孪生：每个键的完整读数，可复制（14 文档 §4.4）。
*
* 键盘是 DOM 而不是 canvas，所以它没有走 charts/Chart.tsx 的 sr-only 表格路径。
* 这张折叠表补上，同时兜住"键面数值印不下"的场景。
*/
function KeyTable({ values, metric }) {
	const definition = metricOf(metric);
	const read = (entry) => Number(entry[metric]) || 0;
	const list = [...values.values()].filter((entry) => read(entry) > 0).sort((a, b) => read(b) - read(a));
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("details", {
		className: "keyboard-table",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("summary", { children: "表格视图" }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "keyboard-table__scroll",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", {
				className: "table",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", { children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { children: "键位" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { children: "次数" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { children: "占比" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", { children: "均时长" })
				] }) }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: list.map((entry) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", { children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { children: entry.label || entry.id }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
						className: "numeric",
						children: definition.format(read(entry))
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
						className: "numeric",
						children: formatPercent(entry.percent)
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
						className: "numeric",
						children: formatMetric("duration_avg_ms", entry.duration_avg_ms)
					})
				] }, entry.id)) })]
			})
		})]
	});
}
//#endregion
//#region frontend/src/domain/buckets.ts
/**
* **泛型而不是收 `TrendBucket`**：键盘时间线的桶（`KeyTimelineBucket`）没有
* seconds / presses / categories，而它同样要标缺口。写成泛型之后调用点不必 `as`
* 一下——那种转型会把"这里的类型其实对不上"这件事藏起来。
*/
function markGaps(buckets, granularity, gaps, period) {
	if (!buckets?.length || !gaps || gaps.size === 0) return [...buckets || []];
	if (granularity === "hour") {
		const day = period?.start || period?.anchor;
		const missing = Boolean(day && gaps.has(day));
		return buckets.map((bucket) => missing ? {
			...bucket,
			gap: true
		} : bucket);
	}
	return buckets.map((bucket) => {
		return (granularity === "day" ? gaps.has(bucket.bucket) : bucketCoversGap(bucket.bucket, gaps)) ? {
			...bucket,
			gap: true
		} : bucket;
	});
}
//#endregion
//#region frontend/src/views/keyboard.tsx
var title = "键盘";
var TOP_KEYS = 10;
var GRAIN_NAMES = {
	hours: "小时",
	days: "天",
	months: "月",
	years: "年"
};
/** markGaps 用的桶粒度命名（它按 hour/day/month/year 判断缺口映射）。 */
var GAP_GRAIN = {
	hours: "hour",
	days: "day",
	months: "month",
	years: "year"
};
var DENSITIES = [{
	id: "standard",
	name: "标准"
}, {
	id: "compact",
	name: "紧凑"
}];
/** 布局族：auto 时不传 family，让后端按平台默认值决定（05 文档 §7）。 */
function familyParam(state) {
	const requested = state.prefs.keyboardLayout;
	return requested && requested !== "auto" ? { family: requested } : {};
}
function needs(state) {
	const period = periodParams(state.period);
	const scope = state.scopeAppId ? { app_id: state.scopeAppId } : {};
	const requests = [
		{
			key: "layout",
			path: "/keyboard/layout",
			params: familyParam(state)
		},
		{
			key: "heatmap",
			path: "/keyboard/heatmap",
			params: {
				...period,
				metric: state.metric,
				...scope
			}
		},
		{
			key: "timeline",
			path: "/keyboard/timeline",
			params: {
				...period,
				view: "hours,days,months,years",
				metric: state.metric,
				...scope
			}
		},
		{
			key: "ergonomics",
			path: "/keyboard/ergonomics",
			params: {
				...period,
				...scope
			}
		},
		{
			key: "appsMeta",
			path: "/apps",
			params: { limit: 300 }
		},
		{
			key: "appsRunning",
			path: "/apps/running"
		}
	];
	if (state.selectedKeyId) requests.push({
		key: "keyDetail",
		path: `/keyboard/keys/${state.selectedKeyId}`,
		params: {
			...period,
			...scope
		}
	});
	return requests;
}
function reload() {
	const state = getState();
	for (const request of needs(state)) fetchInto(request.key, request.path, request.params);
}
function Bar({ ratio }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "bar",
		style: { "--fill": Math.max(0, Math.min(1, ratio || 0)) },
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("i", {})
	});
}
function View() {
	const metric = useSlice("metric");
	const capabilities = useSlice("capabilities");
	const degraded = useSlice("degraded");
	const selectedKeyId = useSlice("selectedKeyId");
	const layout = useResource("layout");
	const heatmap = useResource("heatmap");
	const appsMeta = useResource("appsMeta");
	const appsRunning = useResource("appsRunning");
	const [density, setDensity] = (0, import_react.useState)("standard");
	const [grain, setGrain] = (0, import_react.useState)("days");
	const metricSlot = document.getElementById(METRIC_SLOT_ID);
	const error = heatmap.error || layout.error;
	const keyboardOk = capabilityOf(capabilities, "keyboard");
	const notice = noticeFor(degraded, "keyboard");
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", {
			className: "view__title sr-only",
			tabIndex: -1,
			id: "view-title",
			children: "键盘"
		}),
		metricSlot ? (0, import_react_dom.createPortal)(/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Segmented, {
			items: METRICS,
			active: metric,
			onPick: (id) => setState("metric", id),
			variant: "switch",
			label: "统计指标"
		}), metricSlot) : null,
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Section, {
			title: "按键跟踪",
			sub: "只统计键位次数，不保存输入内容",
			lead: true,
			right: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "keyboard-view__scope",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(AppPicker, {
					apps: appsMeta.data?.apps,
					runningIds: (appsRunning.data?.apps || []).map((app) => app.app_id).filter((id) => typeof id === "number")
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Updated, {})]
			}),
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
				title: "键盘热力图",
				subtitle: "颜色越深，使用次数越多",
				controls: keyboardOk ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(HeatLegend, {
					metric,
					scale: heatmap.data?.scale
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Segmented, {
					items: DENSITIES,
					active: density,
					onPick: (id) => setDensity(id),
					small: true,
					label: "键盘密度"
				})] }) : null,
				footer: keyboardOk && heatmap.data ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Totals, { heatmap: heatmap.data }) : null,
				children: !keyboardOk ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CapabilityNotice, {
					title: notice?.title || "当前环境无法采集键盘",
					detail: notice?.detail || "应用时长统计不受影响。",
					hint: notice?.hint || ""
				}) : error ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ErrorState, {
					message: error.message,
					onRetry: reload
				}) : !layout.data || !heatmap.data ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 1 }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(KeyboardView, {
					layout: layout.data,
					heatmap: heatmap.data,
					metric,
					density,
					onSelectKey: (keyId) => {
						setState("selectedKeyId", keyId);
						loadKeyDetail(keyId);
					}
				})
			})
		}),
		selectedKeyId ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(KeyDetail, { keyId: selectedKeyId }) : null,
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Section, {
			title: "时间分布",
			sub: `按${GRAIN_NAMES[grain]}聚合 · ${metricName(metric)}`,
			right: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Segmented, {
				items: TIMELINE_VIEWS,
				active: grain,
				onPick: (id) => setGrain(id),
				small: true,
				label: "时间尺度"
			}),
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "card",
				children: grain === "days" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Calendar, {}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ScaleBars, { grain })
			})
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "grid grid--2",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
				title: `高频键位 Top ${TOP_KEYS}`,
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "top-keys",
					children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(TopKeys, {
						heatmap: heatmap.data,
						metric
					})
				})
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
				title: "手指负荷",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Ergonomics, {})
			})]
		})
	] });
}
function metricName(metric) {
	return METRICS.find((item) => item.id === metric)?.name || "";
}
/**
* 单键详情的取数。带上 scope：范围切到某个应用时，热图是那个应用的，单键详情也必须
* 是——现状这个请求不带 app_id，于是热图与详情来自两个不同的口径，界面上没有任何
* 提示（14 文档 §2.8）。
*/
function loadKeyDetail(keyId) {
	const state = getState();
	const scope = state.scopeAppId ? { app_id: state.scopeAppId } : {};
	fetchInto("keyDetail", `/keyboard/keys/${keyId}`, {
		...periodParams(state.period),
		...scope
	});
}
/** 四格总计。几何来自 KeyTrace 应用屏的四格摘要，不是原先那一行裸文字（17 文档 §4.3）。 */
function Totals({ heatmap }) {
	const totals = heatmap.totals;
	const scope = heatmap.scope;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "keyboard-totals",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Quad, { items: [
			{
				label: "按键次数",
				value: formatCount(totals?.press_count || 0)
			},
			{
				label: "活跃键位",
				value: `${totals?.active_keys || 0} 个`
			},
			{
				label: "平均时长",
				value: formatMetric("duration_avg_ms", totals?.duration_avg_ms || 0)
			},
			{
				label: "最长按压",
				value: formatMetric("duration_max_ms", totals?.duration_max_ms || 0)
			}
		] }), scope?.type === "app" ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "card__hint",
			children: ["范围：", scope.display_name || ""]
		}) : null]
	});
}
function TopKeys({ heatmap, metric }) {
	if (!heatmap) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 3 });
	const read = (key) => Number(key[metric]) || 0;
	const keys = (heatmap.keys || []).filter((key) => read(key) > 0).sort((left, right) => read(right) - read(left)).slice(0, TOP_KEYS);
	if (!keys.length) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(EmptyState, {
		title: "这段时间没有按键记录",
		mark: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, {
			name: "keyboard",
			size: 28
		})
	});
	const top = read(keys[0]) || 1;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(import_jsx_runtime.Fragment, { children: keys.map((key, index) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "top-key",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "rank",
				children: index + 1
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "top-key__label",
				children: key.label
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Bar, { ratio: read(key) / top }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "top-key__count",
				children: formatMetric(metric, read(key))
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "top-key__percent",
				children: formatPercent(key.percent)
			})
		]
	}, key.id)) });
}
/**
* 小时 / 月 / 年：一根轴上的一组柱。三个尺度共用这一个组件——它们都是一维序列，
* 差别只在桶数（24 / 12 / 若干）与标签。
*
* `available: false` 是"该视图在当前设置下拿不到"，不是"值为 0"。原始事件被关掉时
* 按小时的分布就属于这一类（services/keyboard.py 的 _hours_view）。
*/
function ScaleBars({ grain }) {
	const metric = useSlice("metric");
	const coverage = useSlice("coverage");
	const { data: payload, loading } = useResource("timeline");
	if (!payload) return loading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 1 }) : null;
	const view = payload.views?.[grain];
	if (!view || view.available === false) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CapabilityNotice, {
		title: "该视图在当前设置下不可用",
		detail: payload.warnings?.[0]?.message || "按小时的分布需要保留原始按键事件。",
		hint: "设置中开启\"保存原始按键事件\"后，此后的数据可用"
	});
	const gaps = gapSet(coverage, ["keyboard"]);
	const definition = metricOf(metric);
	const format = (value) => formatMetric(metric, value);
	const data = {
		buckets: markGaps(view.buckets, GAP_GRAIN[grain], gaps, view.period).map((bucket) => ({
			bucket: bucket.bucket,
			label: bucket.label,
			value: Number(bucket[metric]) || 0,
			gap: bucket.gap
		})),
		valueLabel: definition.name,
		caption: `按${GRAIN_NAMES[grain]}的${definition.name}`,
		summary: `按${GRAIN_NAMES[grain]}的${definition.name}，共 ${view.buckets.length} 个桶`
	};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "chart chart--scale",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Chart, {
			data,
			draw: scaleBarsDraw({
				format,
				accent: "keys"
			}),
			describe: scaleBarsDescribe({ format }),
			height: 190,
			label: data.summary,
			onHover: showChartTooltip,
			onLeave: hideChartTooltip
		})
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(GapLegend, { count: gaps.size })] });
}
/**
* 「日」这一档。365 天是**二维**的（7 行 × 53 列），因此它是日历而不是柱：一年 365 根
* 柱各占 2px，看不出星期与月份的位置，而"周末在不在打字"恰是这个尺度上最该看出的事
* （14 文档 §2.11 / §5.2）。月份轴与星期轴也是我们比两个前身都强的地方。
*/
function Calendar() {
	const coverage = useSlice("coverage");
	const prefs = useSlice("prefs");
	const metric = useSlice("metric");
	const { data: payload, loading } = useResource("timeline");
	const view = payload?.views?.days;
	if (!view) return loading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 1 }) : null;
	if (view.available === false) return null;
	const gaps = gapSet(coverage, ["keyboard"]);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(CalendarHeatmap, {
		buckets: view.buckets,
		scale: view.scale,
		gaps,
		weekStartsOn: prefs.weekStartsOn,
		metric
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(GapLegend, { count: gaps.size })] });
}
function Ergonomics() {
	const capabilities = useSlice("capabilities");
	const { data: payload, loading } = useResource("ergonomics");
	if (!payload) return loading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 3 }) : null;
	const hands = payload.hands;
	const left = Number(hands?.left) || 0;
	const right = Number(hands?.right) || 0;
	const both = left + right;
	const fingers = payload.fingers || [];
	const top = Math.max(1, ...fingers.map((finger) => Number(finger.press_count) || 0));
	const rows = payload.rows || [];
	const rowTop = Math.max(1, ...rows.map((row) => Number(row.press_count) || 0));
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "hands",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: ["左手 ", formatPercent(both ? left / both * 100 : 0)] }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "hands__bar",
					style: { "--left": both ? left / both : .5 },
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("i", {}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("i", {})]
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: ["右手 ", formatPercent(both ? right / both * 100 : 0)] })
			]
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "fingers",
			children: fingers.map((finger) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "finger-row",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "finger-row__name",
						children: finger.name
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Bar, { ratio: (Number(finger.press_count) || 0) / top }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "finger-row__percent",
						children: formatPercent(finger.percent)
					})
				]
			}, finger.id || finger.name))
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "text-sm muted",
			children: "行分布"
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "fingers",
			children: rows.map((row) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "finger-row",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "finger-row__name",
						children: row.name
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Bar, { ratio: (Number(row.press_count) || 0) / rowTop }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "finger-row__percent",
						children: formatPercent(row.percent)
					})
				]
			}, row.id || row.name))
		}),
		payload.modifier_ratio ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "card__hint",
			children: [
				"修饰键占比 ",
				formatPercent(payload.modifier_ratio.percent),
				"，口径：修饰键自身被按下的次数"
			]
		}) : null,
		capabilityOf(capabilities, "key_position_stable") ? null : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "card__hint",
			children: "当前后端无法区分左右修饰键，左右手分布仅供参考"
		})
	] });
}
function KeyDetail({ keyId }) {
	const { data: payload } = useResource("keyDetail");
	if (!payload || payload.key.id !== keyId) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
		title: "键位详情",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 2 })
	});
	const key = payload.key;
	const totals = payload.totals;
	const byApp = payload.by_app || [];
	const scope = payload.scope;
	const top = Math.max(1, ...byApp.map((item) => Number(item.press_count) || 0));
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
		title: `键位详情：${key.label}`,
		controls: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
			className: "button",
			type: "button",
			onClick: () => setState("selectedKeyId", null),
			children: "关闭"
		}),
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "stack",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "card__hint",
					children: scope?.type === "app" ? `范围：${scope.display_name || ""}` : "范围：全部应用"
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("dl", {
					className: "kv-list",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "按下次数" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: formatCount(totals?.press_count || 0) }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "平均时长" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: formatMetric("duration_avg_ms", totals?.duration_avg_ms || 0) }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "手指" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: key.finger_name || "-" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "所在行" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: key.row_name || "-" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "在当前布局中" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: key.in_layout ? "是" : "否" })
					]
				}),
				byApp.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "key-app-split",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "text-sm muted",
						children: "主要来自这些应用"
					}), byApp.slice(0, 8).map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
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
					}, item.app_id))]
				}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "card__hint",
					children: "这个键没有按应用拆分的数据"
				})
			]
		})
	});
}
//#endregion
export { View, needs, title };
