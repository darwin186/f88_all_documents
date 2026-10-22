/* F88 UI Kit — Upload (vùng kéo thả + danh sách tệp, tuỳ chọn chụp ảnh). Dùng: <div class="ui-upload" data-ui-upload><input type="file" multiple name="..."></div>. Xem docs/ui-kit/components/upload.md */
(() => {
  'use strict';
  const ICONS = {
    up: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M5 20h14"/></svg>',
    camera: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 8h3l1.5-2h7L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z"/><circle cx="12" cy="13" r="3.5"/></svg>',
  };
  const instances = new WeakMap();
  const size = bytes => (bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1).replace('.', ',')} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);
  const el = (tag, className, attrs = {}) => { const node = document.createElement(tag); if (className) node.className = className; Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v)); return node; };
  const extOf = name => (name.includes('.') ? name.split('.').pop() : '').toUpperCase().slice(0, 4) || 'FILE';
  const keyOf = file => `${file.name}|${file.size}|${file.lastModified}`;

  const init = wrapper => {
    if (instances.has(wrapper)) return;
    const input = wrapper.querySelector('input[type=file]');
    if (!input) return;
    const cfg = wrapper.dataset;
    const maxFiles = Number(cfg.maxFiles) || (input.multiple ? 0 : 1);
    const maxBytes = (Number(cfg.maxMb) || 0) * 1048576;
    const accept = (input.accept || '').split(',').map(part => part.trim().toLowerCase()).filter(Boolean);
    const accepts = file => {
      if (!accept.length) return true;
      const ext = `.${file.name.split('.').pop().toLowerCase()}`;
      return accept.some(part => part === ext || (part.endsWith('/*') && file.type.startsWith(part.slice(0, -1))) || part === file.type);
    };
    const hasCamera = 'camera' in cfg;
    let files = [];
    const previews = new Map();

    // Hai ô chọn tạm (không có name nên không bị gửi đi); ô gốc `input` giữ danh sách cuối cùng
    const picker = el('input', 'ui-upload-native', {type: 'file', tabindex: '-1', 'aria-hidden': 'true'});
    picker.multiple = maxFiles !== 1; if (input.accept) picker.accept = input.accept;
    const camera = el('input', 'ui-upload-native', {type: 'file', accept: 'image/*', capture: 'environment', tabindex: '-1', 'aria-hidden': 'true'});
    camera.multiple = maxFiles !== 1;

    const drop = el('div', 'ui-upload-drop', {role: 'button', tabindex: '0'});
    const icon = el('span', 'ui-upload-icon', {'aria-hidden': 'true'}); icon.innerHTML = ICONS.up;
    const title = el('b', 'ui-upload-title');
    const pickText = el('u'); pickText.textContent = cfg.pickText || 'chọn từ máy';
    title.append(document.createTextNode(`${cfg.dropText || 'Kéo thả tệp vào đây hoặc'} `), pickText);
    const hint = el('small', 'ui-upload-hint'); hint.textContent = cfg.hint || '';
    hint.hidden = !cfg.hint;
    drop.append(icon, title, hint);
    let cameraBtn = null;
    if (hasCamera) {
      cameraBtn = el('button', 'ui-btn ui-btn-secondary ui-btn-sm ui-upload-camera', {type: 'button'});
      cameraBtn.innerHTML = ICONS.camera;
      cameraBtn.append(document.createTextNode(cfg.cameraText || 'Chụp ảnh'));
      drop.append(cameraBtn);
    }
    const list = el('ul', 'ui-upload-list'); list.hidden = true;
    const error = el('p', 'ui-upload-error', {role: 'alert'}); error.hidden = true;
    const showError = message => { error.textContent = message || ''; error.hidden = !message; wrapper.classList.toggle('is-invalid', Boolean(message)); };

    const sync = () => {
      const transfer = new DataTransfer(); files.forEach(file => transfer.items.add(file));
      input.files = transfer.files;
      input.dispatchEvent(new Event('change', {bubbles: true}));
    };
    const release = file => { const url = previews.get(file); if (url) { URL.revokeObjectURL(url); previews.delete(file); } };
    const render = () => {
      list.replaceChildren();
      files.forEach(file => {
        const li = el('li', 'ui-upload-item');
        const thumb = el('span', 'ui-upload-thumb');
        if (file.type.startsWith('image/')) {
          if (!previews.has(file)) previews.set(file, URL.createObjectURL(file));
          const img = el('img', '', {alt: '', src: previews.get(file)}); thumb.append(img); thumb.classList.add('is-image');
        } else {
          thumb.textContent = extOf(file.name); if (/^PDF$/.test(thumb.textContent)) thumb.classList.add('is-pdf');
        }
        const meta = el('div', 'ui-upload-meta');
        const name = el('b'); name.textContent = file.name; name.title = file.name;
        const info = el('span'); info.textContent = size(file.size);
        meta.append(name, info);
        const remove = el('button', 'ui-upload-remove', {type: 'button', 'aria-label': `Bỏ tệp ${file.name}`, title: 'Bỏ tệp'}); remove.textContent = '✕';
        remove.addEventListener('click', () => { files = files.filter(item => item !== file); release(file); showError(''); render(); sync(); drop.focus(); });
        li.append(thumb, meta, remove);
        list.append(li);
      });
      list.hidden = files.length === 0;
      const full = maxFiles > 0 && files.length >= maxFiles;
      wrapper.classList.toggle('is-full', full);
      wrapper.classList.toggle('has-files', files.length > 0);
      drop.setAttribute('aria-disabled', String(full || input.disabled));
      if (cameraBtn) cameraBtn.disabled = full || input.disabled;
      title.hidden = false;
      wrapper.classList.toggle('is-disabled', input.disabled);
    };
    const add = incoming => {
      if (input.disabled) return;
      const problems = [];
      let changed = false;
      for (const file of incoming) {
        if (files.some(item => keyOf(item) === keyOf(file))) continue;
        if (!accepts(file)) { problems.push(`"${file.name}" không đúng định dạng.`); continue; }
        if (maxBytes && file.size > maxBytes) { problems.push(`"${file.name}" vượt quá ${cfg.maxMb} MB.`); continue; }
        if (maxFiles && files.length >= maxFiles) {
          if (maxFiles === 1) { release(files[0]); files = []; }
          else { problems.push(`Chỉ được tải tối đa ${maxFiles} tệp.`); break; }
        }
        files.push(file); changed = true;
      }
      showError([...new Set(problems)].join(' '));
      render();
      if (changed) sync();
    };

    const openPicker = () => { if (!input.disabled && !(maxFiles > 1 && files.length >= maxFiles)) picker.click(); };
    drop.addEventListener('click', event => { if (event.target.closest('.ui-upload-camera')) return; openPicker(); });
    drop.addEventListener('keydown', event => { if ((event.key === 'Enter' || event.key === ' ') && event.target === drop) { event.preventDefault(); openPicker(); } });
    cameraBtn?.addEventListener('click', event => { event.stopPropagation(); if (!input.disabled) camera.click(); });
    [picker, camera].forEach(source => source.addEventListener('change', () => { add([...source.files]); source.value = ''; }));
    ['dragenter', 'dragover'].forEach(type => wrapper.addEventListener(type, event => { if (input.disabled) return; event.preventDefault(); wrapper.classList.add('is-over'); }));
    ['dragleave', 'drop'].forEach(type => wrapper.addEventListener(type, event => { event.preventDefault(); wrapper.classList.remove('is-over'); }));
    wrapper.addEventListener('drop', event => { if (event.dataTransfer?.files.length) add([...event.dataTransfer.files]); });
    input.form?.addEventListener('reset', () => setTimeout(() => { files.forEach(release); files = []; showError(''); render(); }));
    input.addEventListener('invalid', event => { event.preventDefault(); showError(cfg.requiredText || 'Vui lòng chọn tệp.'); drop.focus(); });
    new MutationObserver(render).observe(input, {attributes: true, attributeFilter: ['disabled']});

    input.classList.add('ui-upload-native'); input.tabIndex = -1; input.setAttribute('aria-hidden', 'true');
    const labelText = (input.labels?.[0]?.textContent || '').replace('*', '').trim();
    if (labelText) drop.setAttribute('aria-label', `${pickText.textContent} — ${labelText}`);
    wrapper.append(picker, camera, drop, list, error);
    input.id && document.querySelectorAll(`label[for="${CSS.escape(input.id)}"]`).forEach(label => label.addEventListener('click', event => { event.preventDefault(); drop.focus(); }));
    instances.set(wrapper, {render, reset: () => { files.forEach(release); files = []; showError(''); render(); sync(); }});
    render();
  };

  const initAll = root => {
    if (root.matches?.('[data-ui-upload]')) init(root);
    root.querySelectorAll?.('[data-ui-upload]').forEach(init);
  };
  const start = () => {
    initAll(document);
    new MutationObserver(records => records.forEach(record => record.addedNodes.forEach(node => { if (node.nodeType === 1) initAll(node); })))
      .observe(document.body, {childList: true, subtree: true});
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
  window.uiUpload = {init: initAll, reset: input => instances.get(input?.closest?.('[data-ui-upload]'))?.reset()};
})();
