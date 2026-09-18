// Web chat for the n8n attendance workflow, styled after WhatsApp Web: a conversation list on the
// left, the open chat on the right. Each conversation is one agent session (its id is the
// session_id); history lives in IndexedDB. Messages are posted as multipart/form-data to the
// webhook, proxied by nginx so the request is same-origin.

const WEBHOOK_URL = "/webhook/clinic-chat";
const ACTIVE_KEY = "essentia-chat-active"; // sessionStorage: reopen the same chat after a reload
const DB_NAME = "essentia-chat";
const DB_STORE = "conversations";
const CLINIC_AVATAR = "logo-whats.png";
const MAX_RECORDING_SECONDS = 60;
const MAX_AUDIO_BYTES = 25 * 1024 * 1024; // nginx and the transcription API both cap uploads at 25 MB
const REPLY_TIMEOUT_MS = 125_000; // a bit over nginx's proxy_read_timeout, so its error is the one shown
const WAVEFORM_BARS = 48;
const RECORDING_FORMATS = [
  { mimeType: "audio/webm;codecs=opus", extension: "webm" },
  { mimeType: "audio/mp4", extension: "m4a" },
  { mimeType: "audio/ogg;codecs=opus", extension: "ogg" },
];
const MIC_ICON =
  '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-2.08A7 7 0 0 0 19 12h-2Z"/></svg>';

const elements = {
  app: document.querySelector("#app"),
  newChat: document.querySelector("#new-chat"),
  introNewChat: document.querySelector("#intro-new-chat"),
  search: document.querySelector("#search-input"),
  filters: document.querySelectorAll(".filter"),
  chatList: document.querySelector("#chat-list"),
  chatListEmpty: document.querySelector("#chat-list-empty"),
  introPanel: document.querySelector("#intro-panel"),
  chat: document.querySelector("#chat"),
  backButton: document.querySelector("#back-button"),
  status: document.querySelector("#chat-status"),
  menuButton: document.querySelector("#menu-button"),
  menuList: document.querySelector("#menu-list"),
  deleteConversation: document.querySelector("#delete-conversation"),
  messages: document.querySelector("#messages"),
  intro: document.querySelector("#intro"),
  quickReplies: document.querySelector("#quick-replies"),
  form: document.querySelector("#composer"),
  input: document.querySelector("#message-input"),
  attachButton: document.querySelector("#attach-button"),
  audioFile: document.querySelector("#audio-file"),
  sendButton: document.querySelector("#send-button"),
  recordButton: document.querySelector("#record-button"),
  recorder: document.querySelector("#recorder"),
  recordingTimer: document.querySelector("#recording-timer"),
  cancelRecording: document.querySelector("#cancel-recording"),
  stopRecording: document.querySelector("#stop-recording"),
  chatItemTemplate: document.querySelector("#chat-item-template"),
  messageTemplate: document.querySelector("#message-template"),
  voiceTemplate: document.querySelector("#voice-template"),
};

const state = {
  conversations: [],
  activeId: null,
  pending: new Map(), // conversation id → status label while its reply is in flight
  filter: "all",
  search: "",
  rendered: new Map(), // message id → { node, bubble, player } for the open conversation
  lastRole: null,
  lastDay: null,
  recorder: null,
  recordingDiscarded: false,
  timerId: null,
  audioContext: null,
  playing: null,
};

// ------------------------------------------------------------------ storage

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(DB_STORE, { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function withStore(mode, operation) {
  const database = await openDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = database.transaction(DB_STORE, mode);
      const request = operation(transaction.objectStore(DB_STORE));
      transaction.oncomplete = () => resolve(request.result);
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  } finally {
    database.close();
  }
}

// History is best-effort: without IndexedDB (private window, blocked storage) the chat still works.
const storage = {
  async list() {
    try {
      return await withStore("readonly", (store) => store.getAll());
    } catch {
      return [];
    }
  },
  async save(conversation) {
    try {
      await withStore("readwrite", (store) => store.put(conversation));
    } catch {
      /* not persisted */
    }
  },
  async remove(id) {
    try {
      await withStore("readwrite", (store) => store.delete(id));
    } catch {
      /* not persisted */
    }
  },
};

// ------------------------------------------------------------ conversations

// crypto.randomUUID only exists in secure contexts; opening the demo from a phone over the LAN
// (http://<ip>:8080) is not one.
function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function createConversation() {
  const now = Date.now();
  return { id: uuid(), createdAt: now, updatedAt: now, unread: 0, messages: [] };
}

function createMessage(role, kind, fields = {}) {
  return { id: uuid(), role, kind, at: new Date().toISOString(), ...fields };
}

function findConversation(id) {
  return state.conversations.find((conversation) => conversation.id === id) ?? null;
}

function activeConversation() {
  return findConversation(state.activeId);
}

function sortConversations() {
  state.conversations.sort((a, b) => b.updatedAt - a.updatedAt);
}

function pushMessage(conversation, message) {
  conversation.messages.push(message);
  conversation.updatedAt = Date.now();
  if (conversation.id === state.activeId) {
    renderLiveMessage(conversation, message);
  } else if (message.role === "assistant") {
    conversation.unread += 1;
  }
  sortConversations();
  storage.save(conversation);
  renderChatList();
}

function discardIfEmpty(id) {
  const conversation = findConversation(id);
  if (!conversation || conversation.messages.length || state.pending.has(id)) return;
  state.conversations = state.conversations.filter((item) => item.id !== id);
  storage.remove(id);
}

// On phones the chat opens without focusing the composer, so the keyboard does not cover it.
function focusComposer() {
  if (!window.matchMedia("(max-width: 768px)").matches) elements.input.focus();
}

function startConversation() {
  const active = activeConversation();
  if (active && active.messages.length === 0) {
    focusComposer();
    return;
  }
  const conversation = createConversation();
  state.conversations.unshift(conversation);
  openConversation(conversation.id);
}

function openConversation(id) {
  const conversation = findConversation(id);
  if (!conversation) return;
  if (state.activeId && state.activeId !== id) discardIfEmpty(state.activeId);
  state.activeId = id;
  conversation.unread = 0;
  storage.save(conversation);
  try {
    sessionStorage.setItem(ACTIVE_KEY, id);
  } catch {
    /* per-tab convenience only */
  }
  elements.app.classList.add("has-chat");
  elements.introPanel.hidden = true;
  elements.chat.hidden = false;
  toggleMenu(false);
  renderMessages(conversation);
  updateStatus();
  updateComposer();
  renderChatList();
  focusComposer();
}

function closeConversation() {
  stopRecording({ discard: true });
  discardIfEmpty(state.activeId);
  releasePlayers();
  state.activeId = null;
  try {
    sessionStorage.removeItem(ACTIVE_KEY);
  } catch {
    /* per-tab convenience only */
  }
  elements.app.classList.remove("has-chat");
  elements.chat.hidden = true;
  elements.introPanel.hidden = false;
  toggleMenu(false);
  renderChatList();
}

function deleteConversation(id) {
  state.conversations = state.conversations.filter((conversation) => conversation.id !== id);
  storage.remove(id);
  if (id === state.activeId) {
    state.activeId = null;
    closeConversation();
  } else {
    renderChatList();
  }
}

// -------------------------------------------------------------- formatting

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

function dayKey(date) {
  return date.toDateString();
}

function dayLabel(date) {
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (dayKey(date) === dayKey(today)) return "Hoje";
  if (dayKey(date) === dayKey(yesterday)) return "Ontem";
  return date.toLocaleDateString("pt-BR");
}

function timeLabel(date) {
  return date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function listTimeLabel(timestamp) {
  const date = new Date(timestamp);
  const label = dayLabel(date);
  return label === "Hoje" ? timeLabel(date) : label;
}

function formatDuration(seconds) {
  const total = Number.isFinite(seconds) ? Math.round(seconds) : 0;
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function base64ToBlob(base64, mimeType) {
  const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
  return new Blob([bytes], { type: mimeType });
}

function tickMarkup(read) {
  return `<svg class="tick${read ? " tick--read" : ""}" viewBox="0 0 18 11" aria-hidden="true"><path d="M1.5 6 4.5 9l7-7.5"/><path class="tick__second" d="M8.65 7.65 10 9l7-7.5"/></svg>`;
}

// ---------------------------------------------------------------- chat list

function visibleConversations() {
  const term = state.search.trim().toLowerCase();
  return state.conversations.filter((conversation) => {
    if (state.filter === "unread" && !conversation.unread) return false;
    if (!term) return true;
    return conversation.messages.some((m) => (m.text || m.transcript || "").toLowerCase().includes(term));
  });
}

function previewMarkup(conversation) {
  const pendingLabel = state.pending.get(conversation.id);
  if (pendingLabel) return { html: escapeHtml(pendingLabel), typing: true };
  const last = conversation.messages.at(-1);
  if (!last) return { html: "<span>Toque para começar a conversa</span>", typing: false };
  const tick = last.role === "user" ? tickMarkup(last.read) : "";
  if (last.kind === "voice") {
    const label = last.duration ? formatDuration(last.duration) : "Mensagem de voz";
    return { html: `${tick}${MIC_ICON}<span>${escapeHtml(label)}</span>`, typing: false };
  }
  return { html: `${tick}<span>${escapeHtml(last.text)}</span>`, typing: false };
}

function renderChatList() {
  const conversations = visibleConversations();
  const items = conversations.map((conversation) => {
    const node = elements.chatItemTemplate.content.firstElementChild.cloneNode(true);
    node.dataset.id = conversation.id;
    node.classList.toggle("is-active", conversation.id === state.activeId);
    node.classList.toggle("is-unread", conversation.unread > 0);
    node.querySelector(".chat-item__time").textContent = conversation.messages.length ? listTimeLabel(conversation.updatedAt) : "";
    const preview = previewMarkup(conversation);
    const previewNode = node.querySelector(".chat-item__preview");
    previewNode.innerHTML = preview.html;
    previewNode.classList.toggle("is-typing", preview.typing);
    const badge = node.querySelector(".chat-item__badge");
    badge.hidden = conversation.unread === 0;
    badge.textContent = String(conversation.unread);
    return node;
  });
  elements.chatList.replaceChildren(...items);
  elements.chatListEmpty.hidden = items.length > 0;
  elements.chatListEmpty.textContent = state.conversations.length
    ? "Nenhuma conversa encontrada."
    : "Nenhuma conversa ainda. Toque em Nova conversa para começar.";
}

// ----------------------------------------------------------------- messages

// Scrolls the message list itself, never an ancestor, so the panes stay put.
function scrollToBottom(behavior = "smooth") {
  elements.messages.scrollTo({ top: elements.messages.scrollHeight, behavior });
}

// The time sits at the bottom-right corner; a spacer on the last line keeps text clear of it.
function appendSpacer(container) {
  const lastBlock = container.lastElementChild ?? container;
  const target = lastBlock.tagName === "UL" ? lastBlock.lastElementChild : lastBlock;
  const spacer = document.createElement("span");
  spacer.className = "message__spacer";
  target.append(spacer);
}

function appendSystem(text, { date = false, notice = false } = {}) {
  const node = document.createElement("p");
  node.className = `system${date ? " system--date" : ""}${notice ? " system--notice" : ""}`;
  node.textContent = text;
  elements.messages.append(node);
  state.lastRole = null;
  return node;
}

function appendCaption(bubble, text, { reply = false } = {}) {
  const caption = document.createElement("div");
  caption.className = `message__transcript${reply ? " message__transcript--reply" : ""}`;
  if (reply) caption.innerHTML = formatReply(text);
  else caption.textContent = text;
  appendSpacer(caption);
  bubble.classList.add("message__bubble--captioned");
  bubble.append(caption);
}

function renderMessage(conversation, message, { live = false } = {}) {
  const date = new Date(message.at);
  if (dayKey(date) !== state.lastDay) {
    state.lastDay = dayKey(date);
    appendSystem(dayLabel(date), { date: true });
  }
  if (message.kind === "notice") return appendSystem(message.text, { notice: true });

  const node = elements.messageTemplate.content.firstElementChild.cloneNode(true);
  node.classList.add(`message--${message.role}`);
  node.setAttribute("aria-label", message.role === "user" ? "Você" : "Assistente");
  if (live) node.classList.add("message--new");
  if (state.lastRole !== message.role) node.classList.add("message--tail");
  state.lastRole = message.role;
  node.querySelector(".message__time").textContent = timeLabel(date);
  if (message.read) node.querySelector(".tick").classList.add("tick--read");

  const bubble = node.querySelector(".message__bubble");
  const content = node.querySelector(".message__text");
  let player = null;
  if (message.kind === "voice") {
    player = createVoiceNote(message.audio, (duration) => {
      if (message.duration) return;
      message.duration = duration;
      storage.save(conversation);
      renderChatList();
    });
    bubble.classList.add("message__bubble--voice");
    if (message.role === "assistant") {
      const logo = Object.assign(document.createElement("img"), { src: CLINIC_AVATAR, alt: "" });
      player.node.querySelector(".voice__avatar .avatar").replaceChildren(logo);
    }
    content.replaceWith(player.node);
    const caption = message.role === "assistant" ? message.text : message.transcript;
    if (caption) appendCaption(bubble, caption, { reply: message.role === "assistant" });
  } else if (message.role === "assistant") {
    content.innerHTML = formatReply(message.text);
    appendSpacer(content);
  } else {
    content.textContent = message.text;
    appendSpacer(content);
  }

  elements.messages.append(node);
  state.rendered.set(message.id, { node, bubble, player });
  return node;
}

// Stops and frees the voice notes of the conversation on screen.
function releasePlayers() {
  for (const { player } of state.rendered.values()) {
    if (player) {
      player.audio.pause();
      URL.revokeObjectURL(player.audio.src);
    }
  }
  state.rendered.clear();
}

function renderMessages(conversation) {
  releasePlayers();
  state.lastRole = null;
  state.lastDay = null;
  elements.messages.replaceChildren(elements.intro);
  elements.quickReplies.hidden = conversation.messages.length > 0;
  conversation.messages.forEach((message) => renderMessage(conversation, message));
  scrollToBottom("instant");
}

function renderLiveMessage(conversation, message) {
  elements.quickReplies.hidden = true;
  renderMessage(conversation, message, { live: true });
  scrollToBottom();
}

function updateStatus() {
  elements.status.textContent = state.pending.get(state.activeId) ?? "online";
}

// -------------------------------------------------------------- voice notes

function getAudioContext() {
  if (state.audioContext === null) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    state.audioContext = AudioContextClass ? new AudioContextClass() : false;
  }
  return state.audioContext || null;
}

// Decodes the audio to draw the waveform; also the only reliable duration for recorded webm.
async function analyseAudio(blob) {
  const context = getAudioContext();
  if (!context) throw new Error("Web Audio unavailable");
  const buffer = await context.decodeAudioData(await blob.arrayBuffer());
  const samples = buffer.getChannelData(0);
  const bucket = Math.max(1, Math.floor(samples.length / WAVEFORM_BARS));
  const stride = Math.max(1, Math.floor(bucket / 64));
  const levels = Array.from({ length: WAVEFORM_BARS }, (_, index) => {
    let sum = 0;
    let count = 0;
    for (let i = index * bucket; i < (index + 1) * bucket && i < samples.length; i += stride) {
      sum += Math.abs(samples[i]);
      count += 1;
    }
    return count ? sum / count : 0;
  });
  const peak = Math.max(...levels) || 1;
  return { duration: buffer.duration, levels: levels.map((level) => level / peak) };
}

function drawWave(bars, levels) {
  bars.forEach((bar, index) => {
    bar.style.height = `${3 + Math.round(levels[index] * 21)}px`;
  });
}

function createVoiceNote(blob, onDuration) {
  const node = elements.voiceTemplate.content.firstElementChild.cloneNode(true);
  const audio = new Audio(URL.createObjectURL(blob));
  audio.preload = "metadata";
  const playButton = node.querySelector(".voice__play");
  const seek = node.querySelector(".voice__seek");
  const duration = node.querySelector(".voice__duration");
  const wave = node.querySelector(".voice__wave");
  const bars = Array.from({ length: WAVEFORM_BARS }, () => wave.appendChild(document.createElement("span")));
  let total = 0;

  drawWave(bars, bars.map((_, index) => 0.2 + 0.5 * Math.abs(Math.sin(index * 1.7))));
  analyseAudio(blob)
    .then((analysis) => {
      total = analysis.duration;
      duration.textContent = formatDuration(total);
      drawWave(bars, analysis.levels);
      onDuration?.(total);
    })
    .catch(() => {
      /* keeps the placeholder waveform */
    });

  audio.addEventListener("loadedmetadata", () => {
    if (Number.isFinite(audio.duration)) {
      total = audio.duration;
      duration.textContent = formatDuration(total);
    }
  });
  audio.addEventListener("timeupdate", () => {
    if (!total) return;
    const progress = Math.min(100, (audio.currentTime / total) * 100);
    seek.value = progress;
    duration.textContent = formatDuration(audio.currentTime);
    bars.forEach((bar, index) => bar.classList.toggle("is-played", (index / WAVEFORM_BARS) * 100 < progress));
  });
  audio.addEventListener("play", () => {
    if (state.playing && state.playing !== audio) state.playing.pause();
    state.playing = audio;
    node.classList.add("is-playing");
    playButton.setAttribute("aria-label", "Pausar");
  });
  audio.addEventListener("pause", () => {
    node.classList.remove("is-playing");
    playButton.setAttribute("aria-label", "Reproduzir");
  });
  audio.addEventListener("ended", () => {
    node.classList.add("is-heard");
    seek.value = 0;
    duration.textContent = formatDuration(total);
    bars.forEach((bar) => bar.classList.remove("is-played"));
  });
  playButton.addEventListener("click", () => {
    if (audio.paused) audio.play().catch(() => {});
    else audio.pause();
  });
  seek.addEventListener("input", () => {
    if (total) audio.currentTime = (seek.value / 100) * total;
  });

  return { node, audio };
}

// ---------------------------------------------------------------- networking

async function postToWebhook(formData, conversation) {
  formData.append("session_id", conversation.id);
  let response;
  try {
    response = await fetch(WEBHOOK_URL, {
      method: "POST",
      body: formData,
      signal: AbortSignal.timeout(REPLY_TIMEOUT_MS),
    });
  } catch (error) {
    throw new Error(error.name === "TimeoutError" ? "a resposta demorou demais" : "sem conexão");
  }
  const payload = await response.json().catch(() => null);
  if (!payload?.reply_text) {
    const detail = payload?.error?.message ?? `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return payload;
}

async function send(formData, { text = "", voice = null, awaiting = "digitando…" } = {}) {
  const conversation = activeConversation();
  if (!conversation || state.pending.has(conversation.id)) return;

  const sent = voice
    ? createMessage("user", "voice", { audio: voice, mimeType: voice.type })
    : createMessage("user", "text", { text });
  pushMessage(conversation, sent);
  state.pending.set(conversation.id, awaiting);
  updateStatus();
  updateComposer();
  renderChatList();

  try {
    const reply = await postToWebhook(formData, conversation);
    sent.read = true;
    if (reply.transcript) sent.transcript = reply.transcript;
    const rendered = state.rendered.get(sent.id);
    if (rendered) {
      rendered.node.querySelector(".tick").classList.add("tick--read");
      if (sent.transcript) {
        appendCaption(rendered.bubble, sent.transcript);
        scrollToBottom();
      }
    }

    if (reply.error) {
      // The workflow answers failures with a friendly reply_text plus an error code.
      pushMessage(conversation, createMessage("assistant", "notice", { text: reply.reply_text }));
    } else if (reply.audio?.base64) {
      const answer = createMessage("assistant", "voice", {
        audio: base64ToBlob(reply.audio.base64, reply.audio.mime_type),
        mimeType: reply.audio.mime_type,
        text: reply.reply_text,
      });
      pushMessage(conversation, answer);
      state.rendered.get(answer.id)?.player.audio.play().catch(() => {
        /* autoplay blocked: the player stays visible */
      });
    } else {
      pushMessage(conversation, createMessage("assistant", "text", { text: reply.reply_text }));
    }
  } catch (error) {
    const text = `Não foi possível falar com a assistente (${error.message}). Tente novamente.`;
    pushMessage(conversation, createMessage("assistant", "notice", { text }));
  } finally {
    state.pending.delete(conversation.id);
    updateStatus();
    updateComposer();
    renderChatList();
    if (conversation.id === state.activeId) focusComposer();
  }
}

function sendText(text) {
  const message = text.trim();
  if (!message) return;
  const formData = new FormData();
  formData.append("message", message);
  elements.input.value = "";
  autoResize();
  updateComposer();
  send(formData, { text: message });
}

function sendAudio(blob, filename) {
  if (blob.size > MAX_AUDIO_BYTES) {
    showNotice("O áudio passa de 25 MB. Grave uma mensagem mais curta ou envie por texto.");
    return;
  }
  const formData = new FormData();
  // The transcription API infers the format from the file extension.
  formData.append("audio", blob, filename);
  send(formData, { voice: blob, awaiting: "gravando áudio…" });
}

// ---------------------------------------------------------------- recording

function pickRecordingFormat() {
  return RECORDING_FORMATS.find((format) => MediaRecorder.isTypeSupported(format.mimeType));
}

function showNotice(text) {
  const conversation = activeConversation();
  if (conversation) pushMessage(conversation, createMessage("assistant", "notice", { text }));
}

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    showNotice("Seu navegador não permite gravar áudio. Use a mensagem de texto.");
    return;
  }

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    showNotice("Permissão do microfone negada. Libere o acesso ou envie por texto.");
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
    sendAudio(new Blob(chunks, { type: mimeType }), `recording.${extension}`);
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
  elements.form.hidden = recording;
  elements.recorder.hidden = !recording;
  clearInterval(state.timerId);

  if (recording) {
    const startedAt = Date.now();
    elements.recordingTimer.textContent = "0:00";
    state.timerId = setInterval(() => {
      const seconds = Math.floor((Date.now() - startedAt) / 1000);
      elements.recordingTimer.textContent = formatDuration(seconds);
      if (seconds >= MAX_RECORDING_SECONDS) stopRecording();
    }, 250);
  } else {
    focusComposer();
  }
}

// ---------------------------------------------------------------- composer

function autoResize() {
  elements.input.style.height = "auto";
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 120)}px`;
}

// Like WhatsApp: the microphone gives way to the send button as soon as there is text.
function updateComposer() {
  const busy = state.pending.has(state.activeId);
  const hasText = elements.input.value.trim().length > 0;
  elements.sendButton.hidden = !hasText;
  elements.recordButton.hidden = hasText;
  elements.sendButton.disabled = busy;
  elements.recordButton.disabled = busy;
  elements.attachButton.disabled = busy;
}

function toggleMenu(open = elements.menuList.hidden) {
  elements.menuList.hidden = !open;
  elements.menuButton.setAttribute("aria-expanded", String(open));
}

// ------------------------------------------------------------------ wiring

elements.newChat.addEventListener("click", startConversation);
elements.introNewChat.addEventListener("click", startConversation);
elements.backButton.addEventListener("click", closeConversation);

elements.search.addEventListener("input", () => {
  state.search = elements.search.value;
  renderChatList();
});

elements.filters.forEach((button) => {
  button.addEventListener("click", () => {
    state.filter = button.dataset.filter;
    elements.filters.forEach((item) => {
      const active = item === button;
      item.classList.toggle("is-active", active);
      item.setAttribute("aria-pressed", String(active));
    });
    renderChatList();
  });
});

elements.chatList.addEventListener("click", (event) => {
  const item = event.target.closest(".chat-item");
  if (item) openConversation(item.dataset.id);
});

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendText(elements.input.value);
});

elements.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    sendText(elements.input.value);
  }
});

elements.input.addEventListener("input", () => {
  autoResize();
  updateComposer();
});

elements.recordButton.addEventListener("click", () => startRecording());
elements.stopRecording.addEventListener("click", () => stopRecording());
elements.cancelRecording.addEventListener("click", () => stopRecording({ discard: true }));

elements.attachButton.addEventListener("click", () => elements.audioFile.click());
elements.audioFile.addEventListener("change", () => {
  const file = elements.audioFile.files[0];
  if (file) sendAudio(file, file.name);
  elements.audioFile.value = "";
});

elements.menuButton.addEventListener("click", (event) => {
  event.stopPropagation();
  toggleMenu();
});
document.addEventListener("click", () => toggleMenu(false));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") toggleMenu(false);
});
elements.deleteConversation.addEventListener("click", () => {
  toggleMenu(false);
  if (state.activeId) deleteConversation(state.activeId);
});

document.querySelectorAll("[data-suggestion]").forEach((chip) => {
  chip.addEventListener("click", () => sendText(chip.textContent));
});

// ---------------------------------------------------------------- start-up

async function start() {
  const stored = await storage.list();
  state.conversations = stored.filter((conversation) => conversation.messages.length > 0);
  stored.filter((conversation) => conversation.messages.length === 0).forEach((conversation) => storage.remove(conversation.id));
  sortConversations();
  renderChatList();

  let lastActive = null;
  try {
    lastActive = sessionStorage.getItem(ACTIVE_KEY);
  } catch {
    /* per-tab convenience only */
  }
  if (lastActive && findConversation(lastActive)) openConversation(lastActive);
  else if (state.conversations.length === 0) startConversation();
}

start().finally(() => elements.app.classList.remove("is-loading"));
