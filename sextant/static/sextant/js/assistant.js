/* Minimal SSE chat client for the Sextant assistant.
 *
 * EventSource only supports GET, so we POST with fetch() and parse the
 * text/event-stream body from the ReadableStream ourselves.
 */
(function () {
  "use strict";

  var log = document.getElementById("sextant-log");
  var form = document.getElementById("sextant-form");
  var input = document.getElementById("sextant-input");
  var sendBtn = document.getElementById("sextant-send");

  // Conversation history sent to the server each turn (user/assistant text only).
  var history = [];

  function getCookie(name) {
    var m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return m ? m.pop() : "";
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function addBubble(role) {
    var bubble = el("div", "sextant-msg sextant-" + role);
    log.appendChild(bubble);
    log.scrollTop = log.scrollHeight;
    return bubble;
  }

  function addToolNote(name, isError) {
    var note = el("div", "sextant-tool" + (isError ? " sextant-tool-error" : ""),
      (isError ? "⚠ tool " : "→ ") + name);
    log.appendChild(note);
    log.scrollTop = log.scrollHeight;
  }

  function setBusy(busy) {
    sendBtn.disabled = busy;
    input.disabled = busy;
  }

  function handleEvent(evt, assistantBubble) {
    switch (evt.type) {
      case "token":
        assistantBubble.textContent += evt.text;
        log.scrollTop = log.scrollHeight;
        break;
      case "tool_call":
        addToolNote(evt.name, false);
        break;
      case "tool_result":
        if (evt.is_error) addToolNote(evt.name + " (error)", true);
        break;
      case "error":
        assistantBubble.classList.add("sextant-error");
        assistantBubble.textContent += "\n[error] " + evt.message;
        break;
      case "done":
        break;
    }
  }

  function send(message) {
    history.push({ role: "user", content: message });
    addBubble("user").textContent = message;

    var assistantBubble = addBubble("assistant");
    setBusy(true);

    fetch(window.SEXTANT_STREAM_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken")
      },
      body: JSON.stringify({ messages: history })
    }).then(function (resp) {
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      var reader = resp.body.getReader();
      var decoder = new TextDecoder();
      var buffer = "";

      function pump() {
        return reader.read().then(function (r) {
          if (r.done) {
            history.push({ role: "assistant", content: assistantBubble.textContent });
            setBusy(false);
            return;
          }
          buffer += decoder.decode(r.value, { stream: true });
          var frames = buffer.split("\n\n");
          buffer = frames.pop(); // keep incomplete trailing frame
          frames.forEach(function (frame) {
            var line = frame.trim();
            if (line.indexOf("data:") !== 0) return;
            try {
              handleEvent(JSON.parse(line.slice(5).trim()), assistantBubble);
            } catch (e) { /* ignore malformed frame */ }
          });
          return pump();
        });
      }
      return pump();
    }).catch(function (err) {
      assistantBubble.classList.add("sextant-error");
      assistantBubble.textContent += "\n[error] " + err.message;
      setBusy(false);
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var msg = input.value.trim();
    if (!msg) return;
    input.value = "";
    send(msg);
  });

  // Example chips prefill the box.
  Array.prototype.forEach.call(
    document.querySelectorAll(".sextant-example"),
    function (btn) {
      btn.addEventListener("click", function () {
        input.value = btn.textContent;
        input.focus();
      });
    });
})();
