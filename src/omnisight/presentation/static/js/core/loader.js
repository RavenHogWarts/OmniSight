// 视图级取数编排（07 文档 §5.2）。
//
// 与现状最重要的差别：**慢的那个接口不阻塞快的那个渲染**。TimeLens 用 Promise.all 等齐
// 才渲染，一个慢请求拖累整页；这里每个 key 独立进入 ready，组件各自订阅自己的 key。
//
// 第二个差别：切周期时 abort 掉上一批请求。连点日期箭头时旧响应会晚于新响应到达，
// 现状因此会闪一下错的数据——那种 bug 在本机上很难重现，但用户每天都会碰到。
//
// 类型（07 文档 §2.1）：**这里是整个前端唯一把未校验 JSON 认作声明形状的地方**。
// `fetchInto` 按 `DataMap` 把 key 映射到响应类型，视图因此不必在每个使用点断言。
// 那一次断言不是凭空的：tests/integration/test_frontend_contract.py 拿真实端点的
// 响应逐层核对 types/api.d.ts，字段改名或消失都会红。
import { ApiError, get } from './api.js';
import { setEntry, setState } from './store.js';

/**
 * @typedef {import('../types/api.js').DataMap} DataMap
 * @typedef {import('../types/api.js').DataRequest} DataRequest
 * @typedef {import('../types/api.js').RequestFailure} RequestFailure
 */

let controller = new AbortController();

/** 周期/范围变了：上一批请求的结果已经没人要了。 */
export function abortPending() {
  controller.abort();
  controller = new AbortController();
}

/**
 * 取一段数据并写进 store。
 * `key` 是组件订阅的名字（`overview`、`heatmap`…），与路径无关，便于同一路径不同参数并存。
 * @template {keyof DataMap} K
 * @param {K} key
 * @param {string} path
 * @param {Record<string, string | number | boolean | null | undefined>} [params]
 * @param {{ maxAge?: number }} [options]
 * @returns {Promise<DataMap[K] | null>}
 */
export async function fetchInto(key, path, params = {}, { maxAge = 0 } = {}) {
  setEntry('loading', key, true);
  const signal = controller.signal;
  try {
    const payload = /** @type {DataMap[K] | null} */ (await get(path, params, { signal, maxAge }));
    if (signal.aborted) return null;
    setEntry('errors', key, null);
    setEntry('data', key, payload);
    // period 与 coverage 是公共外壳的一部分：谁先拿到谁更新，内容一致（同一次请求批）。
    // 用 `in` 而不是直接取：`/keyboard/layout` 那类端点的外壳里根本没有这两个字段
    // （见 types/api.d.ts 的三层 Envelope），直接取在类型上就是错的。
    if (payload && 'period' in payload && payload.period) setState('periodMeta', payload.period);
    if (payload && 'coverage' in payload && payload.coverage) setState('coverage', payload.coverage);
    return payload;
  } catch (/** @type {any} */ error) {
    if (error?.name === 'AbortError' || signal.aborted) return null;
    setEntry('errors', key, describe(error));
    setEntry('data', key, null);
    return null;
  } finally {
    if (!signal.aborted) setEntry('loading', key, false);
  }
}

/**
 * @param {unknown} error
 * @returns {RequestFailure}
 */
function describe(error) {
  if (error instanceof ApiError) {
    return { message: error.message, code: error.code, status: error.status, field: error.field };
  }
  // 网络层失败（进程退出、端口换了）：给出可操作的说法，而不是 TypeError。
  return { message: '无法连接到本机服务，采集进程可能已退出', code: 'network_error', status: 0 };
}

/**
 * 并发发起一组请求，各自独立落地。返回全部完成的 Promise，供首屏埋点用。
 * @param {readonly DataRequest[]} requests
 */
export function fetchAll(requests) {
  return Promise.all(requests.map(({ key, path, params, options }) => fetchInto(key, path, params, options)));
}
