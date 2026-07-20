const panel = document.getElementById("study-live");
const title = document.getElementById("study-live-title");
const progress = document.getElementById("study-live-progress");
const question = document.getElementById("study-live-question");
const questionMedia = document.getElementById("study-live-question-media");
const answerArea = document.getElementById("study-live-answer-area");
const answer = document.getElementById("study-live-answer");
const answerMedia = document.getElementById("study-live-answer-media");
const notes = document.getElementById("study-live-notes");
let signature = "";

function renderMedia(target, items) {
  target.innerHTML = items.map((item) =>
    `<img src="${item.url}" alt="${String(item.filename).replaceAll('"', "&quot;")}">`
  ).join("");
}

async function refresh() {
  const response = await fetch("/api/study/sessions/current", { cache: "no-store" });
  if (!response.ok) return;
  const { session } = await response.json();
  const nextSignature = JSON.stringify(session);
  if (nextSignature === signature) return;
  signature = nextSignature;

  const active = session?.status === "active" && session.card;
  panel.hidden = !active;
  if (!active) return;

  title.textContent = session.deck.name;
  progress.textContent =
    `Card ${session.progress.current} of ${session.progress.total} · ` +
    `${session.progress.correct} correct · ${session.progress.wrong} wrong · ` +
    `${session.progress.skipped} skipped`;
  question.textContent = session.card.question;
  renderMedia(questionMedia, session.card.media.question);

  answerArea.hidden = !session.answer_revealed;
  if (session.answer_revealed) {
    answer.textContent = session.card.answer;
    renderMedia(answerMedia, session.card.media.answer);
    notes.textContent = session.card.notes ? `Notes: ${session.card.notes}` : "";
  }
}

refresh().catch(console.error);
setInterval(() => refresh().catch(console.error), 1200);
