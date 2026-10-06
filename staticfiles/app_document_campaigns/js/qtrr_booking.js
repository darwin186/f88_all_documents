document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("[data-qtrr-booking]");
  if (!root) return;
  const rows = [...root.querySelectorAll("[data-select-row]")];
  const all = root.querySelector("[data-select-all]");
  const count = root.querySelector("[data-selected-count]");
  const update = () => { if (count) count.textContent = rows.filter(item => item.checked).length; };
  all?.addEventListener("change", () => { rows.forEach(item => { if (!item.disabled) item.checked = all.checked; }); update(); });
  rows.forEach(item => item.addEventListener("change", update));
  const uploadForm = root.querySelector("[data-qtrr-upload-form]");
  const uploadFile = root.querySelector("[data-qtrr-upload-file]");
  root.querySelector("[data-qtrr-upload-open]")?.addEventListener("click", () => uploadFile?.click());
  uploadFile?.addEventListener("change", () => {
    const file = uploadFile.files[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".xlsx") || file.size > 50 * 1024 * 1024) {
      window.campaignToast?.("Chọn file .xlsx tối đa 50 MB.", "error");
      uploadFile.value = "";
      return;
    }
    if (window.confirm(`Tải lên ${file.name} và cập nhật mapping mã lỗi?`)) uploadForm.submit();
    else uploadFile.value = "";
  });
  root.querySelector("[data-qtrr-map-form]")?.addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget, feedback = form.querySelector("[data-map-feedback]"), button = form.querySelector("button");
    const errorIds = rows.filter(item => item.checked).map(item => Number(item.closest("[data-qtrr-row]").dataset.errorId));
    feedback.textContent = "";
    if (!errorIds.length) { feedback.textContent = "Hãy chọn ít nhất một dòng."; return; }
    button.disabled = true;
    try {
      const response = await fetch(root.dataset.mapUrl, {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json", "X-CSRFToken": root.querySelector('[name="csrfmiddlewaretoken"]').value}, body: JSON.stringify({error_ids: errorIds, risk_code_id: form.elements.risk_code_id.value, note: form.elements.note.value})});
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "Không thể mapping mã lỗi.");
      window.campaignToast?.(data.message, "success"); window.location.reload();
    } catch (error) { feedback.textContent = error.message; }
    finally { button.disabled = false; }
  });
});
