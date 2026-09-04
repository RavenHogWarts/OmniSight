import { A as formatPercent, B as capabilityOf, G as setState, H as useResource, J as require_react_dom, P as assetUrl, T as formatCount, U as useSlice, V as noticeFor, W as getState, Y as require_react, a as FILTERS_SLOT_ID, h as periodParams, i as show, j as initialOf, k as formatDurationShort, m as gapSet, n as fetchInto, q as require_jsx_runtime, r as hide, w as formatClock } from "./main-DA_wrxiB.js";
import { n as EmptyState, o as SkeletonRows, r as ErrorState, s as Card, t as CapabilityNotice } from "./states-DZ-0dhHV.js";
import { a as Chart, i as showChartTooltip, n as drawPanelPair, o as hatchPattern, r as hideChartTooltip, s as niceMax, t as describePanelPair } from "./panel-pair-ZeqsPmhE.js";
//#region frontend/src/charts/stacked-bar.ts
var import_react_dom = require_react_dom();
var PAD = {
	top: 8,
	right: 8,
	bottom: 16,
	left: 44
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
	ctx.font = "10px sans-serif";
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
	ctx.fillStyle = palette.faint;
	ctx.textAlign = "center";
	ctx.textBaseline = "top";
	const stride = Math.max(1, Math.ceil(buckets.length / Math.max(2, Math.floor(plot.w / 44))));
	buckets.forEach((item, index) => {
		if (index % stride) return;
		ctx.fillText(String(item.label ?? ""), plot.x + slot * (index + .5), plot.y + plot.h + 4);
	});
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
//#region frontend/src/components/HourBand.tsx
var import_react = require_react();
var import_jsx_runtime = require_jsx_runtime();
/** 一个图标槽的宽度（图标 26px + 间距 8px），与 hour-band.css 里的值一致。 */
var ICON_SLOT = 34;
/** `+N` 那一格预留的宽度。 */
var MORE_SLOT = 40;
/** 还没量到宽度时的容量（面板隐藏、或 ResizeObserver 第一次回调之前）。 */
var CAPACITY_FALLBACK = 8;
var HOURS = Array.from({ length: 24 }, (_unused, hour) => hour);
function num(value) {
	return Number(value) || 0;
}
function HourBand({ hours, gap = false }) {
	const root = (0, import_react.useRef)(null);
	const [capacity, setCapacity] = (0, import_react.useState)(CAPACITY_FALLBACK);
	(0, import_react.useEffect)(() => {
		const node = root.current;
		if (!node) return;
		const measure = () => {
			const width = Math.max(0, (node.clientWidth || 0) - 60);
			setCapacity(width ? Math.max(1, Math.floor((width - MORE_SLOT) / ICON_SLOT)) : CAPACITY_FALLBACK);
		};
		measure();
		const observer = new ResizeObserver(measure);
		observer.observe(node);
		return () => observer.disconnect();
	}, []);
	(0, import_react.useEffect)(() => () => hide(), []);
	if (gap) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "hour-band",
		ref: root,
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "hour-band__gap",
			children: "该时段没有采集记录（不是 0）"
		})
	});
	const byHour = new Map((hours || []).map((item) => [item.hour, item]));
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "hour-band",
		ref: root,
		onPointerLeave: () => hide(),
		children: HOURS.map((hour) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(HourRow, {
			item: byHour.get(hour) || {
				hour,
				total_seconds: 0,
				apps: [],
				other_seconds: 0
			},
			capacity
		}, hour))
	});
}
function HourRow({ item, capacity }) {
	const list = [...item.apps || []].sort((left, right) => num(right.seconds) - num(left.seconds));
	const visible = list.slice(0, capacity);
	const hiddenCount = Math.max(0, list.length - visible.length);
	const otherSeconds = num(item.other_seconds);
	const moreCount = hiddenCount + (otherSeconds > 0 ? 1 : 0);
	const moreSeconds = list.slice(capacity).reduce((sum, app) => sum + num(app.seconds), 0) + otherSeconds;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "hour-band__row",
		"data-empty": String(!(num(item.total_seconds) > 0)),
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
			className: "hour-band__hour numeric",
			children: [String(item.hour).padStart(2, "0"), ":00"]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "hour-band__apps",
			children: [visible.map((app) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(IconCell, {
				app,
				hour: item.hour
			}, app.app_id)), moreCount ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
				className: "hour-band__more",
				onPointerEnter: (event) => show({
					title: `另外 ${moreCount} 个应用`,
					rows: [["时长", formatDurationShort(moreSeconds)]],
					x: event.clientX,
					y: event.clientY
				}),
				children: ["+", moreCount]
			}) : null]
		})]
	});
}
/** 图标取不到就是首字母块——`icons` 能力缺失的机器上这是常态，不是异常。 */
function IconCell({ app, hour }) {
	const [broken, setBroken] = (0, import_react.useState)(false);
	const label = app.display_name || `应用 ${app.app_id}`;
	const duration = formatDurationShort(num(app.seconds));
	const url = app.icon_url ? assetUrl(app.icon_url) : "";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
		className: "hour-band__app",
		"data-app-id": app.app_id,
		"aria-label": `${String(hour).padStart(2, "0")}:00 ${label} ${duration}`,
		onPointerEnter: (event) => show({
			title: label,
			rows: [["时长", duration], ["占这一小时", formatPercent(num(app.percent))]],
			x: event.clientX,
			y: event.clientY
		}),
		children: !url || broken ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: "hour-band__initial",
			children: initialOf(label)
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("img", {
			className: "hour-band__icon",
			src: url,
			alt: "",
			loading: "lazy",
			decoding: "async",
			onError: () => setBroken(true)
		})
	});
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
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
			title: "键位与应用",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(KeySplit, {})
		}),
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
	const period = payload.period;
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
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
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
		}),
		gaps.size ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "card__hint",
			children: [gaps.size, " 天无应用归因，这些天的时长未计入各小时"]
		}) : null,
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "text-sm muted",
			children: "这些小时里用的是哪些应用"
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(HourBand, {
			hours,
			gap: (period?.days || 0) <= 1 && gaps.has(period?.start || "")
		})
	] });
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
* 选择器 portal 到周期栏：它改的是请求参数（14 文档 §4.1）。
*/
function KeySplit() {
	const selectedKeyId = useSlice("selectedKeyId");
	const heatmap = useResource("insightHeatmap");
	const detail = useResource("insightKey");
	const slot = document.getElementById(FILTERS_SLOT_ID);
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
	const selector = slot && choices.length ? (0, import_react_dom.createPortal)(/* @__PURE__ */ (0, import_jsx_runtime.jsx)("select", {
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
	}), slot) : null;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [selector, /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "key-app-split",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(KeyAppRows, {
			payload: detail.data,
			loading: detail.loading
		})
	})] });
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
