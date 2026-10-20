document.addEventListener('DOMContentLoaded', () => {
  const dialog = document.getElementById('document-edit-dialog');
  if (!dialog) return;
  const content = dialog.querySelector('[data-edit-content]');
  const entity = dialog.dataset.entityLabel || 'văn bản';
  const entityTitle = entity.charAt(0).toUpperCase() + entity.slice(1);
  let request, opener, detailUrl, submitting = false, cleanedUp = true;
  const fields = new WeakMap();
  const render = html => {
    window.adminDocumentFormControls?.destroy(content);
    content.innerHTML = html;
    window.adminDocumentFormControls?.init(content);
    initLiveFields();
  };
  const error = message => window.adminDocumentNotify?.({type: 'error', title: `Không thể cập nhật ${entity}`, message});
  const open = async trigger => {
    if (submitting) return;
    if (trigger.closest('#docDrawer')) window.closeDocDrawer?.();
    opener = trigger.closest('[data-document-preview]') || (trigger.getClientRects().length ? trigger : document.activeElement);
    request?.abort();
    request = new AbortController();
    const signal = request.signal;
    window.adminDocumentFormControls?.destroy(content);
    content.textContent = `Đang tải thông tin ${entity}…`;
    if (!dialog.open) dialog.showModal();
    cleanedUp = false;
    const url = new URL(trigger.href, window.location.href);
    url.searchParams.set('edit', '1');
    detailUrl = url;
    try {
      const response = await fetch(url, {headers: {'X-Requested-With': 'XMLHttpRequest'}, signal});
      if (!response.ok || response.redirected) throw new Error(`Không thể mở ${entity}. Vui lòng tải lại trang hoặc kiểm tra quyền truy cập.`);
      const html = await response.text();
      if (!signal.aborted) render(html);
    } catch (failure) {
      if (failure.name !== 'AbortError') { content.replaceChildren(); error(failure.message); }
    }
  };
  document.addEventListener('click', event => {
    const trigger = event.target.closest('[data-document-edit]');
    if (trigger && event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
      event.preventDefault();
      open(trigger);
    }
    if (event.target.closest('[data-edit-close]') && !submitting) close();
  });
  const cleanUp = () => {
    if (cleanedUp || dialog.open) return;
    cleanedUp = true;
    request?.abort();
    window.adminDocumentFormControls?.destroy(content);
    const url = new URL(window.location.href);
    if (url.searchParams.has('edit')) {
      url.searchParams.delete('edit');
      history.replaceState(null, '', url);
    }
    opener?.focus();
  };
  const close = () => { dialog.close(); cleanUp(); };
  dialog.addEventListener('cancel', event => { event.preventDefault(); if (!submitting) close(); });
  dialog.addEventListener('close', cleanUp);
  const valueOf = input => input.type === 'checkbox' ? String(input.checked) : input.value;
  const labelOf = input => input.tagName === 'SELECT' ? (input.value ? input.selectedOptions[0]?.textContent || '—' : '—') : input.type === 'checkbox' ? (input.checked ? 'Có' : 'Không') : (input.value || '—');
  const setValue = (state, value) => {
    state.restoring = true;
    if (state.input.type === 'checkbox') state.input.checked = value === true || value === 'true';
    else {
      state.input.value = value == null ? '' : String(value);
      if (state.input.datepicker) state.input.datepicker.setDate(state.input.value || {clear: true});
    }
    state.input.dispatchEvent(new Event('change', {bubbles: true}));
    state.restoring = false;
  };
  const endEdit = wrapper => {
    wrapper.querySelector('[data-live-display]').hidden = false;
    wrapper.querySelector('[data-live-editor]').hidden = true;
    window.uiSelect?.closeAll(wrapper);
    wrapper.querySelectorAll('[data-select-menu]').forEach(menu => { menu.hidden = true; });
    wrapper.querySelectorAll('[data-select-toggle]').forEach(toggle => toggle.setAttribute('aria-expanded', 'false'));
    fields.get(wrapper).input.datepicker?.hide();
  };
  const initLiveFields = () => content.querySelectorAll('[data-live-field]').forEach(wrapper => {
    const input = wrapper.querySelector('select, textarea, input:not([type=search])');
    fields.set(wrapper, {input, saved: valueOf(input), restoring: false});
    wrapper.querySelector('[data-live-label]').textContent = labelOf(input);
  });
  const syncGrid = result => {
    const path = new URL(detailUrl).pathname;
    const row = [...document.querySelectorAll('[data-document-preview]')].find(item => new URL(item.dataset.documentPreview, location.href).pathname === path);
    const cell = row?.querySelector(`[data-document-cell="${result.field}"]`);
    if (result.field === 'status' && result.status) {
      [...content.querySelectorAll('.adm-edit-summary .adm-status'), ...(cell?.querySelectorAll('.adm-status') || [])].forEach(badge => {
        badge.textContent = result.status.name;
        badge.style.color = result.status.text_color;
        badge.style.backgroundColor = result.status.bg_color;
      });
    } else if (cell) {
      const label = cell.querySelector('a') || cell;
      label.textContent = result.display;
      if (label.tagName === 'A') label.title = result.display;
    }
    document.dispatchEvent(new CustomEvent('document-live-updated', {detail: result}));
  };
  const saveField = async wrapper => {
    const state = fields.get(wrapper);
    if (!state || state.restoring || submitting) return;
    if (valueOf(state.input) === state.saved) { endEdit(wrapper); return; }
    if (!state.input.reportValidity()) return;
    submitting = true;
    const message = wrapper.querySelector('[data-live-status]');
    const alert = wrapper.querySelector('[data-live-error]');
    alert.hidden = true; message.textContent = 'Đang lưu…';
    const form = content.querySelector('#document-edit-form');
    const body = new URLSearchParams({field: wrapper.dataset.liveField, value: valueOf(state.input), csrfmiddlewaretoken: form.elements.csrfmiddlewaretoken.value});
    const controls = [...wrapper.querySelectorAll('input, select, textarea, button')];
    controls.forEach(control => { control.disabled = true; });
    try {
      const response = await fetch(form.dataset.liveUrl, {method: 'POST', body, headers: {'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/x-www-form-urlencoded'}});
      const result = response.headers.get('Content-Type')?.includes('application/json') ? await response.json() : null;
      if (!response.ok || !result?.ok) throw new Error(result?.error || 'Không thể lưu giá trị. Vui lòng thử lại.');
      setValue(state, result.value);
      state.saved = valueOf(state.input);
      wrapper.querySelector('[data-live-label]').textContent = result.display;
      Object.entries(result.related_values || {}).forEach(([field, value]) => {
        const related = content.querySelector(`[data-live-field="${field}"]`);
        if (!related) return;
        const relatedState = fields.get(related);
        setValue(relatedState, value); relatedState.saved = valueOf(relatedState.input);
        related.querySelector('[data-live-label]').textContent = labelOf(relatedState.input);
      });
      message.textContent = ''; endEdit(wrapper); syncGrid(result);
      window.adminDocumentNotify?.({type: 'success', title: `Đã cập nhật ${entity}`, message: `${entityTitle}: ${content.querySelector('.adm-edit-summary strong').textContent}\n${wrapper.querySelector('label').textContent.replace('*', '').trim()}: ${result.display}`});
    } catch (failure) {
      message.textContent = ''; alert.textContent = failure.message; alert.hidden = false;
      error(`${entityTitle}: ${content.querySelector('.adm-edit-summary strong').textContent}\n${wrapper.querySelector('label').textContent.replace('*', '').trim()}: ${failure.message}\nGiá trị đang nhập: ${labelOf(state.input)}`);
    } finally {
      controls.forEach(control => { control.disabled = false; });
      submitting = false;
    }
  };
  dialog.addEventListener('click', event => {
    const wrapper = event.target.closest('[data-live-field]');
    if (!wrapper || submitting) return;
    if (event.target.closest('[data-live-display]')) {
      wrapper.querySelector('[data-live-display]').hidden = true;
      wrapper.querySelector('[data-live-editor]').hidden = false;
      const input = fields.get(wrapper).input;
      (wrapper.querySelector('.ui-select-toggle, [data-select-toggle]') || input).focus();
    }
    if (event.target.closest('[data-live-save]')) saveField(wrapper);
    if (event.target.closest('[data-live-cancel]')) {
      const state = fields.get(wrapper); setValue(state, state.saved);
      wrapper.querySelector('[data-live-error]').hidden = true;
      endEdit(wrapper); wrapper.querySelector('[data-live-display]').focus();
    }
  });
  dialog.addEventListener('keydown', event => {
    const wrapper = event.target.closest('[data-live-field]');
    if (!wrapper || event.defaultPrevented || wrapper.querySelector('[data-live-editor]').hidden) return;
    if (event.key === 'Enter' && event.target.tagName !== 'BUTTON' && !event.target.matches('[data-select-search], .ui-select-search') && (event.target.tagName !== 'TEXTAREA' || event.ctrlKey || event.metaKey)) {
      event.preventDefault(); saveField(wrapper);
    }
    if (event.key === 'Escape' && !submitting) {
      event.preventDefault(); event.stopPropagation(); wrapper.querySelector('[data-live-cancel]').click();
    }
  });
  const onValueChange = event => {
    const wrapper = event.target.closest('[data-live-field]');
    const state = wrapper && fields.get(wrapper);
    if (state && !state.restoring && event.target === state.input && !wrapper.querySelector('[data-live-editor]').hidden) saveField(wrapper);
  };
  dialog.addEventListener('change', event => { if (event.target.matches('select, input[type=checkbox]')) onValueChange(event); });
  dialog.addEventListener('changeDate', onValueChange, true);
  dialog.addEventListener('submit', event => {
    if (event.target.id === 'document-edit-form') event.preventDefault();
  });
  const autoopen = document.querySelector('[data-edit-autoopen]');
  if (autoopen) setTimeout(() => open(autoopen), 0);
});
