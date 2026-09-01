// 主题引导。**普通脚本，非模块**：模块天然 defer，会在首次绘制之后才执行，
// 于是深色偏好用户会看到一帧白底。这个文件必须保持阻塞加载（07 文档 §6 与 06 文档 §14）。
//
// 只做一件事：把存好的主题与热力色写到 <html> 的 data 属性上。真正的主题切换逻辑
// 在 core/theme.js 里，两处共用同一批键名。
(function () {
  var root = document.documentElement;
  try {
    var theme = localStorage.getItem('omnisight.theme');
    if (theme === 'dark' || theme === 'light') root.dataset.theme = theme;
    var heat = localStorage.getItem('omnisight.heat');
    if (heat === 'warm') root.dataset.heat = heat;
  } catch (error) {
    // localStorage 在隐私模式下会抛。主题跟随系统即可，不值得让页面失败。
  }
})();
