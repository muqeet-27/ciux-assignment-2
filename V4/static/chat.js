async function sendMsg() {
  const q = document.getElementById("q");
  const text = q.value.trim();
  if (!text) return;

  addMessage(text, "user");
  q.value = "";

  const r = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text })
  });
  const d = await r.json();
  addMessage(d.answer, "bot", d.debug);
}

async function resetChat() {
  await fetch("/reset", { method: "POST" });
  document.getElementById("chat").innerHTML = "";
  addMessage("Conversation context cleared. Start a new question!", "bot");
}

function addMessage(text, cls, debugInfo = null) {
  const e = document.createElement("div");
  e.className = "msg " + cls;
  e.textContent = text;
  if (debugInfo) {
    const dbg = document.createElement("div");
    dbg.className = "debug-tag";
    dbg.textContent = `source: ${debugInfo.nlu_source || 'nlu'} | intent: ${debugInfo.intent} | entities: ${JSON.stringify(debugInfo.entities)}`;
    e.appendChild(dbg);
  }
  document.getElementById("chat").appendChild(e);
  e.scrollIntoView();
}

document.getElementById("q").addEventListener("keydown", e => {
  if (e.key === "Enter") sendMsg();
});

addMessage("Hello! Ask a question or follow up across turns.", "bot");
