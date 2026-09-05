import { F as get, K as require_react, L as messageOf, U as Icon, W as require_jsx_runtime, k as fail, z as post } from "./degraded-qMnijys5.js";
import { c as Drawer, l as closeOverlay, u as openOverlay } from "./shell-8ge_e5M8.js";
//#region frontend/src/components/ImportWizard.tsx
var import_react = require_react();
var import_jsx_runtime = require_jsx_runtime();
var DISMISS_KEY = "omnisight.importDismissed";
var PHASE_LABELS = {
	tl_sessions: "导入 TimeLens 应用使用记录",
	tl_keys: "导入 TimeLens 按键统计",
	kt_raw: "导入 KeyTrace 按键明细",
	finalize: "收尾"
};
function openImportWizard() {
	openOverlay(/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Drawer, {
		title: "导入旧版数据",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ImportWizard, {})
	}));
}
/**
* 首页横幅：检测到旧库且从未导入/关闭过时显示（09 文档 §2.1，可关闭）。
*
* 检测不阻塞启动，所以它自己在挂载后异步问一次；失败一律安静跳过。
*/
function ImportBanner() {
	const [visible, setVisible] = (0, import_react.useState)(false);
	(0, import_react.useEffect)(() => {
		if (localStorage.getItem(DISMISS_KEY) === "1") return;
		let cancelled = false;
		(async () => {
			try {
				const status = await get("/import/progress");
				if (cancelled) return;
				if (status && status.state === "idle" && status.available) setVisible(true);
			} catch {}
		})();
		return () => {
			cancelled = true;
		};
	}, []);
	if (!visible) return null;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "banner banner--info",
		role: "status",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "banner__body",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("strong", { children: "发现旧版数据" }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "banner__detail",
				children: "检测到 TimeLens / KeyTrace 的历史数据库，可以导入到 OmniSight。"
			})]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "banner__actions",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
				className: "button button--primary",
				type: "button",
				onClick: () => {
					setVisible(false);
					openImportWizard();
				},
				children: "导入旧数据"
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
				className: "icon-button",
				type: "button",
				"aria-label": "关闭提醒",
				onClick: () => {
					localStorage.setItem(DISMISS_KEY, "1");
					setVisible(false);
				},
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, { name: "close" })
			})]
		})]
	});
}
function ImportWizard() {
	const [step, setStep] = (0, import_react.useState)(1);
	const [detected, setDetected] = (0, import_react.useState)([]);
	const [selected, setSelected] = (0, import_react.useState)({
		timelens: null,
		keytrace: null
	});
	const [preview, setPreview] = (0, import_react.useState)(null);
	const [status, setStatus] = (0, import_react.useState)(null);
	const [report, setReport] = (0, import_react.useState)(null);
	const timer = (0, import_react.useRef)(0);
	(0, import_react.useEffect)(() => () => window.clearInterval(timer.current), []);
	(0, import_react.useEffect)(() => {
		(async () => {
			try {
				const list = (await get("/import/detect"))?.detected || [];
				setDetected(list);
				setSelected((current) => {
					const next = { ...current };
					for (const item of list) {
						const kind = item.kind;
						next[kind] = next[kind] || item.path;
					}
					return next;
				});
			} catch {
				setDetected([]);
			}
		})();
	}, []);
	const toStep2 = async () => {
		if (!selected.timelens && !selected.keytrace) {
			fail("至少要选择一个旧数据库");
			return;
		}
		try {
			setPreview(await post("/import/preview", { sources: selected }));
			setStep(2);
		} catch (error) {
			fail(messageOf(error, "扫描旧数据库失败"));
		}
	};
	const poll = async () => {
		let next = null;
		try {
			next = await get("/import/progress");
		} catch {
			return;
		}
		if (!next) return;
		setStatus(next);
		if (!next.busy && next.state === "done") {
			window.clearInterval(timer.current);
			timer.current = 0;
			try {
				setReport(await get("/import/report"));
			} catch {
				setReport(null);
			}
			setStep(4);
		} else if (!next.busy && next.error) {
			window.clearInterval(timer.current);
			timer.current = 0;
			fail(next.error);
		}
	};
	const start = async () => {
		try {
			setStatus(await post("/import/start", {
				sources: selected,
				losses: preview?.losses || []
			}));
			setStep(3);
		} catch (error) {
			fail(messageOf(error, "启动导入失败"));
			return;
		}
		window.clearInterval(timer.current);
		timer.current = window.setInterval(poll, 1200);
	};
	const pause = async () => {
		try {
			setStatus(await post("/import/cancel"));
		} catch (error) {
			fail(messageOf(error, "暂停失败"));
		}
	};
	const undo = async () => {
		try {
			await post("/import/undo");
			fail("撤销已开始，历史数据将在后台清除");
		} catch (error) {
			fail(messageOf(error, "撤销失败"));
			return;
		}
		closeOverlay();
	};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "import-wizard",
		children: [
			step === 1 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Step1, {
				detected,
				selected,
				onChange: setSelected
			}) : null,
			step === 2 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Step2, { preview }) : null,
			step === 3 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Step3, { status }) : null,
			step === 4 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Step4, { report }) : null
		]
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "import-wizard__foot",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Footer, {
			step,
			paused: status?.state === "paused",
			onNext: toStep2,
			onBack: () => setStep((value) => value - 1),
			onStart: start,
			onPause: pause,
			onUndo: undo
		})
	})] });
}
function StepHeading({ step, title }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("h3", {
		className: "import-wizard__title",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
			className: "import-wizard__step",
			children: [
				"步骤 ",
				step,
				"/4"
			]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [" · ", title] })]
	});
}
/** 步骤 1/4：发现的数据。 */
function Step1({ detected, selected, onChange }) {
	const toggle = (kind, path, checked) => onChange({
		...selected,
		[kind]: checked ? path : null
	});
	const setManual = (kind, value) => onChange({
		...selected,
		[kind]: value.trim() || null
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StepHeading, {
			step: 1,
			title: "发现的数据"
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
			className: "import-sources",
			children: detected.length ? detected.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", {
				className: "import-source",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
					className: "import-source__main",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
						type: "checkbox",
						checked: selected[item.kind] === item.path,
						onChange: (event) => toggle(item.kind, item.path, event.target.checked)
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("strong", { children: item.kind === "timelens" ? "TimeLens" : "KeyTrace" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "import-source__path",
							children: item.path
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
							className: "import-source__meta",
							children: [
								(item.size_bytes / 1048576).toFixed(1),
								" MB · 修改于 ",
								item.mtime
							]
						})
					] })]
				})
			}, item.path)) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "muted",
				children: "默认位置没有找到旧数据库。请在下面输入旧库文件的完整路径。"
			})
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("details", {
			className: "import-manual",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("summary", { children: "选择其他位置…" }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ManualField, {
					kind: "timelens",
					value: selected.timelens,
					placeholder: "TimeLens usage.db 路径",
					onChange: setManual
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ManualField, {
					kind: "keytrace",
					value: selected.keytrace,
					placeholder: "KeyTrace keytrace.sqlite3 路径",
					onChange: setManual
				})
			]
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
			className: "field__note",
			children: "旧库在整个过程中只读，不会被修改；导入前会自动备份到数据目录的 backup/ 下。"
		})
	] });
}
function ManualField({ kind, value, placeholder, onChange }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
		className: "field",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: "field__label",
			children: kind === "timelens" ? "TimeLens 数据库" : "KeyTrace 数据库"
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
			className: "input",
			type: "text",
			value: value || "",
			placeholder,
			spellCheck: false,
			onChange: (event) => onChange(kind, event.target.value)
		})]
	});
}
/** 步骤 2/4：将会丢失什么——整个向导的重点（09 文档 §2.2）。 */
function Step2({ preview }) {
	const tl = preview?.timelens;
	const kt = preview?.keytrace;
	const losses = preview?.losses || [];
	const conflicts = preview?.conflict_days || [];
	const stats = [];
	if (tl?.sessions) stats.push(`应用使用记录 ${tl.sessions.rows} 条（${tl.sessions.date_min} 起）`);
	if (tl?.key_usage) stats.push(`按键统计 ${tl.key_usage.presses} 次（仅次数，无时长与归因）`);
	if (kt?.raw) stats.push(`按键明细 ${kt.raw.rows} 条`);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StepHeading, {
			step: 2,
			title: "将会丢失什么"
		}),
		stats.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", { children: ["将导入：", stats.join("；")] }) : null,
		losses.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
			className: "import-losses",
			children: losses.map((loss) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "import-losses__mark",
				children: "⚠"
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: loss })] }, loss))
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
			className: "muted",
			children: "没有发现数据损失。"
		}),
		conflicts.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
			className: "field__note",
			children: [
				"重叠日期以 KeyTrace 为准：",
				conflicts.length,
				" 天将跳过 TimeLens 的按键计数。"
			]
		}) : null,
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
			className: "field__note",
			children: "从今天起记录的新数据不受任何影响。"
		})
	] });
}
/** 步骤 3/4：正在导入。 */
function Step3({ status }) {
	const counts = status?.counts;
	const phase = PHASE_LABELS[status?.phase || ""] || status?.phase || "";
	const paused = status?.state === "paused";
	const parts = [];
	if (counts?.sessions_imported) parts.push(`使用记录 ${counts.sessions_imported} 条`);
	if (counts?.key_presses) parts.push(`按键次数 ${counts.key_presses}`);
	if (counts?.raw_imported) parts.push(`按键明细 ${counts.raw_imported} 条`);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StepHeading, {
			step: 3,
			title: paused ? "已暂停" : "正在导入"
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "import-progress",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "import-progress__bar",
					role: "progressbar",
					children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "import-progress__fill" })
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { children: phase }),
				parts.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "import-progress__counts",
					children: parts.join(" · ")
				}) : null,
				paused ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "field__note",
					children: "导入已暂停，点击\"继续\"从断点恢复。"
				}) : null
			]
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
			className: "field__note",
			children: "可以关闭此窗口，导入在后台继续；中断后再次导入会从断点续传，不会产生重复。"
		})
	] });
}
/** 步骤 4/4：完成报告。 */
function Step4({ report }) {
	const sessions = report?.sessions;
	const raw = report?.raw_events;
	const usage = report?.key_usage;
	const unmapped = report?.unmapped_keys || {};
	const unmappedKeys = Object.keys(unmapped);
	const rows = [
		[
			"应用使用记录",
			`${sessions?.imported || 0} 条`,
			sessions?.date_range?.[0] ? `${sessions.date_range[0]} 起` : ""
		],
		[
			"按键明细",
			`${raw?.imported || 0} 条`,
			raw?.days ? `${raw.days} 天` : ""
		],
		[
			"按键次数（无时长）",
			`${usage?.presses || 0} 次`,
			usage?.days ? `${usage.days} 天` : ""
		],
		[
			"跳过（日期重叠）",
			`${(report?.skipped_days || []).length} 天`,
			""
		],
		[
			"未能映射的键",
			unmappedKeys.length ? `${unmappedKeys.length} 个：${unmappedKeys.join("、")}` : "无",
			""
		]
	];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(StepHeading, {
			step: 4,
			title: "导入完成"
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("table", {
			className: "table import-report",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: rows.map(([name, value, note]) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", { children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { children: name }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", { children: value }),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
					className: "muted",
					children: note
				})
			] }, name)) })
		}),
		(report?.losses || []).length ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("details", {
			className: "import-losses import-losses--summary",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("summary", { children: "有损说明（导入时已知悉）" }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", { children: (report?.losses || []).map((loss) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("li", { children: loss }, loss)) })]
		}) : null,
		/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
			className: "field__note",
			children: [
				"完整报告：",
				report?.backup_dir || "数据目录",
				"/../import-report.json。旧数据文件未被修改。"
			]
		})
	] });
}
function Footer({ step, paused, onNext, onBack, onStart, onPause, onUndo }) {
	if (step === 1) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
		className: "button button--primary",
		type: "button",
		onClick: onNext,
		children: "下一步"
	});
	if (step === 2) return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "import-wizard__foot-row",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
			className: "button",
			type: "button",
			onClick: onBack,
			children: "上一步"
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
			className: "button button--primary",
			type: "button",
			onClick: onStart,
			children: "我知道了，开始导入"
		})]
	});
	if (step === 3) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
		className: "button",
		type: "button",
		onClick: paused ? onStart : onPause,
		children: paused ? "继续" : "暂停"
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "import-wizard__foot-row",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
				className: "button button--danger",
				type: "button",
				title: "删除导入的历史数据；新采集的数据保留",
				onClick: () => {
					if (window.confirm("撤销将删除导入的历史数据（新采集的数据保留）。确定？")) onUndo();
				},
				children: "撤销导入"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "spacer" }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
				className: "button button--primary",
				type: "button",
				onClick: () => closeOverlay(),
				children: "开始使用"
			})
		]
	});
}
//#endregion
//#region frontend/src/components/controls.tsx
/**
* 用 aria-pressed 而不是 class 表达选中态：屏幕阅读器因此不需要额外的文案。
*/
function Segmented({ items, active, onPick, small = false, variant, label = "" }) {
	const kind = variant || (small ? "sm" : null);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: kind ? `segmented segmented--${kind}` : "segmented",
		role: "group",
		"aria-label": label,
		children: items.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
			className: "segmented__item",
			type: "button",
			"aria-pressed": item.id === active,
			title: item.title || item.name,
			onClick: () => onPick(item.id),
			children: item.name
		}, item.id))
	});
}
/** 单个可切换胶囊（分类过滤用）。 */
function Chip({ item, active, onPick }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
		className: "chip",
		type: "button",
		"aria-pressed": active,
		onClick: () => onPick(item.id),
		children: item.name
	});
}
/**
* 搜索框。**去抖 220ms**：每敲一个字母就发一次请求会让 300 个应用的库明显卡顿。
*
* 输入值是受控的本地 state，而向上抛出的是去抖后的值——这样打字不卡，而请求不多。
*/
function SearchBox({ placeholder = "搜索", value = "", onInput }) {
	const [text, setText] = (0, import_react.useState)(value);
	const timer = (0, import_react.useRef)(0);
	const handler = (0, import_react.useRef)(onInput);
	handler.current = onInput;
	(0, import_react.useEffect)(() => {
		window.clearTimeout(timer.current);
		timer.current = window.setTimeout(() => handler.current(text.trim()), 220);
		return () => window.clearTimeout(timer.current);
	}, [text]);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
		className: "search",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: "search__mark",
			"aria-hidden": "true",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, { name: "search" })
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
			type: "search",
			value: text,
			placeholder,
			"aria-label": placeholder,
			enterKeyHint: "search",
			onChange: (event) => setText(event.target.value)
		})]
	});
}
function Checkbox({ label, checked = false, onChange }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
		className: "checkbox",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
			type: "checkbox",
			checked,
			onChange: (event) => onChange(event.target.checked)
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: label })]
	});
}
function Switch({ checked = false, disabled = false, onChange, label = "" }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
		className: "switch",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
			type: "checkbox",
			checked,
			disabled,
			"aria-label": label,
			onChange: (event) => onChange(event.target.checked)
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "switch__track" })]
	});
}
//#endregion
export { Switch as a, Segmented as i, Chip as n, ImportBanner as o, SearchBox as r, openImportWizard as s, Checkbox as t };
