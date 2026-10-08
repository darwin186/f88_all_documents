document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("[data-master-email-templates]");
  if (!root) return;

  root.querySelectorAll("[data-template-select]").forEach(button => button.addEventListener("click", () => {
    root.querySelectorAll("[data-template-item]").forEach(item => {
      const selected = item.contains(button);
      item.classList.toggle("is-selected", selected);
      item.querySelector("[data-template-edit]")?.classList.toggle("is-visible", selected);
      item.querySelector("[data-template-select]")?.setAttribute("aria-expanded", String(selected));
    });
  }));

  const form = root.querySelector("[data-master-template-form]");
  if (!form) return;
  const sample = JSON.parse(document.getElementById("master-email-sample-parameters")?.textContent || "{}");
  const type = form.elements.email_type;
  const subject = form.elements.subject_template;
  const body = form.elements.body_template;
  const cc = form.elements.cc_template;
  const bcc = form.elements.bcc_template;
  const subjectPreview = root.querySelector("[data-master-preview-subject]");
  const bodyPreview = root.querySelector("[data-master-preview-body]");
  let active = body;

  const renderText = value => String(value || "").replace(/{{\s*([a-z_]+)\s*}}/g, (token, key) => Object.hasOwn(sample, key) ? sample[key] : token);
  const updateVariables = () => {
    const isPgd = type.value === "pgd_response";
    root.querySelectorAll("[data-variable-group]").forEach(group => {
      group.hidden = group.dataset.variableGroup === "pgd_response" ? !isPgd : isPgd;
    });
  };
  const updatePreview = () => {
    root.querySelector("[data-master-preview-cc]").textContent = renderText(cc.value) || "—";
    root.querySelector("[data-master-preview-bcc]").textContent = renderText(bcc.value) || "—";
    subjectPreview.textContent = renderText(subject.value) || "—";
    const html = window.campaignRichEmail?.html(body) || body.value;
    if (window.campaignRichEmail) bodyPreview.innerHTML = window.campaignRichEmail.render(html, sample) || "—";
    else bodyPreview.textContent = renderText(html) || "—";
  };
  [subject, body, cc, bcc].forEach(field => field?.addEventListener("focus", () => { active = field; }));
  form.querySelector("[data-rich-email-editor]")?.addEventListener("focus", () => { active = body; });
  form.querySelectorAll("[data-met-variable]").forEach(button => button.addEventListener("click", () => {
    const token = `{{${button.dataset.metVariable}}}`;
    if (active === body && window.campaignRichEmail) window.campaignRichEmail.insert(body, token);
    else {
      const start = active.selectionStart ?? active.value.length;
      active.setRangeText(token, start, active.selectionEnd ?? start, "end");
      active.focus();
      active.dispatchEvent(new Event("input", {bubbles: true}));
    }
    updatePreview();
  }));
  type.addEventListener("change", () => { updateVariables(); updatePreview(); });
  form.addEventListener("input", updatePreview);
  updateVariables();
  updatePreview();

  const startLoading = (button, label) => {
    button.disabled = true;
    button.classList.add("is-loading");
    button.dataset.originalLabel = button.textContent;
    button.textContent = label;
  };
  form.addEventListener("submit", () => startLoading(form.querySelector("[data-master-save]"), "Đang lưu…"));
  root.querySelector("[data-master-test-form]")?.addEventListener("submit", event => {
    startLoading(event.currentTarget.querySelector('[type="submit"]'), "Đang gửi…");
  });
});
