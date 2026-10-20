/* F88 UI Kit — File (ô chọn tệp gọn). Dùng: <div class="ui-file" data-ui-file><input type="file" ...></div>. Xem docs/ui-kit/components/file.md */
(() => {
  'use strict';
  const ARROW = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M5 20h14"/></svg>';
  const instances = new WeakMap();
  const size = bytes => (bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1).replace('.', ',')} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);

  const init = wrapper => {
    if (instances.has(wrapper)) return;
    const input = wrapper.querySelector('input[type=file]');
    if (!input) return;
    const cfg = wrapper.dataset;
    const maxBytes = (Number(cfg.maxMb) || 0) * 1048576;
    const placeholder = cfg.placeholder || 'Chưa chọn tệp';
    const labelText = (input.labels?.[0]?.textContent || '').replace('*', '').trim();
    const el = (tag, className, attrs = {}) => { const node = document.createElement(tag); if (className) node.className = className; Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v)); return node; };

    const name = el('span', 'ui-file-name');
    const info = el('span', 'ui-file-size'); info.hidden = true;
    const clear = el('button', 'ui-file-clear', {type: 'button', 'aria-label': 'Bỏ tệp', title: 'Bỏ tệp'}); clear.textContent = '✕'; clear.hidden = true;
    const pick = el('button', 'ui-btn ui-btn-secondary ui-btn-icon ui-btn-sm ui-file-pick', {type: 'button', 'aria-label': input.multiple ? 'Chọn các tệp' : 'Chọn tệp', title: input.multiple ? 'Chọn các tệp' : 'Chọn tệp'});
    pick.innerHTML = ARROW;
    const error = el('p', 'ui-file-error', {role: 'alert'}); error.hidden = true;

    const showError = message => { error.textContent = message || ''; error.hidden = !message; wrapper.classList.toggle('is-invalid', Boolean(message)); };
    const render = () => {
      const files = [...input.files];
      wrapper.classList.toggle('has-file', files.length > 0);
      name.textContent = files.length > 1 ? `Đã chọn ${files.length} tệp` : (files[0]?.name || placeholder);
      name.title = files.map(file => file.name).join(', ');
      info.hidden = files.length !== 1; if (files.length === 1) info.textContent = size(files[0].size);
      clear.hidden = files.length === 0 || input.disabled;
      wrapper.classList.toggle('is-disabled', input.disabled);
      pick.disabled = input.disabled;
    };
    const check = () => {
      const tooBig = maxBytes && [...input.files].find(file => file.size > maxBytes);
      if (tooBig) { input.value = ''; showError(`"${tooBig.name}" vượt quá ${cfg.maxMb} MB.`); return false; }
      showError(''); return true;
    };
    const accepts = file => {
      const accept = (input.accept || '').split(',').map(part => part.trim().toLowerCase()).filter(Boolean);
      if (!accept.length) return true;
      const ext = `.${file.name.split('.').pop().toLowerCase()}`;
      return accept.some(part => part === ext || (part.endsWith('/*') && file.type.startsWith(part.slice(0, -1))) || part === file.type);
    };

    pick.addEventListener('click', () => input.click());
    name.addEventListener('click', () => { if (!input.disabled) input.click(); });
    clear.addEventListener('click', () => { input.value = ''; showError(''); render(); input.dispatchEvent(new Event('change', {bubbles: true})); pick.focus(); });
    input.addEventListener('change', () => { check(); render(); });
    input.form?.addEventListener('reset', () => setTimeout(() => { showError(''); render(); }));
    input.addEventListener('invalid', event => { event.preventDefault(); showError(cfg.requiredText || 'Vui lòng chọn tệp.'); pick.focus(); });
    ['dragenter', 'dragover'].forEach(type => wrapper.addEventListener(type, event => { if (input.disabled) return; event.preventDefault(); wrapper.classList.add('is-over'); }));
    ['dragleave', 'drop'].forEach(type => wrapper.addEventListener(type, event => { event.preventDefault(); wrapper.classList.remove('is-over'); }));
    wrapper.addEventListener('drop', event => {
      if (input.disabled || !event.dataTransfer?.files.length) return;
      const files = [...event.dataTransfer.files].slice(0, input.multiple ? undefined : 1);
      const rejected = files.find(file => !accepts(file));
      if (rejected) { showError(`"${rejected.name}" không đúng định dạng (${input.accept}).`); return; }
      const transfer = new DataTransfer(); files.forEach(file => transfer.items.add(file));
      input.files = transfer.files; input.dispatchEvent(new Event('change', {bubbles: true}));
    });
    new MutationObserver(render).observe(input, {attributes: true, attributeFilter: ['disabled']});

    input.classList.add('ui-file-native'); input.tabIndex = -1; input.setAttribute('aria-hidden', 'true');
    if (labelText) pick.setAttribute('aria-label', `${pick.getAttribute('aria-label')} — ${labelText}`);
    wrapper.classList.toggle('ui-file-sm', cfg.size === 'sm');
    wrapper.append(name, info, clear, pick);
    wrapper.after(error);
    input.id && document.querySelectorAll(`label[for="${CSS.escape(input.id)}"]`).forEach(label => label.addEventListener('click', event => { event.preventDefault(); pick.focus(); }));
    instances.set(wrapper, {render});
    render();
  };

  const initAll = root => {
    if (root.matches?.('[data-ui-file]')) init(root);
    root.querySelectorAll?.('[data-ui-file]').forEach(init);
  };
  const start = () => {
    initAll(document);
    new MutationObserver(records => records.forEach(record => record.addedNodes.forEach(node => { if (node.nodeType === 1) initAll(node); })))
      .observe(document.body, {childList: true, subtree: true});
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
  window.uiFile = {init: initAll, refresh: input => instances.get(input.closest('[data-ui-file]'))?.render()};
})();
