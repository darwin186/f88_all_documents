document.addEventListener("DOMContentLoaded", () => {
  let latestBulkLinks = [];

  document.querySelectorAll("[data-publish-shop-links]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const replacing = form.dataset.hasLinks === "true";
      const question = replacing
        ? "Tạo lại toàn bộ link sẽ vô hiệu tất cả link PGD hiện tại. Tiếp tục?"
        : "Phát hành chiến dịch và tạo unique link cho toàn bộ PGD? Thao tác này chưa gửi email.";
      if (!window.confirm(question)) return;

      const allForms = document.querySelectorAll("[data-publish-shop-links]");
      const feedback = document.querySelector("[data-publish-feedback]");
      allForms.forEach((item) => {
        const button = item.querySelector("button");
        button.disabled = true;
        button.dataset.previousText = button.textContent;
        button.textContent = "Đang tạo link PGD…";
      });
      if (feedback) {
        feedback.textContent = "Đang tạo link riêng cho từng PGD, vui lòng giữ nguyên trang…";
        feedback.classList.remove("is-error", "is-success");
      }

      try {
        const response = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: { "X-Requested-With": "XMLHttpRequest" },
          credentials: "same-origin",
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) throw new Error(payload.error || "Không thể phát hành tới PGD.");

        latestBulkLinks = payload.links;
        window.campaignToast?.(`Đã phát hành ${payload.count} link PGD.`, "success");
        payload.links.forEach((item) => {
          const row = document.querySelector(`[data-shop-link-row][data-shop-id="${item.shop_id}"]`);
          if (!row) return;
          const input = row.querySelector("[data-link-url]");
          const result = row.querySelector("[data-link-result]");
          const status = row.querySelector("[data-link-status]");
          const issueForm = row.querySelector("[data-issue-link]");
          input.value = item.url;
          result.hidden = false;
          status.innerHTML = '<span class="dec-link-status is-issued">Đã phát hành</span><small>Vừa tạo</small>';
          issueForm.dataset.hasLink = "true";
          if (!row.querySelector(".crm-status")?.classList.contains("submitted")) {
            row.querySelector("[data-email-link] button")?.removeAttribute("disabled");
            row.querySelector("[data-extend-deadline]")?.removeAttribute("disabled");
          }
          const issueButton = issueForm.querySelector("button");
          issueButton.textContent = "Đổi link";
          issueButton.classList.remove("dec-btn-primary");
          issueButton.classList.add("dec-btn-secondary");
        });
        allForms.forEach((item) => {
          item.dataset.hasLinks = "true";
          item.querySelector("button").textContent = "Tạo lại toàn bộ link";
        });
        const campaignStatus = document.querySelector("[data-campaign-status]");
        if (campaignStatus) campaignStatus.textContent = payload.status_label;
        const copyAll = document.querySelector("[data-copy-all-links]");
        if (copyAll) copyAll.hidden = false;
        if (feedback) {
          feedback.textContent = `Đã phát hành và tạo ${payload.count} link PGD. Hãy copy link trước khi tải lại trang.`;
          feedback.classList.add("is-success");
        }
        document.querySelector("#pgd-links")?.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (error) {
        window.campaignToast?.(error.message, "error");
        if (feedback) {
          feedback.textContent = error.message;
          feedback.classList.add("is-error");
        }
      } finally {
        allForms.forEach((item) => {
          const button = item.querySelector("button");
          if (button.textContent === "Đang tạo link PGD…") {
            button.textContent = button.dataset.previousText;
          }
          button.disabled = false;
        });
      }
    });
  });

  const copyAllButton = document.querySelector("[data-copy-all-links]");
  if (copyAllButton) {
    copyAllButton.addEventListener("click", async () => {
      const text = latestBulkLinks
        .map((item) => `${item.shop_code}\t${item.shop_name}\t${item.url}`)
        .join("\n");
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
      } catch (_) {
        const area = document.createElement("textarea");
        area.value = text;
        document.body.appendChild(area);
        area.select();
        document.execCommand("copy");
        area.remove();
      }
      copyAllButton.textContent = `Đã copy ${latestBulkLinks.length} link`;
      window.campaignToast?.(`Đã copy ${latestBulkLinks.length} link PGD.`, "success");
      window.setTimeout(() => { copyAllButton.textContent = "Copy toàn bộ link"; }, 2000);
    });
  }

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
        window.campaignToast?.("Đã tạo link mới cho PGD. Hãy copy để gửi.", "success");
        result.hidden = false;
        feedback.textContent = "Link mới chỉ hiện trong lần này. Hãy copy và gửi đúng PGD.";
        feedback.classList.add("is-success");
        status.innerHTML = `<span class="dec-link-status is-issued">Đã phát hành</span><small>${payload.created_at}</small>`;
        form.dataset.hasLink = "true";
        button.textContent = "Đổi link";
        button.classList.remove("dec-btn-primary");
        button.classList.add("dec-btn-secondary");
      } catch (error) {
        window.campaignToast?.(error.message, "error");
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
      window.campaignToast?.("Đã copy link vào clipboard.", "success");
      feedback.classList.add("is-success");
      window.setTimeout(() => { button.textContent = "Copy link"; }, 1800);
    });
  });
});
