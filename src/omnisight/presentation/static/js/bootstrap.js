// 施工中页面的引导脚本。
//
// 两件事在这里就定型，M3 的正式前端沿用：
//   1. 令牌从 URL 拿到后存进 sessionStorage，后续请求用 X-OmniSight-Token 头带上
//      （08 文档 §3.2b）。自定义头会触发 CORS 预检，因此任意网页拿不到 API。
//   2. 页面**不判断平台**，只读 capabilities 的布尔值与 degraded 数组
//      （07 文档 §10）。
const TOKEN_HEADER = 'X-OmniSight-Token';
const STORAGE_KEY = 'omnisight.token';

function resolveToken() {
  const root = document.getElementById('status');
  const fromPage = root?.dataset.token || '';
  if (fromPage) {
    sessionStorage.setItem(STORAGE_KEY, fromPage);
    // 把令牌从地址栏抹掉，避免它进入浏览器历史或被截图带走。
    history.replaceState(null, '', window.location.pathname);
    return fromPage;
  }
  return sessionStorage.getItem(STORAGE_KEY) || '';
}

async function fetchStatus(token) {
  const response = await fetch('/api/v1/status', { headers: { [TOKEN_HEADER]: token } });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.message || `HTTP ${response.status}`);
  }
  return response.json();
}

function renderRows(target, rows) {
  target.replaceChildren();
  for (const [label, value] of rows) {
    const dt = document.createElement('dt');
    dt.textContent = label;
    const dd = document.createElement('dd');
    dd.textContent = value;
    target.append(dt, dd);
  }
}

function renderDegraded(notices) {
  const card = document.getElementById('degraded-card');
  const list = document.getElementById('degraded');
  if (!notices.length) {
    card.hidden = true;
    return;
  }
  list.replaceChildren();
  for (const notice of notices) {
    const item = document.createElement('li');
    const title = document.createElement('strong');
    title.textContent = notice.title;
    item.append(title, document.createTextNode(notice.detail));
    if (notice.hint) {
      const hint = document.createElement('div');
      hint.textContent = notice.hint;
      item.append(hint);
    }
    list.append(item);
  }
  card.hidden = false;
}

async function main() {
  const target = document.getElementById('status');
  const token = resolveToken();
  if (!token) {
    renderRows(target, [['无法访问', '缺少访问令牌，请从托盘菜单重新打开仪表盘']]);
    return;
  }
  try {
    const status = await fetchStatus(token);
    renderRows(target, [
      ['运行环境', `${status.platform.id} · ${status.platform.os_version} · 支持级别 ${status.platform.tier}`],
      ['端口', String(status.port)],
      ['数据库', status.database.path],
      ['schema 版本', String(status.database.schema_version)],
      ['键盘采集', status.capabilities.keyboard ? '已启用' : '未启用'],
      ['应用归因', status.capabilities.foreground ? '可用' : '不可用'],
    ]);
    renderDegraded(status.degraded || []);
  } catch (error) {
    renderRows(target, [['读取状态失败', error.message]]);
  }
}

main();
