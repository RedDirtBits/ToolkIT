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
    // A text box has a .value; any other element (a <span> in the subnet
    // calculator's table) gives its text instead.
    const text = "value" in source ? source.value : source.textContent;
    await navigator.clipboard.writeText(text);
    button.textContent = "Copied";
  } catch (error) {
    // Clipboard blocked (rare): select the text so Ctrl+C works.
    if (source.select) {
      source.select();
    } else {
      window.getSelection().selectAllChildren(source);
    }
    button.textContent = "Press Ctrl+C";
  }
  setTimeout(() => { button.textContent = label; }, 1500);
});

// Clear button: <button type="reset"> already puts the form's fields back to
// their defaults (that's built into HTML). This adds the part HTML can't do:
// emptying the same tab's result area, then putting the cursor in the first
// field, ready for the next input. Without JavaScript, the fields still reset.
document.addEventListener("reset", (event) => {
  const tool = event.target.closest(".tool");
  if (!tool) return;
  // A tab with several forms (OUI lookup) names each form's result area in
  // data-result; otherwise the tab's one result area is used.
  const resultId = event.target.dataset.result;
  const result = resultId ? document.getElementById(resultId) : tool.querySelector(".result");
  if (result) result.innerHTML = "";
  // The "reset" event fires just BEFORE the fields are reset, so wait a
  // moment (setTimeout 0 = "right after this") before moving the cursor.
  setTimeout(() => {
    const first = event.target.querySelector("textarea, input:not([type=hidden]):not([type=radio]):not([type=checkbox])");
    if (first) first.focus();
  }, 0);
});

// Enter submits: in a <textarea data-enter-submits> (the OUI lookup box),
// Enter looks it up, like a search box; Shift+Enter still starts a new line.
// Pasting several lines isn't affected (a paste isn't a key press).
// requestSubmit() fires the form's normal "submit" event, which htmx listens
// for, so it behaves exactly like clicking the button.
document.addEventListener("keydown", (event) => {
  const box = event.target.closest("textarea[data-enter-submits]");
  if (!box || event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  box.form.requestSubmit();
});

// Safety net for errors. Each tool reports the problems it expects (a bad
// count, a missing file) as a normal result with a message. Anything else, an
// unexpected bug (HTTP 500) or the app not answering at all (its console
// window was closed), would otherwise do nothing visible: htmx only swaps in
// successful responses, so the button would just seem dead. These two htmx
// events fire in exactly those cases; we show a message where the result
// would have gone instead.
//   htmx:responseError  the app answered, but with an error status (4xx/5xx)
//   htmx:sendError      no answer at all (app stopped, connection refused)
function showRequestError(target, message) {
  if (!target) return;
  const flash = document.createElement("div");
  flash.className = "flash bad request-error";
  // textContent, never innerHTML: the message is shown as plain text.
  flash.textContent = message;
  if (target.classList.contains("result")) {
    // A tool's result area: replace whatever was there (an old result).
    target.replaceChildren(flash);
  } else {
    // Anything else (the OUI list panel, whose buttons must stay usable):
    // put the message at the top, replacing an earlier one if there is one.
    const old = target.querySelector(":scope > .request-error");
    if (old) old.remove();
    target.prepend(flash);
  }
}

document.addEventListener("htmx:responseError", (event) => {
  const status = event.detail.xhr.status;
  showRequestError(event.detail.target,
    `Something went wrong (HTTP ${status}). The details are in ToolkIT's console window. ` +
    "Try again; if it keeps happening, restart ToolkIT.");
});

document.addEventListener("htmx:sendError", (event) => {
  showRequestError(event.detail.target,
    "ToolkIT didn't answer. Is its console window still open? If not, start it again " +
    "(run.bat, or python -m app).");
});
