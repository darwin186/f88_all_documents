document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("[data-area-monitor]");
  if (!root) return;
  const configDialog = root.querySelector("[data-area-email-config-dialog]");
  const configForm = root.querySelector("[data-area-email-config-form]");
  const testDialog = root.querySelector("[data-area-email-test-dialog]");
  const testForm = root.querySelector("[data-area-email-test-form]");
  let previewSample = null;
  const splitEmails = value => [...new Set((value || "").split(/[;,\n]+/).map(item => item.trim().toLowerCase()).filter(Boolean))];
  const renderText = (template, context) => (template || "").replace(/{{\s*([a-z_]+)\s*}}/g, (token, key) => Object.hasOwn(context, key) ? context[key] : token);
  const readJson = async response => {
    const type = response.headers.get("content-type") || "";
    if (!type.includes("application/json")) throw new Error(`Máy chủ trả về dữ liệu không hợp lệ (HTTP ${response.status}).`);
    return response.json();
  };
  root.querySelectorAll("[data-close-area-email]").forEach(button => button.addEventListener("click", () => button.closest("dialog")?.close()));
  const updatePreview = () => {
    if (!configForm || !previewSample) return;
    const confirmation = configForm.dataset.emailStage === "confirmation";
    const subject = configForm.elements[confirmation ? "confirmation_subject_template" : "monitoring_subject_template"];
    const body = configForm.elements[confirmation ? "confirmation_body_template" : "monitoring_body_template"];
    const context = {...previewSample.context, support_email: configForm.elements.support_email.value.trim()};
    const fromAddress = previewSample.from_email.replace(/^.*<([^>]+)>$/, "$1");
    const fromName = configForm.elements.from_name.value.trim();
    configDialog.querySelector("[data-area-live-preview-name]").textContent = previewSample.area;
    configDialog.querySelector("[data-area-live-preview-from]").textContent = fromName ? `${fromName} <${fromAddress}>` : fromAddress;
    configDialog.querySelector("[data-area-live-preview-to]").textContent = previewSample.to.join(", ") || "—";
    configDialog.querySelector("[data-area-live-preview-cc]").textContent = splitEmails(configForm.elements.cc_emails_text.value).join(", ") || "—";
    configDialog.querySelector("[data-area-live-preview-bcc]").textContent = splitEmails(configForm.elements.bcc_emails_text.value).join(", ") || "—";
    configDialog.querySelector("[data-area-live-preview-subject]").textContent = renderText(subject.value, context) || "—";
    const bodyHtml = window.campaignRichEmail?.html(body) || body.value;
    const bodyPreview = configDialog.querySelector("[data-area-live-preview-body]");
    if (window.campaignRichEmail) bodyPreview.innerHTML = window.campaignRichEmail.render(bodyHtml, context) || "—";
    else bodyPreview.textContent = renderText(bodyHtml, context) || "—";
  };
  const loadPreview = async () => {
    const errorBox = configDialog.querySelector("[data-area-live-preview-error]");
    errorBox.hidden = true;
    try {
      const response = await fetch(configDialog.dataset.previewUrl, {credentials: "same-origin", cache: "no-store"});
      const data = await readJson(response);
      if (!response.ok || !data.ok) throw new Error(data.error || "Không thể tải dữ liệu xem trước.");
      previewSample = data; updatePreview();
    } catch (error) { errorBox.textContent = error.message; errorBox.hidden = false; }
  };
  root.querySelector("[data-open-area-email-config]")?.addEventListener("click", () => { configDialog?.showModal(); loadPreview(); });
  root.querySelector("[data-open-area-email-test]")?.addEventListener("click", () => testDialog?.showModal());
  if (configForm) {
    let active = configForm.dataset.emailStage === "confirmation"
      ? configForm.elements.confirmation_body_template
      : configForm.elements.monitoring_body_template;
    ["monitoring_subject_template", "monitoring_body_template", "confirmation_subject_template", "confirmation_body_template"].forEach(name => {
      configForm.elements[name]?.addEventListener("focus", event => { active = event.currentTarget; });
    });
    configForm.querySelector("[data-rich-email-editor]")?.addEventListener("focus", () => {
      active = configForm.elements[configForm.dataset.emailStage === "confirmation" ? "confirmation_body_template" : "monitoring_body_template"];
    });
    configForm.querySelectorAll("[data-area-email-variable]").forEach(button => button.addEventListener("click", () => {
      if (!active) return;
      const token = `{{${button.dataset.areaEmailVariable}}}`;
      if (active._richEmail && window.campaignRichEmail) window.campaignRichEmail.insert(active, token);
      else {
        const start = active.selectionStart ?? active.value.length;
        active.setRangeText(token, start, active.selectionEnd ?? start, "end"); active.focus();
      }
      updatePreview();
    }));
    configForm.addEventListener("input", updatePreview);
    configForm.addEventListener("change", updatePreview);
    configForm.addEventListener("submit", async event => {
      event.preventDefault();
      const submit = configForm.querySelector('[type="submit"]'), errorBox = configForm.querySelector("[data-area-email-config-error]");
      submit.disabled = true; errorBox.hidden = true;
      try {
        const response = await fetch(configForm.action, {method: "POST", body: new FormData(configForm), credentials: "same-origin", headers: {Accept: "application/json"}});
        const data = await readJson(response);
        if (!response.ok || !data.ok) throw new Error(data.errors ? Object.values(data.errors).flat().join(" ") : data.error || "Không thể lưu.");
        configDialog.close(); window.campaignToast?.(data.message, "success");
      } catch (error) { errorBox.textContent = error.message; errorBox.hidden = false; }
      finally { submit.disabled = false; }
    });
  }
  testForm?.addEventListener("submit", async event => {
    event.preventDefault();
    const submit = testForm.querySelector('[type="submit"]'), errorBox = testForm.querySelector("[data-area-email-test-error]");
    submit.disabled = true; errorBox.hidden = true;
    try {
      const response = await fetch(testForm.action, {method: "POST", body: new FormData(testForm), credentials: "same-origin", headers: {Accept: "application/json"}});
      const data = await readJson(response);
      if (!response.ok || !data.ok) throw new Error(data.error || "Không thể gửi thử.");
      testDialog.close(); window.campaignToast?.(data.message, "success");
    } catch (error) { errorBox.textContent = error.message; errorBox.hidden = false; }
    finally { submit.disabled = false; }
  });
});
