// app.js — small conveniences. Every page still works without this file.

// Copy button: <button data-copy="ip-output"> copies the text of the element
// with id "ip-output" to the clipboard. One listener on the whole page
// ("event delegation") also covers buttons that htmx adds later.
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;
  const source = document.getElementById(button.dataset.copy);
  if (!source) return;

  const label = button.textContent;
  try {
    // The clipboard API works on http://127.0.0.1 because browsers treat the
    // local machine as a "secure context".
    await navigator.clipboard.writeText(source.value);
    button.textContent = "Copied";
  } catch (error) {
    // Clipboard blocked (rare): select the text so Ctrl+C works.
    source.select();
    button.textContent = "Press Ctrl+C";
  }
  setTimeout(() => { button.textContent = label; }, 1500);
});
