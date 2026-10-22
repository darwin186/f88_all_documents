/* F88 UI Kit — Color pair (chọn màu chữ + màu nền, xem trước trực tiếp). Xem docs/ui-kit/components/color-pair.md */
(() => {
  'use strict';
  const luminance = hex => {
    const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map(v => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const contrast = (a, b) => { const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };
  const valid = hex => /^#[0-9a-f]{6}$/i.test(hex);

  const init = form => {
    if (form.dataset.ready) return;
    const text = form.querySelector('[data-color-text]');
    const bg = form.querySelector('[data-color-bg]');
    if (!text || !bg) return;
    form.dataset.ready = '1';
    const preview = form.querySelector('[data-color-preview]');
    const save = form.querySelector('[data-color-save]');
    const warn = form.querySelector('[data-color-warn]');
    const textTile = text.closest('.ui-color');
    const bgTile = bg.closest('.ui-color');
    const start = {text: text.value, bg: bg.value};
    const minRatio = Number(form.dataset.minContrast) || 3;
    const paint = () => {
      if (preview) { preview.style.color = text.value; preview.style.backgroundColor = bg.value; }
      textTile?.style.setProperty('--ui-color-value', text.value);
      bgTile?.style.setProperty('--ui-color-value', bg.value);
      const dirty = text.value !== start.text || bg.value !== start.bg;
      form.classList.toggle('is-dirty', dirty);
      if (save) save.disabled = !dirty;
      if (warn) warn.hidden = !(valid(text.value) && valid(bg.value) && contrast(text.value, bg.value) < minRatio);
    };
    [text, bg].forEach(input => input.addEventListener('input', paint));
    form.addEventListener('reset', () => setTimeout(paint));
    paint();
  };
  const initAll = root => {
    if (root.matches?.('[data-ui-color-pair]')) init(root);
    root.querySelectorAll?.('[data-ui-color-pair]').forEach(init);
  };
  const start = () => initAll(document);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
  window.uiColorPair = {init: initAll};
})();
