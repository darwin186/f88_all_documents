(() => {
  const sync = (root) => {
    const selected = new Set(
      [...document.querySelectorAll('input[name="response_options"]:checked')].map((input) => input.value)
    );
    root.querySelectorAll('[data-guidance-option]').forEach((item) => {
      const visible = selected.has(item.dataset.guidanceOption);
      item.hidden = !visible;
      item.querySelectorAll('textarea, input').forEach((field) => {
        field.disabled = !visible;
      });
    });
  };

  document.querySelectorAll('[data-response-guidance-config]').forEach((root) => {
    sync(root);
    document.querySelectorAll('input[name="response_options"]').forEach((checkbox) => {
      checkbox.addEventListener('change', () => sync(root));
    });
  });
})();
