/* F88 UI Kit — Toast (thông báo). Xem docs/ui-kit/components/toast.md
   Dùng: uiToast({type, title, message, time, icon, action, progress, ring, meta, duration}) hoặc uiToast.success('Đã lưu'). */
(() => {
  'use strict';
  if (window.uiToast && window.uiToast.__ready) return;
  const queued = window.__uiToastQ || [];

  const TYPES = ['success', 'error', 'warning', 'info', 'neutral', 'accent'];
  const TITLES = {success: 'Thành công', error: 'Không thể hoàn tất', warning: 'Cần kiểm tra', info: 'Thông báo', neutral: 'Thông báo', accent: 'Thông báo'};
  const ICONS = {
    success: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    error: '<path d="M6 6l12 12M18 6 6 18"/>',
    warning: '<path d="M12 4 2.8 19.5h18.4L12 4Z"/><path d="M12 10v4.5M12 17.6v.1"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.8v.1"/>',
    file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z"/><path d="M14 3v5h5M12 12v5M9.5 14.5h5"/>',
    download: '<path d="M12 4v11m0 0-4-4m4 4 4-4M5 19h14"/>',
    upload: '<path d="M12 16V5m0 0L8 9m4-4 4 4M5 19h14"/>',
    calendar: '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3.5 7 8.5 6 8.5-6"/>',
    package: '<path d="M12 3 4 7v10l8 4 8-4V7l-8-4Z"/><path d="m4 7 8 4 8-4M12 11v10"/>',
    bell: '<path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15L6 16Z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    link: '<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1 1"/><path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1-1"/>',
    copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    edit: '<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4Z"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  };
  const svg = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ICONS.info}</svg>`;

  let host;
  const getHost = () => {
    if (host && host.isConnected) return host;
    host = document.getElementById('ui-toasts') || document.createElement('div');
    host.id = 'ui-toasts'; host.className = 'ui-toasts';
    host.setAttribute('role', 'region'); host.setAttribute('aria-label', 'Thông báo');
    if (HTMLElement.prototype.hasOwnProperty('popover')) host.setAttribute('popover', 'manual');
    // Cuối <body> và ở top layer để nổi trên cả <dialog> / modal đang mở.
    document.body.append(host);
    return host;
  };
  const showHost = () => { const h = getHost(); if (h.showPopover) { if (h.matches(':popover-open')) h.hidePopover(); h.showPopover(); } };
  const maybeHideHost = () => { const h = getHost(); if (!h.children.length && h.hidePopover && h.matches(':popover-open')) h.hidePopover(); };

  const el = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text != null) node.textContent = text; return node; };
  const clampPercent = value => Math.max(0, Math.min(100, Math.round(Number(value) || 0)));

  const create = (input = {}) => {
    if (typeof input === 'string') input = {message: input};
    const state = {};
    const node = el('article', 'ui-toast');
    const iconBox = el('span', 'ui-toast-icon'); iconBox.setAttribute('aria-hidden', 'true');
    const main = el('div', 'ui-toast-main');
    const head = el('div', 'ui-toast-head');
    const title = el('h2', 'ui-toast-title');
    const side = el('div', 'ui-toast-side');
    const time = el('span', 'ui-toast-time');
    const close = el('button', 'ui-toast-close', '×'); close.type = 'button'; close.setAttribute('aria-label', 'Đóng thông báo');
    side.append(time, close); head.append(title, side);
    const text = el('p', 'ui-toast-text');
    const extras = el('div', 'ui-toast-extras');
    main.append(head, text, extras);
    node.append(iconBox, main);

    let timer, remaining = 0, startedAt = 0, dismissed = false, paused = false;
    const arm = () => {
      clearTimeout(timer);
      if (dismissed || paused || !remaining) return;
      startedAt = Date.now(); timer = setTimeout(dismiss, remaining);
    };
    const dismiss = () => {
      if (dismissed) return; dismissed = true; clearTimeout(timer);
      node.classList.add('is-leaving');
      const done = () => { node.remove(); maybeHideHost(); };
      node.addEventListener('animationend', done, {once: true}); setTimeout(done, 300);
    };
    node.addEventListener('pointerenter', () => { paused = true; if (timer) { clearTimeout(timer); remaining = Math.max(1200, remaining - (Date.now() - startedAt)); } });
    node.addEventListener('pointerleave', () => { paused = false; arm(); });
    node.addEventListener('focusin', () => { paused = true; clearTimeout(timer); });
    node.addEventListener('focusout', () => { paused = false; arm(); });
    close.addEventListener('click', dismiss);

    const render = () => {
      const type = TYPES.includes(state.type) ? state.type : 'info';
      node.dataset.type = type;
      node.setAttribute('role', type === 'error' || type === 'warning' ? 'alert' : 'status');
      iconBox.innerHTML = svg(state.icon || (type === 'neutral' || type === 'accent' ? 'bell' : type));
      title.textContent = state.title || TITLES[type];
      text.textContent = state.message || '';
      time.textContent = state.time === false ? '' : (state.time || 'Vừa xong');
      time.hidden = state.time === false;
      extras.replaceChildren();
      node.querySelector('.ui-toast-ring')?.remove();
      node.classList.toggle('has-ring', state.ring != null);
      if (state.action && state.action.label) {
        const a = state.action;
        const control = a.href ? el('a', 'ui-toast-action') : el('button', 'ui-toast-action');
        if (a.href) { control.href = a.href; if (a.download != null) control.setAttribute('download', a.download === true ? '' : a.download); if (a.target) { control.target = a.target; control.rel = 'noopener'; } }
        else control.type = 'button';
        control.append(el('span', '', a.label));
        if (a.icon) control.insertAdjacentHTML('beforeend', svg(a.icon));
        control.addEventListener('click', event => {
          if (typeof a.onClick === 'function') a.onClick(event, api);
          if (a.dismiss !== false && (!a.href || a.download != null)) dismiss();
        });
        extras.append(control);
      }
      if (state.progress != null) {
        const percent = clampPercent(state.progress);
        const bar = el('div', 'ui-toast-bar'); bar.setAttribute('role', 'progressbar');
        bar.setAttribute('aria-valuemin', '0'); bar.setAttribute('aria-valuemax', '100'); bar.setAttribute('aria-valuenow', String(percent));
        bar.style.setProperty('--ui-toast-progress', `${percent}%`);
        bar.append(document.createElement('i')); extras.append(bar);
      }
      if (Array.isArray(state.meta) && state.meta.length) {
        const row = el('div', 'ui-toast-meta');
        state.meta.forEach(item => {
          const entry = typeof item === 'string' ? {text: item} : item;
          const cell = el('span'); if (entry.icon) cell.insertAdjacentHTML('beforeend', svg(entry.icon));
          cell.append(document.createTextNode(entry.text || '')); row.append(cell);
        });
        extras.append(row);
      }
      if (state.ring != null) {
        const percent = clampPercent(state.ring);
        const ring = el('div', 'ui-toast-ring'); ring.style.setProperty('--p', percent);
        ring.setAttribute('role', 'progressbar'); ring.setAttribute('aria-valuenow', String(percent));
        ring.append(el('span', '', `${percent}%`)); node.append(ring);
      }
    };
    const resolveDuration = () => {
      if (state.duration != null) return Number(state.duration) || 0;
      if (state.progress != null && clampPercent(state.progress) < 100) return 0;
      if (state.ring != null && clampPercent(state.ring) < 100) return 0;
      return state.type === 'error' ? 9000 : state.type === 'warning' ? 8000 : 6000;
    };
    const api = {
      element: node,
      dismiss,
      update(patch = {}) {
        if (dismissed) return api;
        Object.assign(state, patch); render();
        if (!('duration' in patch) && patch.progress == null && patch.ring == null && !patch.type && !patch.message && !patch.title) return api;
        remaining = resolveDuration(); paused = node.matches(':hover'); arm();
        return api;
      },
    };
    Object.assign(state, input);
    render();
    // Giữ tối đa 4 thông báo; bỏ cái cũ nhất.
    if (state.container) {
      // Hiển thị tại chỗ (demo / tài liệu): không dùng hộp nổi, không tự đóng.
      state.container.append(node); remaining = 0;
    } else {
      const h = getHost();
      while (h.children.length >= 4) h.lastElementChild.remove();
      h.prepend(node); showHost();
      remaining = resolveDuration(); arm();
    }
    return api;
  };

  const uiToast = (input, extra) => (typeof input === 'string' ? create({message: input, ...(extra || {})}) : create(input));
  TYPES.forEach(type => { uiToast[type] = (message, options) => create({...(options || {}), type, message}); });
  uiToast.__ready = true;
  uiToast.levelToType = level => {
    const tokens = String(level || '').toLowerCase().split(/\s+/);
    return ['error', 'danger', 'warning', 'success', 'info'].map(name => [name, tokens.includes(name)]).filter(([, hit]) => hit).map(([name]) => (name === 'danger' ? 'error' : name))[0] || 'info';
  };
  uiToast.seeds = (root = document) => {
    root.querySelectorAll('[data-ui-toast-seed]').forEach(seed => {
      const message = seed.textContent.trim();
      if (message) create({type: uiToast.levelToType(seed.dataset.level), title: seed.dataset.title || undefined, message});
      seed.remove();
    });
    root.querySelectorAll('[data-ui-toast-seeds]').forEach(box => { if (!box.children.length) box.remove(); });
  };
  window.uiToast = uiToast;
  window.__uiToastQ = [];
  queued.forEach(args => { try { uiToast(...args); } catch (error) { console.error(error); } });

  const start = () => uiToast.seeds();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once: true}); else start();
})();
