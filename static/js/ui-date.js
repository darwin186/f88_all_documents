/* F88 UI Kit — Date (chọn ngày / khoảng ngày / ngày giờ / giờ). Dùng: <div class="ui-date" data-ui-date data-mode="single"><input id name></div>.
   Dựa trên Flatpickr (phải nạp trước). Xem docs/ui-kit/components/date.md */
(() => {
  'use strict';
  const instances = new WeakMap();
  const pad = n => String(n).padStart(2, '0');
  const isoDate = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const vnDate = d => `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
  const hm = d => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const today = () => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), d.getDate()); };
  const addDays = (d, n) => { const r = new Date(d); r.setDate(r.getDate() + n); return r; };

  const ICON_DATE = '<svg class="ui-date-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></svg>';
  const ICON_CLOCK = '<svg class="ui-date-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>';
  const VN = {
    weekdays: {shorthand: ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'], longhand: ['Chủ nhật', 'Thứ hai', 'Thứ ba', 'Thứ tư', 'Thứ năm', 'Thứ sáu', 'Thứ bảy']},
    months: {
      shorthand: ['Th1', 'Th2', 'Th3', 'Th4', 'Th5', 'Th6', 'Th7', 'Th8', 'Th9', 'Th10', 'Th11', 'Th12'],
      longhand: ['Tháng một', 'Tháng hai', 'Tháng ba', 'Tháng tư', 'Tháng năm', 'Tháng sáu', 'Tháng bảy', 'Tháng tám', 'Tháng chín', 'Tháng mười', 'Tháng mười một', 'Tháng mười hai'],
    },
    firstDayOfWeek: 1, rangeSeparator: ' to ', weekAbbreviation: 'Tuần', scrollTitle: 'Cuộn để tăng giảm', toggleTitle: 'Nhấn để chuyển đổi', time_24hr: true,
  };
  const FORMATS = {
    single: {value: 'Y-m-d', alt: 'd/m/Y'}, range: {value: 'Y-m-d', alt: 'd/m/Y'},
    datetime: {value: 'Y-m-d H:i', alt: 'd/m/Y H:i'}, time: {value: 'H:i', alt: 'H:i'},
  };
  const formatDate = (date, format) => ({
    'Y-m-d': isoDate(date), 'd/m/Y': vnDate(date), 'Y-m-d H:i': `${isoDate(date)} ${hm(date)}`, 'd/m/Y H:i': `${vnDate(date)} ${hm(date)}`, 'H:i': hm(date),
  }[format] || isoDate(date));
  const RANGE_SHORTCUTS = {
    today: ['Hôm nay', () => [today(), today()]],
    7: ['7 ngày qua', () => [addDays(today(), -6), today()]],
    30: ['30 ngày qua', () => [addDays(today(), -29), today()]],
    month: ['Tháng này', () => { const t = today(); return [new Date(t.getFullYear(), t.getMonth(), 1), t]; }],
  };
  const pointShortcut = key => {
    if (key === 'today') return ['Hôm nay', () => today()];
    if (key === 'now') return ['Bây giờ', () => new Date()];
    if (key === 'tomorrow8') return ['Mai 08:00', () => { const d = addDays(today(), 1); d.setHours(8, 0, 0, 0); return d; }];
    if (key.startsWith('t:')) { const [h, m] = key.slice(2).split(':').map(Number); return [key.slice(2), () => { const d = new Date(); d.setHours(h, m, 0, 0); return d; }]; }
    return null;
  };
  const rule = value => (value === 'today' ? today() : value === 'now' ? new Date() : value || undefined);
  const idOf = ref => (ref || '').replace(/^#/, '');

  // Khi ô "Từ" đổi thì ô "Đến" (data-link-min="id-của-ô-Từ") không được sớm hơn
  const applyLinks = (source, dates) => {
    if (!source.id) return;
    document.querySelectorAll('[data-ui-date][data-link-min]').forEach(wrapper => {
      if (idOf(wrapper.dataset.linkMin) !== source.id) return;
      const linked = instances.get(wrapper)?.picker;
      if (!linked) return;
      linked.set('minDate', dates[0] || null);
      if (dates[0] && linked.selectedDates[0] && linked.selectedDates[0] < dates[0]) linked.clear();
    });
  };

  const init = wrapper => {
    if (instances.has(wrapper)) return;
    const input = wrapper.querySelector('input');
    if (!input) return;
    if (!window.flatpickr) { window.addEventListener('load', () => init(wrapper), {once: true}); return; }
    const cfg = wrapper.dataset;
    const mode = FORMATS[cfg.mode] ? cfg.mode : 'single';
    const range = mode === 'range';
    const withTime = mode === 'datetime' || mode === 'time';
    const formats = FORMATS[mode];
    const maxDays = Number(cfg.maxDays) || 0;
    const required = input.required || 'required' in cfg;
    const placeholder = input.placeholder || cfg.placeholder || (mode === 'time' ? 'Chọn giờ' : range ? 'Chọn khoảng ngày' : 'Chọn ngày');
    const labelText = (input.labels?.[0]?.textContent || '').replace('*', '').trim();
    const el = (tag, className, attrs = {}) => { const node = document.createElement(tag); if (className) node.className = className; Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v)); return node; };

    const error = el('p', 'ui-date-error', {role: 'alert'}); error.hidden = true;
    const showError = message => { error.textContent = message || ''; error.hidden = !message; wrapper.classList.toggle('is-invalid', Boolean(message)); };
    const clear = el('button', 'ui-date-clear', {type: 'button', 'aria-label': 'Xóa'}); clear.textContent = '×'; clear.hidden = true;

    const paint = () => {
      const picker = input._flatpickr;
      clear.hidden = !picker || picker.selectedDates.length === 0 || input.disabled;
      wrapper.classList.toggle('is-disabled', input.disabled);
      if (range && picker?.altInput) picker.altInput.value = picker.altInput.value.replace(' to ', ' → ');
    };

    const picker = window.flatpickr(input, {
      mode: range ? 'range' : 'single', dateFormat: formats.value, altInput: true, altFormat: formats.alt, altInputClass: 'ui-date-input',
      enableTime: withTime, noCalendar: mode === 'time', time_24hr: true, minuteIncrement: Number(cfg.step) || 1,
      minTime: cfg.minTime, maxTime: cfg.maxTime, minDate: rule(cfg.min), maxDate: rule(cfg.max),
      disableMobile: true, allowInput: false, animate: false, monthSelectorType: 'static',
      defaultDate: cfg.default === 'today' ? today() : undefined,
      locale: Object.assign({}, window.flatpickr.l10ns?.default || {}, VN),
      formatDate,
      onOpen: () => wrapper.classList.add('is-open'),
      onClose: () => wrapper.classList.remove('is-open'),
      onValueUpdate: paint,
      onChange: dates => {
        if (range && dates.length === 2 && maxDays && (dates[1] - dates[0]) / 86400000 + 1 > maxDays) {
          picker.clear(); showError(cfg.maxDaysText || `Chỉ cho phép chọn tối đa ${maxDays} ngày.`); return;
        }
        showError(''); paint(); applyLinks(input, dates);
      },
      onReady: (dates, _text, instance) => {
        instance.calendarContainer.classList.add('ui-date-cal');
        applyLinks(input, dates);
        const keys = (cfg.shortcuts || '').split(',').map(key => key.trim()).filter(Boolean);
        if (!keys.length) return;
        const bar = el('div', 'ui-date-shortcuts');
        keys.forEach(key => {
          const found = range ? RANGE_SHORTCUTS[key] : pointShortcut(key);
          if (!found) return;
          const [label, resolve] = found;
          const chip = el('button', 'ui-date-chip', {type: 'button'}); chip.textContent = label;
          chip.addEventListener('click', () => { instance.setDate(resolve(), true); if (!withTime || mode === 'time') instance.close(); });
          bar.append(chip);
        });
        instance.calendarContainer.append(bar);
      },
    });

    // Khung ô nhập quanh ô hiển thị; ô gốc giữ id, name và giá trị gửi server
    const display = picker.altInput;
    display.readOnly = true; display.placeholder = placeholder; display.disabled = input.disabled; display.autocomplete = 'off';
    display.id = input.id ? `${input.id}-display` : '';
    if (labelText) display.setAttribute('aria-label', labelText);
    const field = el('div', 'ui-date-field');
    field.insertAdjacentHTML('beforeend', mode === 'time' ? ICON_CLOCK : ICON_DATE);
    if (mode === 'datetime') field.insertAdjacentHTML('beforeend', ICON_CLOCK);
    field.append(display, clear);
    wrapper.prepend(field);
    wrapper.after(error);

    field.addEventListener('click', event => { if (!display.disabled && !event.target.closest('.ui-date-clear')) picker.open(); });
    display.addEventListener('keydown', event => {
      if ((event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') && !picker.isOpen) { event.preventDefault(); picker.open(); }
      if ((event.key === 'Backspace' || event.key === 'Delete') && picker.selectedDates.length) { event.preventDefault(); picker.clear(); }
    });
    clear.addEventListener('click', () => { picker.clear(); display.focus(); });
    if (input.id) document.querySelectorAll(`label[for="${CSS.escape(input.id)}"]`).forEach(label => label.addEventListener('click', event => { event.preventDefault(); if (!display.disabled) picker.open(); display.focus(); }));
    input.form?.addEventListener('reset', () => setTimeout(() => { picker.clear(false); showError(''); paint(); }));
    // Lỗi "bắt buộc" chỉ báo lúc submit, không báo ngay khi người dùng xóa ngày
    input.form?.addEventListener('submit', event => {
      if (!required || input.value || input.disabled || wrapper.getClientRects().length === 0) return;
      event.preventDefault();
      showError(cfg.requiredText || (mode === 'time' ? 'Vui lòng chọn giờ.' : range ? 'Vui lòng chọn khoảng ngày.' : 'Vui lòng chọn ngày.'));
      if (!event.__uiDateFocused) { event.__uiDateFocused = true; display.focus(); }
    }, true);
    new MutationObserver(paint).observe(input, {attributes: true, attributeFilter: ['disabled']});
    if ('invalid' in cfg) showError(cfg.error || (mode === 'time' ? 'Giờ không hợp lệ.' : 'Ngày không hợp lệ.'));
    instances.set(wrapper, {paint, picker});
    if (cfg.linkMin) {   // ô nguồn đã có giá trị từ trước (khởi tạo trước ô này)
      const sourceDate = document.getElementById(idOf(cfg.linkMin))?._flatpickr?.selectedDates[0];
      if (sourceDate) picker.set('minDate', sourceDate);
    }
    paint();
  };

  const initAll = root => {
    if (root.matches?.('[data-ui-date]')) init(root);
    root.querySelectorAll?.('[data-ui-date]').forEach(init);
  };
  const start = () => {
    initAll(document);
    new MutationObserver(records => records.forEach(record => record.addedNodes.forEach(node => { if (node.nodeType === 1) initAll(node); })))
      .observe(document.body, {childList: true, subtree: true});
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
  window.uiDate = {
    init: initAll,
    picker: input => input?._flatpickr,
    set: (input, value) => input?._flatpickr?.setDate(value, true),
    clear: input => input?._flatpickr?.clear(),
  };
})();
