let isListening = false;

const chat = document.getElementById("chat");
const form = document.getElementById("messageForm");
const input = document.getElementById("q");
const speakButton = document.getElementById("speakBtn");
const voiceStatus = document.getElementById("voiceStatus");

function add(text, kind, debugInfo = null) {
  const message = document.createElement("article");
  message.className = `msg ${kind}`;
  message.textContent = text;

  if (debugInfo) {
    const debug = document.createElement("small");
    debug.className = "debug-tag";
    debug.textContent =
      `source: ${debugInfo.nlu_source || "nlu"} | intent: ${debugInfo.intent} | ` +
      `entities: ${JSON.stringify(debugInfo.entities)}`;
    message.appendChild(debug);
  }
  chat.appendChild(message);
  chat.scrollTop = chat.scrollHeight;
}

async function sendMsg() {
  const text = input.value.trim();
  if (!text) return;

  add(text, "user");
  input.value = "";
  const sendButton = form.querySelector('button[type="submit"]');
  sendButton.disabled = true;

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text })
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "The request could not be completed.");
    }
    add(data.answer, "bot", data.debug);
    if (data.notice) add(data.notice, "bot");

    if (document.getElementById("speakBack").checked && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(data.answer));
    }
  } catch (error) {
    add(`Request failed: ${error.message}`, "bot");
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
}

async function resetChat() {
  try {
    const response = await fetch("/reset", { method: "POST" });
    if (!response.ok) throw new Error("Could not reset the conversation.");
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    chat.replaceChildren();
    add("Conversation context cleared. Type or use the microphone!", "bot");
  } catch (error) {
    add(error.message, "bot");
  }
}

function listen() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    add("Speech recognition is not supported in this browser.", "bot");
    return;
  }
  if (isListening) return;

  const recognition = new SpeechRecognition();
  recognition.lang = "en-IN";
  recognition.continuous = false;
  recognition.interimResults = false;

  let sent = false;
  isListening = true;
  speakButton.disabled = true;
  speakButton.classList.add("listening");
  speakButton.textContent = "Listening...";
  voiceStatus.textContent = "Listening (en-IN)...";

  recognition.onresult = event => {
    const finalResult = event.results[event.results.length - 1];
    if (!finalResult || !finalResult.isFinal || sent) return;
    sent = true;
    input.value = finalResult[0].transcript;
    recognition.stop();
    sendMsg();
  };
  recognition.onerror = event => {
    add(`Voice input error: ${event.error}`, "bot");
  };
  recognition.onend = () => {
    isListening = false;
    speakButton.disabled = false;
    speakButton.classList.remove("listening");
    speakButton.textContent = "Speak";
    voiceStatus.textContent = "";
  };

  try {
    recognition.start();
  } catch (error) {
    isListening = false;
    speakButton.disabled = false;
    speakButton.classList.remove("listening");
    speakButton.textContent = "Speak";
    voiceStatus.textContent = "";
    add(`Could not start speech recognition: ${error.message}`, "bot");
  }
}

form.addEventListener("submit", event => {
  event.preventDefault();
  sendMsg();
});
document.getElementById("resetBtn").addEventListener("click", resetChat);
speakButton.addEventListener("click", listen);
add("Hello! You can use the microphone or type your question.", "bot");
