const filters = [...document.querySelectorAll(".filter")];
const cards = [...document.querySelectorAll(".support-card")];
const status = document.querySelector("#results-status");
const toast = document.querySelector("#toast");
let toastTimer;

function updateFilterCounts() {
  filters.forEach((button) => {
    const filter = button.dataset.filter;
    const count = filter === "all"
      ? cards.length
      : cards.filter((card) => card.dataset.categories.split(" ").includes(filter)).length;

    const label = button.dataset.label || button.textContent.replace(/（\d+件）/g, "").trim();
    button.dataset.label = label;
    button.textContent = `${label}（${count}件）`;
  });
}

function clearActiveFilters() {
  filters.forEach((button) => {
    button.classList.remove("is-active");
    button.setAttribute("aria-pressed", "false");
  });
}

function hideAllCards() {
  clearActiveFilters();
  cards.forEach((card) => { card.hidden = true; });
  status.textContent = "困りごとを選んでください。全部確認したい場合は、一番上の「すべての支援を見る」を押してください。";
}

function setFilter(selectedFilter) {
  let visibleCount = 0;
  clearActiveFilters();
  selectedFilter.classList.add("is-active");
  selectedFilter.setAttribute("aria-pressed", "true");

  cards.forEach((card) => {
    const categories = card.dataset.categories.split(" ");
    const visible = selectedFilter.dataset.filter === "all" || categories.includes(selectedFilter.dataset.filter);
    card.hidden = !visible;
    if (visible) visibleCount += 1;
  });

  status.textContent = selectedFilter.dataset.filter === "all"
    ? `すべての支援 ${visibleCount}件を表示しています`
    : `関係しそうな支援 ${visibleCount}件を表示しています`;
}

function showCardFromHash() {
  if (!location.hash) return false;
  const target = document.querySelector(location.hash);
  if (!target || !target.classList.contains("support-card")) return false;
  clearActiveFilters();
  cards.forEach((card) => { card.hidden = card !== target; });
  status.textContent = "選んだ支援を表示しています";
  return true;
}

updateFilterCounts();

filters.forEach((button) => {
  button.addEventListener("click", () => setFilter(button));
});

if (!showCardFromHash()) hideAllCards();
window.addEventListener("hashchange", () => { showCardFromHash(); });

function showToast(message) {
  window.clearTimeout(toastTimer);
  toast.textContent = message;
  toast.hidden = false;
  toastTimer = window.setTimeout(() => { toast.hidden = true; }, 2400);
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
      showToast("コピーできませんでした。URLを表示して長押ししてください");
    }
  });
});
