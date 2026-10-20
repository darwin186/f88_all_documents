document.addEventListener('DOMContentLoaded', () => {
  const form = document.querySelector('[data-adm-filters]');
  if (!form) return;
  const controllers = [], calendars = [];
  const closeMenus = except => controllers.forEach(controller => { if (controller !== except) controller.close(); });
  const changed = () => form.dispatchEvent(new Event('change', {bubbles: true}));
  form.querySelectorAll('[data-filter-select]').forEach(wrapper => {
    const source = wrapper.querySelector('select'), label = wrapper.querySelector('label');
    const toggle = document.createElement('button'); toggle.type = 'button'; toggle.id = `${source.id}-toggle`;
    toggle.className = 'adm-filter-toggle'; toggle.dataset.filterToggle = '';
    toggle.setAttribute('aria-expanded', 'false'); toggle.setAttribute('aria-haspopup', 'listbox'); toggle.setAttribute('aria-controls', `${source.id}-options`);
    const text = document.createElement('span');
    const chevron = document.createElement('span'); chevron.className = 'adm-filter-chevron'; chevron.textContent = '⌄'; chevron.setAttribute('aria-hidden', 'true'); toggle.append(text, chevron);
    const menu = document.createElement('div'); menu.className = 'adm-filter-menu'; menu.hidden = true;
    const search = document.createElement('input'); search.type = 'search'; search.className = 'adm-filter-option-search'; search.placeholder = 'Tìm kiếm…'; search.setAttribute('aria-label', `Tìm ${label.textContent.toLowerCase()}`);
    const list = document.createElement('div'); list.id = `${source.id}-options`; list.className = 'adm-filter-options'; list.setAttribute('role', 'listbox'); list.setAttribute('aria-label', label.textContent);
    menu.append(search, list); wrapper.append(toggle, menu);
    const close = () => { menu.hidden = true; wrapper.classList.remove('is-open'); toggle.setAttribute('aria-expanded', 'false'); };
    const refresh = () => {
      text.textContent = source.selectedOptions[0]?.textContent || source.options[0].textContent;
      const term = search.value.trim().toLocaleLowerCase('vi'); list.replaceChildren();
      [...source.options].filter(option => !option.disabled && option.textContent.toLocaleLowerCase('vi').includes(term)).forEach(option => {
        const item = document.createElement('button'); item.type = 'button'; item.tabIndex = -1; item.setAttribute('role', 'option'); item.setAttribute('aria-selected', String(option.selected)); item.dataset.value = option.value;
        const title = document.createElement('span'); title.textContent = option.textContent;
        const check = document.createElement('span'); check.textContent = option.selected ? '✓' : ''; check.setAttribute('aria-hidden', 'true'); item.append(title, check);
        item.addEventListener('click', () => { source.value = option.value; source.dispatchEvent(new Event('change', {bubbles: true})); close(); toggle.focus(); });
        list.append(item);
      });
      if (!list.children.length) { const empty = document.createElement('p'); empty.textContent = 'Không tìm thấy lựa chọn'; list.append(empty); }
    };
    const controller = {close}; controllers.push(controller);
    const open = () => {
      closeMenus(controller); calendars.forEach(calendar => calendar.close());
      search.value = ''; refresh(); menu.hidden = false; wrapper.classList.add('is-open'); toggle.setAttribute('aria-expanded', 'true');
      menu.classList.remove('opens-up');
      const rect = toggle.getBoundingClientRect();
      if (innerHeight - rect.bottom < Math.min(menu.scrollHeight, 280) && rect.top > innerHeight - rect.bottom) menu.classList.add('opens-up');
      search.focus();
    };
    toggle.addEventListener('click', () => menu.hidden ? open() : close());
    search.addEventListener('input', refresh);
    source.addEventListener('change', refresh);
    wrapper.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !menu.hidden) { event.preventDefault(); event.stopPropagation(); close(); toggle.focus(); return; }
      const items = [...list.querySelectorAll('[role=option]')];
      if (['ArrowDown', 'ArrowUp'].includes(event.key)) {
        event.preventDefault();
        if (menu.hidden) open();
        const options = [...list.querySelectorAll('[role=option]')];
        const current = options.indexOf(document.activeElement);
        const next = current < 0 ? (event.key === 'ArrowDown' ? 0 : options.length - 1) : (current + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length;
        options[next]?.focus(); options[next]?.scrollIntoView({block: 'nearest'});
      } else if (['Home', 'End'].includes(event.key) && items.includes(event.target)) {
        event.preventDefault(); (event.key === 'Home' ? items[0] : items.at(-1))?.focus();
      } else if (event.key === 'Enter' && event.target === search) { event.preventDefault(); items[0]?.click(); }
    });
    source.hidden = true; source.tabIndex = -1; label.htmlFor = toggle.id; refresh();
  });
  document.addEventListener('pointerdown', event => { if (!event.target.closest('[data-filter-select]')) closeMenus(); });
  document.addEventListener('focusin', event => { if (!event.target.closest('[data-filter-select]')) closeMenus(); });
  const rangeInput = form.querySelector('[data-filter-created-range]');
  const start = form.elements.start_date, end = form.elements.end_date, allCreated = form.elements.created_all;
  const issue = form.querySelector('[data-filter-issue-date]');
  let rangePicker, issuePicker;
  if (window.flatpickr) {
    const locale = {...window.flatpickr.l10ns.vn, rangeSeparator: ' → '};
    const options = {
      dateFormat: 'd/m/Y', locale, disableMobile: true, monthSelectorType: 'static',
      onReady: (_, __, instance) => instance.calendarContainer.classList.add('adm-filter-datepicker'),
      onOpen: (_, __, instance) => {
        closeMenus(); calendars.forEach(other => { if (other !== instance) other.close(); });
        document.querySelectorAll('[data-adm-date], [data-document-datepicker]').forEach(input => input.datepicker?.hide());
      },
    };
    rangePicker = window.flatpickr(rangeInput, {
      ...options, mode: 'range', defaultDate: [start.value, end.value].filter(Boolean),
      onChange: (dates, _, instance) => {
        start.value = dates[0] ? instance.formatDate(dates[0], 'd/m/Y') : '';
        end.value = dates.length ? instance.formatDate(dates[1] || dates[0], 'd/m/Y') : '';
        allCreated.value = dates.length ? '' : '1'; changed();
      },
      onClose: (dates, _, instance) => { if (dates.length === 1) instance.setDate([dates[0], dates[0]], false); },
    });
    if (issue) issuePicker = window.flatpickr(issue, {...options, onChange: changed});
    calendars.push(rangePicker);
    if (issuePicker) calendars.push(issuePicker);
    form.querySelectorAll('[data-filter-calendar]').forEach(button => button.addEventListener('click', () => document.getElementById(button.dataset.filterCalendar)._flatpickr.open()));
  }
  const chips = form.querySelector('[data-filter-chips]');
  const values = () => {
    const selected = [];
    if (form.elements.q.value.trim()) selected.push({key: 'q', label: 'Tìm kiếm', value: form.elements.q.value.trim()});
    form.querySelectorAll('[data-filter-select] select').forEach(source => {
      if (source.value) selected.push({key: source.name, label: source.closest('[data-filter-select]').querySelector('label').textContent, value: source.selectedOptions[0].textContent});
    });
    if (start.value || end.value) selected.push({key: 'created', label: 'Ngày tạo', value: start.value === end.value ? start.value : `${start.value || '…'} → ${end.value || '…'}`});
    if (issue?.value) selected.push({key: 'issue_date', label: 'Ngày ban hành', value: issue.value});
    return selected;
  };
  window.adminUi.mountChips(form, chips, {values, remove: key => {
    if (key === 'created') { start.value = ''; end.value = ''; allCreated.value = '1'; rangePicker?.clear(false); rangeInput.value = ''; }
    else if (key === 'issue_date') { issuePicker?.clear(false); issue.value = ''; }
    else { const input = form.elements[key]; input.value = ''; input.dispatchEvent(new Event('change', {bubbles: true})); }
    changed(); form.requestSubmit();
  }});
  document.addEventListener('scroll', event => {
    if (event.target === document || event.target.contains?.(form)) { closeMenus(); calendars.forEach(calendar => calendar.close()); }
  }, true);
  window.addEventListener('resize', () => { closeMenus(); calendars.forEach(calendar => calendar.close()); });
});
