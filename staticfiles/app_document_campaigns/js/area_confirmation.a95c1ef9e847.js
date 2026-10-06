document.addEventListener("DOMContentLoaded", () => {
  const csrf = document.querySelector("[data-csrf-token] input[name=csrfmiddlewaretoken]")?.value;
  document.querySelectorAll("[data-area-confirm]").forEach(row => {
    const button = row.querySelector("button");
    const note = row.querySelector("textarea");
    const feedback = row.querySelector("small");
    button.addEventListener("click", async () => {
      if (!window.confirm("Xác nhận đây là lỗi chính thức sau Team review?")) return;
      button.disabled = true;
      const oldLabel = button.textContent;
      button.textContent = "Đang lưu…";
      feedback.classList.remove("is-error");
      try {
        const response = await fetch(row.dataset.url, {
          method: "POST",
          credentials: "same-origin",
          headers: {"Content-Type": "application/json", "X-CSRFToken": csrf || "", "Accept": "application/json"},
          body: JSON.stringify({
            decision: "confirmed",
            note: note.value,
            expected_confirmation_id: row.dataset.confirmationId ? Number(row.dataset.confirmationId) : null,
          }),
        });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || "Không lưu được xác nhận.");
        row.dataset.confirmationId = String(data.confirmation_id);
        button.textContent = "Lưu lại xác nhận";
        feedback.textContent = `Đã xác nhận · tiến độ ${data.completed}/${data.total} dòng`;
      } catch (error) {
        button.textContent = oldLabel;
        feedback.textContent = error.message;
        feedback.classList.add("is-error");
      } finally {
        button.disabled = false;
      }
    });
  });
});
