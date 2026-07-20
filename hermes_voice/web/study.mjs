const state = {
  decks: [],
  selectedDeck: null,
  cards: [],
  editingCard: null,
  session: null,
};

const byId = (id) => document.getElementById(id);
const deckList = byId("deck-list");
const emptyState = byId("empty-state");
const deckWorkspace = byId("deck-workspace");
const sessionPanel = byId("session-panel");
const layout = document.querySelector(".layout");

async function api(path, options = {}) {
  const init = { ...options };
  init.headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const response = await fetch(path, init);
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status})`);
  return payload;
}

function escapeHtml(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function accuracy(stats) {
  return stats.accuracy == null ? "No graded cards" : `${Math.round(stats.accuracy * 100)}% accuracy`;
}

async function loadDecks(preferredId = state.selectedDeck?.id) {
  const payload = await api("/api/study/decks");
  state.decks = payload.decks;
  if (preferredId != null) state.selectedDeck = state.decks.find((deck) => deck.id === preferredId) || null;
  if (!state.selectedDeck && state.decks.length) state.selectedDeck = state.decks[0];
  renderDecks();
  if (state.selectedDeck) await loadCards();
  else { state.cards = []; renderWorkspace(); }
}

async function loadCards() {
  const payload = await api(`/api/study/decks/${state.selectedDeck.id}/cards`);
  state.cards = payload.cards;
  renderWorkspace();
}

function renderDecks() {
  deckList.innerHTML = state.decks.map((deck) => `
    <button class="deck-item ${state.selectedDeck?.id === deck.id ? "active" : ""}"
            data-deck-id="${deck.id}" type="button">
      <strong>${escapeHtml(deck.name)}</strong>
      <span>${deck.card_count} cards · ${escapeHtml(accuracy(deck.stats))}</span>
    </button>`).join("");
  deckList.querySelectorAll("[data-deck-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedDeck = state.decks.find((deck) => deck.id === Number(button.dataset.deckId));
      renderDecks();
      await loadCards();
    });
  });
}

function mediaPreview(card) {
  const items = card.media.question.slice(0, 3);
  if (!items.length) return "";
  return `<div class="inline-media">${items.map((item) =>
    `<img src="${item.url}" alt="${escapeHtml(item.filename)}" loading="lazy">`
  ).join("")}</div>`;
}

function renderWorkspace() {
  const hasDeck = Boolean(state.selectedDeck);
  emptyState.hidden = hasDeck;
  deckWorkspace.hidden = !hasDeck;
  if (!hasDeck) return;
  const deck = state.selectedDeck;
  byId("deck-title").textContent = deck.name;
  byId("deck-description").textContent = deck.description || "No description";
  byId("deck-stats").textContent = `${deck.card_count} cards · ${accuracy(deck.stats)} · ${deck.stats.correct} correct, ${deck.stats.wrong} wrong, ${deck.stats.skipped} skipped`;
  const cardList = byId("card-list");
  if (!state.cards.length) {
    cardList.innerHTML = `<div class="panel"><strong>No cards yet.</strong><p class="muted">Create the first question and answer for this deck.</p></div>`;
    return;
  }
  cardList.innerHTML = state.cards.map((card, index) => `
    <article class="card-row"><div><h3>${index + 1}. ${escapeHtml(card.question)}</h3>
    <p class="answer-preview">${escapeHtml(card.answer)}</p>
    ${card.notes ? `<p class="muted">${escapeHtml(card.notes)}</p>` : ""}${mediaPreview(card)}
    <p class="muted">${card.stats.attempts} attempts · ${escapeHtml(accuracy(card.stats))}</p></div>
    <div class="row-actions"><button data-edit-card="${card.id}" type="button">Edit</button>
    <button data-delete-card="${card.id}" class="danger" type="button">Delete</button></div></article>`).join("");
  cardList.querySelectorAll("[data-edit-card]").forEach((button) => {
    button.addEventListener("click", () => openCardDialog(state.cards.find((item) => item.id === Number(button.dataset.editCard))));
  });
  cardList.querySelectorAll("[data-delete-card]").forEach((button) => {
    button.addEventListener("click", async () => {
      const card = state.cards.find((item) => item.id === Number(button.dataset.deleteCard));
      if (!confirm(`Delete the card "${card.question}"?`)) return;
      await api(`/api/study/cards/${card.id}`, { method: "DELETE" });
      await loadDecks(state.selectedDeck.id);
    });
  });
}

function openDeckDialog(deck = null) {
  byId("deck-id").value = deck?.id || "";
  byId("deck-dialog-title").textContent = deck ? "Edit deck" : "New deck";
  byId("deck-name").value = deck?.name || "";
  byId("deck-description-input").value = deck?.description || "";
  byId("deck-error").textContent = "";
  byId("deck-dialog").showModal();
  byId("deck-name").focus();
}

function renderExistingMedia(card) {
  for (const section of ["question", "answer", "notes"]) {
    const target = byId(`${section}-media-existing`);
    const items = card?.media?.[section] || [];
    target.innerHTML = items.map((item) => `<article><img src="${item.url}" alt="${escapeHtml(item.filename)}">
      <button type="button" data-remove-media="${item.id}" data-section="${section}" aria-label="Remove image">×</button></article>`).join("");
    target.querySelectorAll("[data-remove-media]").forEach((button) => {
      button.addEventListener("click", async () => {
        await api(`/api/study/cards/${card.id}/media/${button.dataset.section}/${button.dataset.removeMedia}`, { method: "DELETE" });
        const payload = await api(`/api/study/cards/${card.id}`);
        state.editingCard = payload.card;
        renderExistingMedia(payload.card);
        await loadCards();
      });
    });
  }
}

function openCardDialog(card = null) {
  state.editingCard = card;
  byId("card-id").value = card?.id || "";
  byId("card-dialog-title").textContent = card ? "Edit card" : "New card";
  byId("card-question").value = card?.question || "";
  byId("card-answer").value = card?.answer || "";
  byId("card-notes").value = card?.notes || "";
  for (const section of ["question", "answer", "notes"]) byId(`${section}-images`).value = "";
  byId("card-error").textContent = "";
  renderExistingMedia(card);
  byId("card-dialog").showModal();
  byId("card-question").focus();
}

async function fileToBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  return btoa(binary);
}

async function uploadSection(cardId, section) {
  for (const file of byId(`${section}-images`).files) {
    await api(`/api/study/cards/${cardId}/media`, { method: "POST", body: JSON.stringify({ section, filename: file.name, mime_type: file.type, data_base64: await fileToBase64(file) }) });
  }
}

byId("deck-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = Number(byId("deck-id").value || 0);
  try {
    const payload = { name: byId("deck-name").value, description: byId("deck-description-input").value };
    const response = id ? await api(`/api/study/decks/${id}`, { method: "PATCH", body: JSON.stringify(payload) }) : await api("/api/study/decks", { method: "POST", body: JSON.stringify(payload) });
    byId("deck-dialog").close();
    state.selectedDeck = response.deck;
    await loadDecks(response.deck.id);
  } catch (error) { byId("deck-error").textContent = error.message; }
});

byId("card-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = Number(byId("card-id").value || 0);
  try {
    const payload = { question: byId("card-question").value, answer: byId("card-answer").value, notes: byId("card-notes").value };
    const response = id ? await api(`/api/study/cards/${id}`, { method: "PATCH", body: JSON.stringify(payload) }) : await api(`/api/study/decks/${state.selectedDeck.id}/cards`, { method: "POST", body: JSON.stringify(payload) });
    for (const section of ["question", "answer", "notes"]) await uploadSection(response.card.id, section);
    byId("card-dialog").close();
    await loadDecks(state.selectedDeck.id);
  } catch (error) { byId("card-error").textContent = error.message; }
});

document.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => button.closest("dialog").close()));
for (const id of ["new-deck", "empty-new-deck"]) byId(id).addEventListener("click", () => openDeckDialog());
byId("edit-deck").addEventListener("click", () => openDeckDialog(state.selectedDeck));
byId("new-card").addEventListener("click", () => openCardDialog());
byId("delete-deck").addEventListener("click", async () => {
  if (!confirm(`Delete the deck "${state.selectedDeck.name}" and all of its cards?`)) return;
  await api(`/api/study/decks/${state.selectedDeck.id}`, { method: "DELETE" });
  state.selectedDeck = null;
  await loadDecks();
});

function renderImages(targetId, items) {
  byId(targetId).innerHTML = items.map((item) => `<img src="${item.url}" alt="${escapeHtml(item.filename)}">`).join("");
}

function renderSession() {
  const session = state.session;
  const active = session?.status === "active" && session.card;
  sessionPanel.hidden = !active;
  layout.classList.toggle("has-session", Boolean(active));
  if (!active) return;
  const card = session.card;
  const progress = session.progress;
  byId("session-deck").textContent = session.deck.name;
  byId("session-progress").textContent = `Card ${progress.current} of ${progress.total} · ${progress.correct} correct · ${progress.wrong} wrong · ${progress.skipped} skipped`;
  byId("session-question").textContent = card.question;
  renderImages("session-question-images", card.media.question);
  const revealed = session.answer_revealed;
  byId("session-answer-area").hidden = !revealed;
  byId("reveal-answer").hidden = revealed;
  byId("grade-actions").hidden = !revealed;
  if (revealed) {
    byId("session-answer").textContent = card.answer;
    renderImages("session-answer-images", card.media.answer);
    byId("session-notes-area").hidden = !card.notes && !card.media.notes.length;
    byId("session-notes").textContent = card.notes;
    renderImages("session-notes-images", card.media.notes);
  }
}

async function refreshSession() {
  const payload = await api("/api/study/sessions/current");
  state.session = payload.session;
  renderSession();
}

byId("study-deck").addEventListener("click", async () => {
  if (!state.cards.length) { alert("Create at least one card before starting a session."); return; }
  state.session = (await api("/api/study/sessions", { method: "POST", body: JSON.stringify({ deck_id: state.selectedDeck.id, mode: "shuffled" }) })).session;
  renderSession();
});
byId("reveal-answer").addEventListener("click", async () => {
  state.session = (await api(`/api/study/sessions/${state.session.id}/reveal`, { method: "POST", body: "{}" })).session;
  renderSession();
});
document.querySelectorAll("[data-grade]").forEach((button) => {
  button.addEventListener("click", async () => {
    state.session = (await api(`/api/study/sessions/${state.session.id}/grade`, { method: "POST", body: JSON.stringify({ outcome: button.dataset.grade }) })).session;
    renderSession();
    await loadDecks(state.selectedDeck.id);
    if (state.session.status === "finished") { const p = state.session.progress; alert(`Session finished: ${p.correct} correct, ${p.wrong} wrong, ${p.skipped} skipped.`); }
  });
});
byId("finish-session").addEventListener("click", async () => {
  state.session = (await api(`/api/study/sessions/${state.session.id}/finish`, { method: "POST", body: "{}" })).session;
  renderSession();
});

await loadDecks();
await refreshSession();
setInterval(() => refreshSession().catch(console.error), 1500);
