document.addEventListener("DOMContentLoaded", () => {
  const csrf = document.querySelector("[data-csrf-token] input[name=csrfmiddlewaretoken]")?.value;
  document.querySelectorAll("[data-area-confirm]").forEach(row => {
    const button = row.querySelector("button");
    const decision = row.querySelector("select");
    const note = row.querySelector("textarea");
    const feedback = row.querySelector("small");
    button.addEventListener("click", async () => {
      if (!decision.value) {
        feedback.textContent = "Vui lòng chọn phản hồi QLKV.";
        feedback.classList.add("is-error");
        decision.focus();
        return;
      }
      if (!window.confirm(`Lưu kết luận “${decision.selectedOptions[0].textContent}” cho dòng này?`)) return;
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
            decision: decision.value,
            note: note.value,
            expected_confirmation_id: row.dataset.confirmationId ? Number(row.dataset.confirmationId) : null,
          }),
        });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || "Không lưu được xác nhận.");
        row.dataset.confirmationId = String(data.confirmation_id);
        button.textContent = "Lưu lại kết luận";
        feedback.textContent = `Đã lưu · tiến độ ${data.completed}/${data.total} dòng`;
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
