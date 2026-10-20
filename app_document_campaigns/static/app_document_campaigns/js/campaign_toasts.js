(() => {
  if (window.campaignToast) return;
  // Thông báo dùng chung của bộ kit (static/js/ui-toast.js). Giữ API cũ campaignToast(message, level).
  window.campaignToast = (message, level = 'info') => {
    if (!message) return;
    return window.uiToast({type: window.uiToast.levelToType ? window.uiToast.levelToType(level) : level, message});
  };
})();
