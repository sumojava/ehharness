const log = document.getElementById("log");
const form = document.getElementById("composer");
const input = document.getElementById("input");
const send = document.getElementById("send");
const modelSelect = document.getElementById("model");
const clearBtn = document.getElementById("clear");

// The whole conversation lives in memory for this tab only. Nothing is written
// to disk or sent anywhere except the Claude API request itself.
let history = [];

function addMessage(role, text, usage) {
  const wrap = document.createElement("div");
  wrap.className = "msg";

  const who = document.createElement("span");
  who.className = "who";
  who.textContent = role === "user" ? "You" : "Claude";

  // textContent, never innerHTML: model output is untrusted text.
  const body = document.createElement("div");
  body.textContent = text;

  wrap.append(who, body);

  if (usage) {
    const u = document.createElement("p");
    u.className = "usage";
    u.textContent = `${usage.input_tokens} tokens in, ${usage.output_tokens} tokens out`;
    wrap.append(u);
  }

  log.append(wrap);
  log.scrollTop = log.scrollHeight;
  return wrap;
}

function setBusy(busy) {
  send.disabled = busy;
  input.disabled = busy;
  send.textContent = busy ? "Sending..." : "Send";
}

async function loadModels() {
  try {
    const res = await fetch("/api/models");
    const data = await res.json();
    for (const id of data.claude) {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = id;
      modelSelect.append(opt);
    }
  } catch {
    modelSelect.innerHTML = "";
    const opt = document.createElement("option");
    opt.textContent = "Could not load models";
    modelSelect.append(opt);
  }
}

async function sendMessage(text) {
  history.push({ role: "user", content: text });
  addMessage("user", text);
  setBusy(true);

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: "anthropic",
        model: modelSelect.value,
        messages: history,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      // Roll back the unsent turn so the conversation stays valid.
      history.pop();
      addMessage("assistant", `Error: ${data.error || "Something went wrong."}`);
      return;
    }
    history.push({ role: "assistant", content: data.text });
    addMessage("assistant", data.text, data.usage);
  } catch {
    history.pop();
    addMessage("assistant", "Error: could not reach the local server.");
  } finally {
    setBusy(false);
    input.focus();
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  sendMessage(text);
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

clearBtn.addEventListener("click", () => {
  history = [];
  log.textContent = "";
  input.focus();
});

loadModels();
