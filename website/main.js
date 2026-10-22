"use strict";

const status = document.querySelector(".copy-status");
const timers = new WeakMap();

for (const button of document.querySelectorAll("[data-copy]")) {
  if (!navigator.clipboard?.writeText) continue;
  button.hidden = false;

  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(button.dataset.copy);
      clearTimeout(timers.get(button));
      button.textContent = "[copied]";
      status.textContent = "Copied.";
      timers.set(button, setTimeout(() => { button.textContent = "[copy]"; }, 2000));
    } catch {
      status.textContent = "Copy failed. Select the command and copy it manually.";
    }
  });
}
