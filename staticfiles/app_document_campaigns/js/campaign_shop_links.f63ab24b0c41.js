document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-issue-link]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (form.dataset.hasLink === "true" && !window.confirm("Đổi link sẽ vô hiệu link cũ của PGD. Tiếp tục?")) return;

      const row = form.closest("[data-shop-link-row]");
      const button = form.querySelector("button[type='submit']");
      const result = row.querySelector("[data-link-result]");
      const urlInput = row.querySelector("[data-link-url]");
      const feedback = row.querySelector("[data-link-feedback]");
      const status = row.querySelector("[data-link-status]");
      button.disabled = true;
      feedback.textContent = "Đang tạo link…";
      feedback.classList.remove("is-error", "is-success");

      try {
        const response = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: { "X-Requested-With": "XMLHttpRequest" },
          credentials: "same-origin",
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) throw new Error(payload.error || "Không thể tạo link.");

        urlInput.value = payload.url;
        result.hidden = false;
        feedback.textContent = "Link mới chỉ hiện trong lần này. Hãy copy và gửi đúng PGD.";
        feedback.classList.add("is-success");
        status.innerHTML = `<span class="dec-link-status is-issued">Đã phát hành</span><small>${payload.created_at}</small>`;
        form.dataset.hasLink = "true";
        button.textContent = "Đổi link";
        button.classList.remove("dec-btn-primary");
        button.classList.add("dec-btn-secondary");
      } catch (error) {
        feedback.textContent = error.message;
        feedback.classList.add("is-error");
      } finally {
        button.disabled = false;
      }
    });
  });

  document.querySelectorAll("[data-copy-link]").forEach((button) => {
    button.addEventListener("click", async () => {
      const result = button.closest("[data-link-result]");
      const input = result.querySelector("[data-link-url]");
      const feedback = result.parentElement.querySelector("[data-link-feedback]");
      try {
        await navigator.clipboard.writeText(input.value);
      } catch (_) {
        input.select();
        document.execCommand("copy");
      }
      button.textContent = "Đã copy";
      feedback.textContent = "Đã copy link vào clipboard.";
      feedback.classList.add("is-success");
      window.setTimeout(() => { button.textContent = "Copy link"; }, 1800);
    });
  });
});
