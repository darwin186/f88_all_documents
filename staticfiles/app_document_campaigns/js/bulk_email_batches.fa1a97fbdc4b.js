document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("[data-bulk-email-dialog]");
  if (!root) return;
  const form = root.querySelector("[data-bulk-email-form]");
  const list = root.querySelector("[data-bulk-email-list]");
  const summary = root.querySelector("[data-bulk-email-summary]");
  const errorBox = root.querySelector("[data-bulk-email-error]");
  const transports = root.querySelector("[data-bulk-email-transports]");
  const sendButton = root.querySelector("[data-send-bulk-email]");
  let kind = "", batches = [];
  const readJson = async response => {
    const type = response.headers.get("content-type") || "";
    if (!type.includes("application/json")) throw new Error(`Máy chủ trả dữ liệu không hợp lệ (HTTP ${response.status}).`);
    return response.json();
  };
  const refreshButton = () => { sendButton.disabled = !list.querySelector("input:checked"); };
  const render = data => {
    batches = data.batches;
    summary.textContent = `${data.eligible} email hợp lệ · ${data.invalid} email lỗi · ${data.batches.length} batch · tối đa ${data.chunk_size} email/batch`;
    list.replaceChildren();
    transports.replaceChildren();
    const legend = document.createElement("legend"); legend.textContent = "Kênh gửi email"; transports.append(legend);
    data.transports.forEach(provider => {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "radio"; input.name = "bulk_email_transport"; input.value = provider.value;
      input.checked = provider.value === data.default_transport;
      const text = document.createElement("span");
      const strong = document.createElement("strong"); strong.textContent = provider.label;
      const small = document.createElement("small");
      small.textContent = provider.value === "power_automate" ? "Webhook · gửi theo batch 25–50 email" : "Máy chủ SMTP · gửi tuần tự qua worker";
      text.append(strong, small); label.append(input, text); transports.append(label);
    });
    if (!data.transports.length) {
      const empty = document.createElement("p"); empty.textContent = "Chưa có kênh gửi email nào được cấu hình."; transports.append(empty);
    }
    data.batches.forEach(batch => {
      const label = document.createElement("label");
      label.className = "crm-bulk-email-row";
      const input = document.createElement("input");
      input.type = "checkbox"; input.value = String(batch.index); input.addEventListener("change", refreshButton);
      const text = document.createElement("span");
      const strong = document.createElement("strong"); strong.textContent = `Batch ${batch.index} · ${batch.count} email`;
      const small = document.createElement("small"); small.textContent = `${batch.first} → ${batch.last}`;
      text.append(strong, small); label.append(input, text); list.append(label);
    });
    if (!data.batches.length) list.textContent = "Không có người nhận hợp lệ để gửi.";
    if (data.invalid) {
      const warning = document.createElement("p"); warning.className = "crm-bulk-email-warning";
      warning.textContent = `${data.invalid} người nhận bị loại do thiếu hoặc sai email. Hãy cập nhật Master Data rồi chuẩn bị lại.`;
      list.prepend(warning);
    }
    refreshButton();
  };
  document.querySelectorAll("[data-open-bulk-email]").forEach(button => button.addEventListener("click", async () => {
    kind = button.dataset.bulkEmailKind;
    root.querySelector("[data-bulk-email-title]").textContent = button.dataset.bulkEmailTitle || "Chuẩn bị batch email";
    errorBox.hidden = true; summary.textContent = "Đang kiểm tra người nhận…"; list.replaceChildren();
    transports.innerHTML = "<legend>Kênh gửi email</legend><p>Đang kiểm tra các kênh đã được cấu hình…</p>"; sendButton.disabled = true;
    root.showModal();
    try {
      const response = await fetch(`${root.dataset.prepareUrl}?kind=${encodeURIComponent(kind)}`, {credentials: "same-origin", cache: "no-store", headers: {Accept: "application/json"}});
      const data = await readJson(response);
      if (!response.ok || !data.ok) throw new Error(data.error || "Không thể chuẩn bị batch.");
      render(data);
    } catch (error) { errorBox.textContent = error.message; errorBox.hidden = false; summary.textContent = "Không thể chuẩn bị batch."; }
  }));
  root.querySelectorAll("[data-close-bulk-email]").forEach(button => button.addEventListener("click", () => root.close()));
  root.querySelector("[data-bulk-select-all]").addEventListener("click", () => {
    const inputs = [...list.querySelectorAll('input[type="checkbox"]')];
    const select = inputs.some(input => !input.checked); inputs.forEach(input => { input.checked = select; }); refreshButton();
  });
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const selected = [...list.querySelectorAll("input:checked")].map(input => batches[Number(input.value) - 1].target_ids);
    if (!selected.length) return;
    const transport = form.querySelector('input[name="bulk_email_transport"]:checked')?.value;
    if (!transport) { errorBox.textContent = "Hãy chọn một kênh gửi email."; errorBox.hidden = false; return; }
    const original = sendButton.textContent;
    sendButton.disabled = true; sendButton.classList.add("is-loading"); sendButton.textContent = "Đang xếp hàng…"; errorBox.hidden = true;
    try {
      const csrf = form.querySelector('[name="csrfmiddlewaretoken"]').value;
      const response = await fetch(root.dataset.sendUrl, {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json", "Accept": "application/json", "X-CSRFToken": csrf}, body: JSON.stringify({kind, transport, batches: selected})});
      const data = await readJson(response);
      if (!response.ok || !data.ok) throw new Error(data.error || "Không thể gửi batch.");
      root.close(); window.campaignToast?.(`${data.message} ${data.batch_count} batch · ${data.email_count} email.`, "success");
      setTimeout(() => window.location.reload(), 1200);
    } catch (error) { errorBox.textContent = error.message; errorBox.hidden = false; }
    finally { sendButton.disabled = false; sendButton.classList.remove("is-loading"); sendButton.textContent = original; }
  });
});
