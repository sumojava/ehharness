const container = document.getElementById("providers");

function setStatus(el, text, ok) {
  el.textContent = text;
  el.className = ok ? "status ok" : "status error";
}

function renderProvider(id, info) {
  const card = document.createElement("div");
  card.className = "card";

  const title = document.createElement("h2");
  title.textContent = info.label;

  const status = document.createElement("p");
  status.className = info.saved ? "status ok" : "status";
  status.textContent = info.saved ? "Key saved" : "No key saved";

  const form = document.createElement("form");
  const input = document.createElement("input");
  input.type = "password";
  input.placeholder = info.saved ? "Paste a new key to replace" : "Paste your API key";
  input.autocomplete = "off";
  input.spellcheck = false;

  const save = document.createElement("button");
  save.type = "submit";
  save.textContent = "Save key";

  const test = document.createElement("button");
  test.type = "button";
  test.className = "secondary";
  test.textContent = "Test connection";
  test.disabled = !info.saved;

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "secondary";
  remove.textContent = "Remove";
  remove.disabled = !info.saved;

  const result = document.createElement("p");
  result.className = "status";

  form.append(input, save, test, remove);

  test.addEventListener("click", async () => {
    test.disabled = true;
    result.textContent = "Testing...";
    result.className = "status";
    try {
      const res = await fetch("/api/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: id }),
      });
      const data = await res.json();
      setStatus(result, data.message, data.ok);
    } catch {
      setStatus(result, "Test failed. Is the server running?", false);
    } finally {
      test.disabled = false;
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const key = input.value;
    input.value = "";
    const res = await fetch("/api/key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: id, key }),
    });
    const data = await res.json();
    if (res.ok) {
      setStatus(status, "Key saved", true);
      remove.disabled = false;
      test.disabled = false;
    } else {
      setStatus(status, data.error || "Could not save", false);
    }
  });

  remove.addEventListener("click", async () => {
    const res = await fetch("/api/key/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: id }),
    });
    if (res.ok) {
      setStatus(status, "No key saved", false);
      remove.disabled = true;
    }
  });

  card.append(title, status, form, result);
  container.append(card);
}

fetch("/api/providers")
  .then((r) => r.json())
  .then((providers) => {
    for (const [id, info] of Object.entries(providers)) {
      renderProvider(id, info);
    }
  })
  .catch(() => {
    container.textContent = "Could not load settings. Is the server running?";
  });
