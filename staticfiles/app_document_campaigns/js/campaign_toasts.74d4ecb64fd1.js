(() => {
  if (window.campaignToast) return;
  const stack = document.querySelector('[data-campaign-toasts]');
  if (!stack) return;

  window.campaignToast = (message, level = 'info') => {
    if (!message) return;
    const toast = document.createElement('div');
    toast.className = 'campaign-toast';
    toast.dataset.level = ['success', 'error', 'warning', 'info'].includes(level) ? level : 'info';
    toast.setAttribute('role', level === 'error' ? 'alert' : 'status');
    const text = document.createElement('span');
    text.className = 'campaign-toast-message';
    text.textContent = message;
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'campaign-toast-close';
    close.textContent = '×';
    close.setAttribute('aria-label', 'Đóng thông báo');
    let dismissed = false;
    let timer;
    const dismiss = () => {
      if (dismissed) return;
      dismissed = true;
      clearTimeout(timer);
      toast.classList.remove('is-visible');
      toast.classList.add('is-leaving');
      window.setTimeout(() => toast.remove(), 300);
    };
    close.addEventListener('click', dismiss);
    toast.append(text, close);
    stack.prepend(toast);
    requestAnimationFrame(() => { if (!dismissed) toast.classList.add('is-visible'); });
    timer = window.setTimeout(dismiss, 7000);
    return dismiss;
  };

  document.querySelectorAll('[data-toast-seeds] [data-toast-level]').forEach((seed) => {
    window.campaignToast(seed.textContent, seed.dataset.toastLevel);
  });
})();
