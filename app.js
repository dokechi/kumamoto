const filters = [...document.querySelectorAll(".filter")];
const cards = [...document.querySelectorAll(".support-card")];
const status = document.querySelector("#results-status");
const toast = document.querySelector("#toast");
let toastTimer;

function setFilter(selectedFilter) {
  let visibleCount = 0;

  filters.forEach((button) => {
    const active = button === selectedFilter;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  });

  cards.forEach((card) => {
    const categories = card.dataset.categories.split(" ");
    const visible = selectedFilter.dataset.filter === "all" || categories.includes(selectedFilter.dataset.filter);
    card.hidden = !visible;
    if (visible) visibleCount += 1;
  });

  status.textContent = `${visibleCount}件の支援を表示しています`;
}

filters.forEach((button) => {
  button.addEventListener("click", () => setFilter(button));
});

function showToast(message) {
  window.clearTimeout(toastTimer);
  toast.textContent = message;
  toast.hidden = false;
  toastTimer = window.setTimeout(() => {
    toast.hidden = true;
  }, 2400);
}

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("copy failed");
}

document.querySelectorAll(".copy-link").forEach((button) => {
  button.addEventListener("click", async () => {
    try {
      await copyText(button.dataset.copyUrl);
      showToast("URLをコピーしました");
    } catch {
      showToast("コピーできませんでした。表示URLを長押ししてください");
    }
  });
});
