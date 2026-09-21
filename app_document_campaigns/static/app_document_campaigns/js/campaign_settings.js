document.addEventListener("DOMContentLoaded", () => {
  const dialog = document.querySelector("[data-campaign-settings]");
  if (!dialog) return;

  const openDialog = () => {
    if (!dialog.open) dialog.showModal();
  };
  const closeDialog = () => dialog.close();

  document.querySelectorAll("[data-open-campaign-settings]").forEach((button) => {
    button.addEventListener("click", openDialog);
  });
  dialog.querySelectorAll("[data-close-campaign-settings]").forEach((button) => {
    button.addEventListener("click", closeDialog);
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) closeDialog();
  });
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeDialog();
  });
  if (dialog.hasAttribute("data-open-on-load") || new URLSearchParams(window.location.search).get("settings") === "1") openDialog();
});
