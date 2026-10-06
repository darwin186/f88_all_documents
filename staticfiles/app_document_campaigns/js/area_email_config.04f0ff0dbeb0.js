document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("[data-area-monitor]");
  if (!root) return;
  const configDialog = root.querySelector("[data-area-email-config-dialog]");
  const configForm = root.querySelector("[data-area-email-config-form]");
  const testDialog = root.querySelector("[data-area-email-test-dialog]");
  const testForm = root.querySelector("[data-area-email-test-form]");
  const readJson = async response => {
    const type = response.headers.get("content-type") || "";
    if (!type.includes("application/json")) throw new Error(`Máy chủ trả về dữ liệu không hợp lệ (HTTP ${response.status}).`);
    return response.json();
  };
  root.querySelectorAll("[data-close-area-email]").forEach(button => button.addEventListener("click", () => button.closest("dialog")?.close()));
  root.querySelector("[data-open-area-email-config]")?.addEventListener("click", () => configDialog?.showModal());
  root.querySelector("[data-open-area-email-test]")?.addEventListener("click", () => testDialog?.showModal());
  if (configForm) {
    let active = configForm.elements.monitoring_body_template;
    ["monitoring_subject_template", "monitoring_body_template", "confirmation_subject_template", "confirmation_body_template"].forEach(name => {
      configForm.elements[name]?.addEventListener("focus", event => { active = event.currentTarget; });
    });
    configForm.querySelectorAll("[data-area-email-variable]").forEach(button => button.addEventListener("click", () => {
      if (!active) return;
      const start = active.selectionStart ?? active.value.length;
      active.setRangeText(`{{${button.dataset.areaEmailVariable}}}`, start, active.selectionEnd ?? start, "end");
      active.focus();
    }));
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
