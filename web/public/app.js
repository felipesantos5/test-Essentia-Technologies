// Web chat for the n8n attendance workflow. Text and voice messages are posted as
// multipart/form-data to the webhook (proxied by nginx, so the request is same-origin).

const WEBHOOK_URL = "/webhook/clinic-chat";
const SESSION_KEY = "essentia-chat-session-id";
const MAX_RECORDING_SECONDS = 60;
const RECORDING_FORMATS = [
  { mimeType: "audio/webm;codecs=opus", extension: "webm" },
  { mimeType: "audio/mp4", extension: "m4a" },
  { mimeType: "audio/ogg;codecs=opus", extension: "ogg" },
];

const elements = {
  messages: document.querySelector("#messages"),
  emptyState: document.querySelector("#empty-state"),
  composer: document.querySelector("#composer"),
  input: document.querySelector("#message-input"),
  sendButton: document.querySelector("#send-button"),
  recordButton: document.querySelector("#record-button"),
  recordingIndicator: document.querySelector("#recording-indicator"),
  recordingTimer: document.querySelector("#recording-timer"),
  cancelRecording: document.querySelector("#cancel-recording"),
  newConversation: document.querySelector("#new-conversation"),
  template: document.querySelector("#message-template"),
};

const state = { busy: false, recorder: null, recordingDiscarded: false, timerId: null };

function getSessionId() {
  try {
    let sessionId = sessionStorage.getItem(SESSION_KEY);
    if (!sessionId) {
      sessionId = crypto.randomUUID();
      sessionStorage.setItem(SESSION_KEY, sessionId);
    }
    return sessionId;
  } catch {
    state.fallbackSessionId ??= crypto.randomUUID();
    return state.fallbackSessionId;
  }
}

function resetSession() {
  try {
    sessionStorage.removeItem(SESSION_KEY);
  } catch {
    state.fallbackSessionId = undefined;
  }
  elements.messages.replaceChildren(elements.emptyState);
  elements.emptyState.hidden = false;
  elements.input.focus();
}

// ---------------------------------------------------------------- rendering

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (char) => `&#${char.charCodeAt(0)};`);
}

// Minimal, safe formatting for the agent's text replies: paragraphs, bullet lists and bold.
function formatReply(text) {
  const blocks = escapeHtml(text.trim()).split(/\n{2,}/);
  return blocks
    .map((block) => {
      const lines = block.split("\n");
      const bold = (line) => line.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
      if (lines.every((line) => /^\s*([-*•]|\d+[.)])\s+/.test(line))) {
        const items = lines.map((line) => `<li>${bold(line.replace(/^\s*([-*•]|\d+[.)])\s+/, ""))}</li>`);
        return `<ul>${items.join("")}</ul>`;
      }
      return `<p>${lines.map(bold).join("<br>")}</p>`;
    })
    .join("");
}

function timeLabel() {
  return new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function addMessage(role, { html = "", text = "", audioUrl = null, meta = timeLabel() } = {}) {
  elements.emptyState.hidden = true;
  const node = elements.template.content.firstElementChild.cloneNode(true);
  node.classList.add(`message--${role}`);
  const content = node.querySelector(".message__text");

  if (audioUrl) {
    const audio = document.createElement("audio");
    audio.className = "message__audio";
    audio.controls = true;
    audio.src = audioUrl;
    content.before(audio);
  }
  if (html) content.innerHTML = html;
  else content.textContent = text;

  node.querySelector(".message__meta").textContent = meta;
  elements.messages.append(node);
  node.scrollIntoView({ behavior: "smooth", block: "end" });
  return node;
}

function addTypingIndicator() {
  const node = addMessage("assistant", {
    html: '<span class="typing" aria-label="Assistente digitando"><span></span><span></span><span></span></span>',
    meta: "digitando…",
  });
  return () => node.remove();
}

function setBusy(busy) {
  state.busy = busy;
  elements.sendButton.disabled = busy;
  elements.recordButton.disabled = busy && !state.recorder;
  elements.input.disabled = busy;
  if (!busy) elements.input.focus();
}

// ---------------------------------------------------------------- networking

async function postMessage(formData) {
  formData.append("session_id", getSessionId());
  const response = await fetch(WEBHOOK_URL, { method: "POST", body: formData });
  const payload = await response.json().catch(() => null);
  if (!payload?.reply_text) {
    const detail = payload?.error?.message ?? `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return payload;
}

async function send(formData, userMessage) {
  if (state.busy) return;
  setBusy(true);
  const userNode = addMessage("user", userMessage);
  const removeTyping = addTypingIndicator();
  const startedAt = performance.now();

  try {
    const reply = await postMessage(formData);
    removeTyping();
    if (reply.transcript) {
      const caption = document.createElement("div");
      caption.className = "message__transcript";
      caption.textContent = `“${reply.transcript}”`;
      userNode.querySelector(".message__bubble").append(caption);
    }

    const seconds = ((performance.now() - startedAt) / 1000).toFixed(1);
    const audioUrl = reply.audio?.base64 ? `data:${reply.audio.mime_type};base64,${reply.audio.base64}` : null;
    // The workflow answers failures with a friendly reply_text plus an error code.
    const node = addMessage(reply.error ? "error" : "assistant", {
      html: formatReply(reply.reply_text),
      audioUrl,
      meta: `${timeLabel()} · ${seconds}s${audioUrl ? " · resposta em áudio" : ""}`,
    });
    if (audioUrl) {
      node.querySelector("audio").play().catch(() => {
        /* autoplay blocked: the player stays visible */
      });
    }
  } catch (error) {
    removeTyping();
    addMessage("error", { text: `Não foi possível falar com a assistente (${error.message}). Tente novamente.` });
  } finally {
    setBusy(false);
  }
}

function sendText(text) {
  const message = text.trim();
  if (!message) return;
  const formData = new FormData();
  formData.append("message", message);
  elements.input.value = "";
  autoResize();
  send(formData, { text: message });
}

// ---------------------------------------------------------------- recording

function pickRecordingFormat() {
  return RECORDING_FORMATS.find((format) => MediaRecorder.isTypeSupported(format.mimeType));
}

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    addMessage("error", { text: "Seu navegador não permite gravar áudio. Use a mensagem de texto." });
    return;
  }

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    addMessage("error", { text: "Permissão do microfone negada. Libere o acesso ou envie por texto." });
    return;
  }

  const format = pickRecordingFormat();
  const recorder = new MediaRecorder(stream, format ? { mimeType: format.mimeType } : undefined);
  const chunks = [];
  state.recorder = recorder;
  state.recordingDiscarded = false;

  recorder.addEventListener("dataavailable", (event) => event.data.size && chunks.push(event.data));
  recorder.addEventListener("stop", () => {
    stream.getTracks().forEach((track) => track.stop());
    toggleRecordingUi(false);
    state.recorder = null;
    if (state.recordingDiscarded || chunks.length === 0) return;

    const mimeType = recorder.mimeType || format?.mimeType || "audio/webm";
    const extension = RECORDING_FORMATS.find((item) => mimeType.startsWith(item.mimeType.split(";")[0]))?.extension ?? "webm";
    const blob = new Blob(chunks, { type: mimeType });
    const formData = new FormData();
    // The transcription API infers the format from the file extension.
    formData.append("audio", blob, `recording.${extension}`);
    send(formData, { text: "Mensagem de voz", audioUrl: URL.createObjectURL(blob) });
  });

  recorder.start();
  toggleRecordingUi(true);
}

function stopRecording({ discard = false } = {}) {
  if (!state.recorder) return;
  state.recordingDiscarded = discard;
  state.recorder.stop();
}

function toggleRecordingUi(recording) {
  elements.recordButton.setAttribute("aria-pressed", String(recording));
  elements.recordButton.setAttribute("aria-label", recording ? "Parar e enviar áudio" : "Gravar áudio");
  elements.recordingIndicator.hidden = !recording;
  elements.input.disabled = recording;
  elements.sendButton.disabled = recording;
  clearInterval(state.timerId);

  if (recording) {
    const startedAt = Date.now();
    elements.recordingTimer.textContent = "0:00";
    state.timerId = setInterval(() => {
      const seconds = Math.floor((Date.now() - startedAt) / 1000);
      elements.recordingTimer.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
      if (seconds >= MAX_RECORDING_SECONDS) stopRecording();
    }, 250);
  }
}

// ---------------------------------------------------------------- wiring

function autoResize() {
  elements.input.style.height = "auto";
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 140)}px`;
}

elements.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  sendText(elements.input.value);
});

elements.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    sendText(elements.input.value);
  }
});

elements.input.addEventListener("input", autoResize);

elements.recordButton.addEventListener("click", () => {
  if (state.recorder) stopRecording();
  else startRecording();
});

elements.cancelRecording.addEventListener("click", () => stopRecording({ discard: true }));

elements.newConversation.addEventListener("click", () => {
  if (state.busy) return;
  stopRecording({ discard: true });
  resetSession();
});

document.querySelectorAll("[data-suggestion]").forEach((chip) => {
  chip.addEventListener("click", () => sendText(chip.textContent));
});

elements.input.focus();
