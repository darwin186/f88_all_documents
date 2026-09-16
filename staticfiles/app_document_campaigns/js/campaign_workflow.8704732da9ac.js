(function () {
  const job = document.querySelector("[data-import-job]");
  if (!job) return;

  const statusUrl = job.dataset.statusUrl;
  const statusLabel = job.querySelector("[data-job-status]");
  const progressValue = job.querySelector("[data-job-progress]");
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
      progressValue.style.width = `${payload.job.progress}%`;
      if (payload.job.error) {
        errorBox.textContent = payload.job.error;
        errorBox.hidden = false;
      }
      if (["succeeded", "failed"].includes(status)) {
        window.setTimeout(() => window.location.reload(), 700);
        return;
      }
    } catch (_) {
      statusLabel.textContent = "Mất kết nối khi kiểm tra tiến độ — đang thử lại";
    }
    window.setTimeout(poll, 2000);
  };

  window.setTimeout(poll, 800);
})();
