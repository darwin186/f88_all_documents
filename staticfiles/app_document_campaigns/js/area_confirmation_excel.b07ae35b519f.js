document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("[data-area-confirmation-excel]");
  if (!root) return;
  const base = new URL(root.dataset.url, location.origin);
  const fileInput = root.querySelector("[data-area-excel-file]");
  const buttons = {export: root.querySelector("[data-area-excel-export]"), import: root.querySelector("[data-area-excel-import]")};
  const states = {export: root.querySelector("[data-area-excel-export-state]"), import: root.querySelector("[data-area-excel-import-state]")};
  const generations = {export: 0, import: 0};
  const csrf = root.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
  const fail = (kind, message) => { states[kind].textContent = message; window.campaignToast?.(message, "error"); };
  const poll = async (kind, id, notify, generation) => {
    if (generation !== generations[kind]) return;
    try {
      const response = await fetch(new URL(`${id}/`, base), {cache: "no-store"});
      const job = await response.json();
      if (!response.ok) throw new Error(job.error || "Không kiểm tra được tiến độ.");
      states[kind].replaceChildren();
      if (["queued", "running"].includes(job.status)) {
        buttons[kind].disabled = true;
        const spinner = document.createElement("i"); spinner.className = "area-excel-spinner";
        states[kind].append(spinner, `Đang xử lý · ${job.progress}%`);
        setTimeout(() => poll(kind, id, true, generation), 2000); return;
      }
      buttons[kind].disabled = false;
      if (job.status === "failed") return fail(kind, job.message);
      if (kind === "export" && job.download_url) {
        const link = document.createElement("a"); link.href = job.download_url; link.textContent = "↓ Tải file Excel";
        states[kind].append(link);
        if (notify) window.campaignToast?.("File xác nhận QLKV đã sẵn sàng.", "success");
      } else {
        states[kind].textContent = job.message;
        if (notify) { window.campaignToast?.(job.message, "success"); setTimeout(() => location.reload(), 800); }
      }
    } catch (error) {
      states[kind].textContent = "Mất kết nối — đang thử lại";
      setTimeout(() => poll(kind, id, notify, generation), 4000);
    }
  };
  const start = async (kind, file) => {
    const generation = ++generations[kind]; buttons[kind].disabled = true; states[kind].textContent = "Đang gửi yêu cầu…";
    const data = new FormData(); data.append("kind", kind); if (file) data.append("file", file);
    try {
      const response = await fetch(base, {method: "POST", headers: {"X-CSRFToken": csrf}, body: data});
      const result = await response.json(); if (!response.ok) throw new Error(result.error || "Không tạo được job.");
      poll(kind, result.id, true, generation);
    } catch (error) { buttons[kind].disabled = false; fail(kind, error.message); }
  };
  buttons.export.addEventListener("click", () => start("export"));
  buttons.import.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => { const file=fileInput.files[0]; fileInput.value=""; if (!file) return; if (!file.name.toLowerCase().endsWith(".xlsx") || file.size > 50*1024*1024) return fail("import", "Chọn file .xlsx tối đa 50 MB."); start("import", file); });
  const jobs = JSON.parse(document.getElementById("area-confirmation-excel-jobs").textContent);
  Object.entries(jobs).forEach(([kind,id]) => { if (id) poll(kind,id,false,generations[kind]); });
});
