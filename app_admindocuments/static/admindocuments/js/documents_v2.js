document.addEventListener('DOMContentLoaded', () => {
  const nav = document.querySelector('.adm-top-nav');
  if (nav) {
    const syncNavOffset = () => document.documentElement.style.setProperty('--adm-nav-offset', `${Math.ceil(nav.getBoundingClientRect().height) + 16}px`);
    syncNavOffset();
    new ResizeObserver(syncNavOffset).observe(nav);
  }
  const filters = document.querySelector('[data-adm-filters]');
  const exportLink = document.querySelector('[data-adm-export]');
  if (filters && exportLink) {
    const syncExport = () => {
      const params = new URLSearchParams(new FormData(filters));
      [...params].forEach(([key, value]) => { if (!value) params.delete(key); });
      exportLink.href = `${exportLink.dataset.admExport}?${params}`;
    };
    filters.addEventListener('input', syncExport);
    filters.addEventListener('change', syncExport);
    // Calendar selections do not consistently emit native input events.
    exportLink.addEventListener('click', syncExport);
    syncExport();
  }
  const dateInputs = () => document.querySelectorAll('[data-adm-date], [data-document-datepicker]');
  const onPickerShow = event => {
    const input = event.target;
    if (!input.matches?.('[data-adm-date], [data-document-datepicker]')) return;
    input.datepicker.picker.element.classList.add('adm-datepicker');
    dateInputs().forEach(other => { if (other !== input) other.datepicker?.hide(); });
  };
  // Flowbite emits "show"; older datepicker bundles use "showDatepicker".
  document.addEventListener('show', onPickerShow, true);
  document.addEventListener('showDatepicker', onPickerShow, true);
  const closeOutsidePickers = event => {
    dateInputs().forEach(input => {
      const picker = input.datepicker;
      if (!picker?.picker.active || input === event.target || picker.picker.element.contains(event.target)) return;
      const trigger = event.target.closest('[data-adm-date-trigger]');
      if (trigger?.parentElement.contains(input)) return;
      picker.hide();
    });
  };
  document.addEventListener('pointerdown', closeOutsidePickers, true);
  document.addEventListener('click', closeOutsidePickers, true);
  document.addEventListener('focusin', closeOutsidePickers, true);
  // Pickers live outside the scrolling form, so close them before their anchor moves.
  document.addEventListener('scroll', event => {
    dateInputs().forEach(input => {
      if (event.target === document || event.target.contains?.(input)) input.datepicker?.hide();
    });
  }, true);
  window.addEventListener('resize', () => dateInputs().forEach(input => input.datepicker?.hide()));
  document.querySelectorAll('[data-adm-date]').forEach(input => {
    if (window.Datepicker && !input.datepicker) {
      new window.Datepicker(input, { format: 'dd/mm/yyyy', autohide: true, todayBtn: input.name !== 'expiry_date', todayBtnMode: 1 });
      input.dataset.dpAttached = '1';
    }
    input.datepicker?.picker.element.classList.add('adm-datepicker');
  });
  document.querySelectorAll('[data-adm-date-trigger]').forEach(button => {
    button.addEventListener('click', () => {
      const input = button.parentElement.querySelector('input');
      input.focus();
      input.datepicker?.show();
    });
  });
  const createForm = document.querySelector('[data-adm-create-form]');
  createForm?.addEventListener('submit', event => {
    const signer = createForm.querySelector('[name=signer_role]');
    const error = createForm.querySelector('[data-signer-error]');
    if (signer && !signer.value) {
      event.preventDefault();
      error.hidden = false;
      window.adminDocumentNotify?.({type: 'error', title: 'Chưa chọn người ký', message: 'Vui lòng chọn Người ký trước khi tạo văn bản.'});
      const toggle = signer.parentElement.querySelector('.ui-select-toggle, button');
      toggle.classList.add('is-invalid'); toggle.focus();
    }
  });
  createForm?.addEventListener('click', () => {
    if (createForm.querySelector('[name=signer_role]').value) createForm.querySelector('[data-signer-error]').hidden = true;
  });
  const copyWithSelection = (value, trigger) => {
    const active = document.activeElement;
    const selection = window.getSelection();
    const ranges = selection ? Array.from({length: selection.rangeCount}, (_, index) => selection.getRangeAt(index).cloneRange()) : [];
    const input = document.createElement('textarea');
    input.value = value; input.readOnly = true; input.tabIndex = -1;
    input.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0';
    (trigger.closest('dialog[open]') || document.body).append(input);
    try {
      input.focus({preventScroll: true}); input.select();
      if (!document.execCommand('copy')) throw new Error('Copy unavailable');
    } finally {
      input.remove(); active?.focus({preventScroll: true});
      if (selection) { selection.removeAllRanges(); ranges.forEach(range => selection.addRange(range)); }
    }
  };
  document.addEventListener('click', async event => {
    const trigger = event.target.closest('[data-copy-document-number]');
    if (!trigger || event.button !== 0 || trigger.disabled) return;
    event.preventDefault();
    const value = trigger.dataset.copyDocumentNumber;
    const restoreFocus = document.activeElement === trigger;
    trigger.disabled = true;
    try {
      if (window.isSecureContext && navigator.clipboard?.writeText) {
        try { await navigator.clipboard.writeText(value); }
        catch { copyWithSelection(value, trigger); }
      } else copyWithSelection(value, trigger);
      window.adminDocumentNotify?.({type: 'success', title: 'Đã sao chép số hiệu', message: value});
    } catch {
      window.adminDocumentNotify?.({type: 'error', title: 'Chưa sao chép được số hiệu', message: `${value}\nVui lòng chọn số hiệu và sao chép thủ công.`});
    } finally {
      trigger.disabled = false;
      if (restoreFocus && trigger.isConnected && document.activeElement === document.body) trigger.focus({preventScroll: true});
    }
  });
  const menus = [...document.querySelectorAll('.adm-row-actions, .adm-nav-menu')];
  const closeMenus = except => menus.forEach(menu => { if (menu !== except) menu.open = false; });
  menus.forEach(menu => menu.addEventListener('toggle', () => {
    if (!menu.open) return;
    closeMenus(menu);
    const popup = menu.querySelector('.adm-row-menu');
    if (!popup) return;
    const rect = menu.querySelector('summary').getBoundingClientRect();
    const height = popup.offsetHeight;
    popup.style.left = `${Math.max(8, Math.min(rect.right - popup.offsetWidth, window.innerWidth - popup.offsetWidth - 8))}px`;
    popup.style.top = `${rect.bottom + height + 8 > window.innerHeight ? rect.top - height - 4 : rect.bottom + 4}px`;
  }));
  document.addEventListener('click', event => {
    const menu = event.target.closest('.adm-row-actions, .adm-nav-menu');
    if (!menu || event.target.closest('a')) closeMenus();
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') closeMenus(); });
  document.addEventListener('scroll', () => closeMenus(), true);
});
