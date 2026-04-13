/**
 * main.js — Hospital Queue Optimisation System
 * Global utilities and enhancements
 */

// Auto-dismiss flash alerts after 4 seconds
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".alert-dismissible").forEach(el => {
    setTimeout(() => {
      el.classList.remove("show");
      setTimeout(() => el.remove(), 300);
    }, 4000);
  });

  // Tooltip init (Bootstrap 5)
  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
    new bootstrap.Tooltip(el);
  });
});

/**
 * Formats a number with comma (Indian style: 12,34,567)
 */
function formatIndian(n) {
  return n.toLocaleString("en-IN");
}

/**
 * Returns a severity color class
 */
function severityColor(s) {
  return ["", "success", "info", "warning", "orange", "danger"][s] || "secondary";
}