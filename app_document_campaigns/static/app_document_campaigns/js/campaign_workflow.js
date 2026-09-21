(function () {
  document.querySelectorAll("[data-dataset-open]").forEach(button => button.addEventListener("click", () => {
    document.querySelector('[data-dataset-dialog="' + button.dataset.datasetOpen + '"]')?.showModal();
  }));
  document.querySelectorAll("[data-dataset-dialog]").forEach(dialog => {
    dialog.querySelectorAll("[data-dataset-close]").forEach(button => button.addEventListener("click", () => dialog.close()));
    dialog.addEventListener("click", event => {
      const rect = dialog.getBoundingClientRect();
      if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
    });
  });
  const sourcesForm = document.querySelector("[data-dataset-sources]");
  if (sourcesForm) {
    const all = sourcesForm.querySelector("[data-sources-all]"), choices = [...sourcesForm.querySelectorAll('[name="sources"]')];
    all.addEventListener("change", () => { choices.forEach(choice => choice.checked = all.checked); all.indeterminate = false; });
    choices.forEach(choice => choice.addEventListener("change", () => {
      all.checked = choices.every(item => item.checked);
      all.indeterminate = choices.some(item => item.checked) && !all.checked;
      sourcesForm.querySelector("[data-sources-error]").hidden = true;
    }));
    sourcesForm.addEventListener("submit", event => {
      if (!choices.some(choice => choice.checked)) { event.preventDefault(); sourcesForm.querySelector("[data-sources-error]").hidden = false; return; }
      const submit = sourcesForm.querySelector('button:not([type="button"])');
      submit.disabled = true; submit.textContent = "Đang gửi yêu cầu…";
    });
  }
  const uploadForm = document.querySelector("[data-dataset-upload]");
  if (uploadForm) {
    const input = uploadForm.querySelector("[data-dataset-file]"), zone = uploadForm.querySelector("[data-dataset-drop]");
    const submit = uploadForm.querySelector("[data-upload-submit]"), error = uploadForm.querySelector("[data-upload-error]");
    const showFile = () => {
      const file = input.files[0];
      const valid = file && file.name.toLowerCase().endsWith(".xlsx") && file.size > 0 && file.size <= 10 * 1024 * 1024;
      submit.disabled = !valid; error.hidden = !file || valid;
      error.textContent = "Chọn một file .xlsx không rỗng, tối đa 10 MB.";
      uploadForm.querySelector("[data-upload-name]").textContent = file ? file.name : "Excel .xlsx · tối đa 10 MB";
      return valid;
    };
    input.addEventListener("change", showFile);
    zone.addEventListener("dragover", event => {event.preventDefault(); zone.classList.add("is-dragging");});
    zone.addEventListener("dragleave", () => zone.classList.remove("is-dragging"));
    zone.addEventListener("drop", event => {
      event.preventDefault(); zone.classList.remove("is-dragging");
      if (event.dataTransfer.files.length !== 1) {input.value = ""; submit.disabled = true; uploadForm.querySelector("[data-upload-name]").textContent = "Excel .xlsx · tối đa 10 MB"; error.textContent = "Vui lòng chọn đúng một file."; error.hidden = false; return;}
      input.files = event.dataTransfer.files; showFile();
    });
    uploadForm.addEventListener("submit", event => {
      if (!showFile()) {event.preventDefault(); return;}
      submit.disabled = true; submit.textContent = "Đang upload…";
    });
  }
  const job = document.querySelector("[data-import-job]");
  if (!job) return;

  const statusUrl = job.dataset.statusUrl;
  const statusLabel = job.querySelector("[data-job-status]");
  const progressValue = document.querySelector("[data-job-progress]");
  const messageBox = job.querySelector("[data-job-message]");
  const errorBox = job.querySelector("[data-job-error]");
  let status = job.dataset.status;

  const poll = async () => {
    if (!statusUrl || !["queued", "running"].includes(status)) return;
    try {
      const response = await fetch(statusUrl, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("status_request_failed");
      const payload = await response.json();
      if (!payload.job) return;
      status = payload.job.status;
      statusLabel.textContent = payload.job.status_label;
      if (progressValue) {
        progressValue.style.width = `${payload.job.progress}%`;
        progressValue.parentElement.setAttribute("aria-valuenow", payload.job.progress);
        progressValue.parentElement.classList.toggle("is-active", ["queued", "running"].includes(status));
      }
      if (payload.job.summary && payload.job.summary.message) {
        messageBox.textContent = payload.job.summary.message;
        messageBox.hidden = false;
        job.hidden = false;
      }
      if (payload.job.error) {
        errorBox.textContent = payload.job.error;
        errorBox.hidden = false;
        job.hidden = false;
      }
      if (["succeeded", "failed"].includes(status)) {
        window.setTimeout(() => window.location.reload(), 700);
        return;
      }
    } catch (_) {
      statusLabel.textContent = "Mất kết nối khi kiểm tra tiến độ — đang thử lại";
      statusLabel.hidden = false;
      job.hidden = false;
    }
    window.setTimeout(poll, 2000);
  };

  window.setTimeout(poll, 800);
})();
