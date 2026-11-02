"use strict";
document.querySelectorAll(".ai-request").forEach(button => {
  button.addEventListener("click", async () => {
    const area = button.closest(".category-tools");
    const status = area.querySelector(".ai-status");
    const review = area.querySelector(".ai-review");
    review.hidden = true;
    button.disabled = true;
    status.textContent = "Requesting a suggestion. Your note is already saved.";
    try {
      const response = await fetch(button.dataset.url, {
        method: "POST", headers: {"X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content}
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "The request could not be completed.");
      if (result.status === "suggested") {
        review.querySelector('[name="suggestion_id"]').value = result.suggestion_id;
        review.querySelector(".suggested-label").textContent = "Suggested category: " + result.category;
        status.textContent = "Review required. The suggested category has not been saved.";
        review.hidden = false;
      } else {
        const messages = {
          uncertain: "Category uncertain. The saved category is unchanged. Choose a category manually if appropriate.",
          timeout: "AI did not respond within five seconds. Your note remains saved; choose a category manually or retry.",
          unavailable: "AI is unavailable. Your note remains saved; you can choose a category manually."
        };
        status.textContent = messages[result.status] || messages.unavailable;
      }
    } catch (error) {
      status.textContent = error.message + " Your saved note is unaffected.";
    } finally {
      button.disabled = false;
    }
  });
});
