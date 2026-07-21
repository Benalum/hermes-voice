const CURRICULUM = "mcat-medical-foundations-phase-1";

const byId = (id) => document.getElementById(id);

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status})`);
  return payload;
}

function percent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function escapeHtml(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

async function loadProgress() {
  const payload = await request(`/api/study/curricula/${CURRICULUM}/progress`);
  renderProgress(payload.progress);
}

function renderProgress(progress) {
  byId("curriculum-title").textContent = progress.curriculum.name;
  byId("curriculum-summary").textContent =
    `${percent(progress.overall_mastery)} overall mastery · ${progress.courses.length} courses`;
  byId("continue-curriculum").disabled = !progress.next_deck;

  byId("curriculum-courses").innerHTML = progress.courses.map((course) => `
    <details class="curriculum-course" ${course.order < 2 ? "open" : ""}>
      <summary>
        <span>${String(course.order).padStart(2, "0")} ${escapeHtml(course.name)}</span>
        <span>${course.unlocked ? percent(course.mastery) : "Locked"}</span>
      </summary>
      <div class="curriculum-lessons">
        ${course.decks.map((deck) => `
          <article class="curriculum-lesson ${deck.unlocked ? "" : "locked"}">
            <div>
              <strong>${escapeHtml(deck.name)}</strong>
              <p>${deck.bound ? `${deck.total_cards} cards · ${percent(deck.mastery)} mastery` : "No deck bound"}</p>
              ${deck.reasons.length ? `<p class="muted">${escapeHtml(deck.reasons.join(" "))}</p>` : ""}
            </div>
            <button type="button" data-bind-curriculum-deck="${escapeHtml(deck.key)}">
              ${deck.bound ? "Replace binding" : "Bind selected deck"}
            </button>
          </article>`).join("")}
      </div>
    </details>`).join("");

  document.querySelectorAll("[data-bind-curriculum-deck]").forEach((button) => {
    button.addEventListener("click", async () => {
      const active = document.querySelector(".deck-item.active");
      if (!active) {
        alert("Select a Study deck first.");
        return;
      }
      button.disabled = true;
      try {
        await request(`/api/study/curriculum-decks/${button.dataset.bindCurriculumDeck}/bind`, {
          method: "POST",
          body: JSON.stringify({ deck_id: Number(active.dataset.deckId) }),
        });
        await loadProgress();
      } catch (error) {
        alert(error.message);
      } finally {
        button.disabled = false;
      }
    });
  });
}

byId("continue-curriculum").addEventListener("click", async () => {
  try {
    await request(`/api/study/curricula/${CURRICULUM}/continue`, {
      method: "POST",
      body: "{}",
    });
  } catch (error) {
    alert(error.message);
  }
});

byId("start-cumulative-review").addEventListener("click", async () => {
  try {
    await request(`/api/study/curricula/${CURRICULUM}/review-session`, {
      method: "POST",
      body: JSON.stringify({ limit: 20 }),
    });
  } catch (error) {
    alert(error.message);
  }
});

document.querySelectorAll("[data-review-rating]").forEach((button) => {
  button.addEventListener("click", async () => {
    try {
      const current = await request("/api/study/sessions/current");
      const session = current.session;
      if (!session?.card) throw new Error("There is no active card to rate.");
      const rating = button.dataset.reviewRating;
      await request(`/api/study/cards/${session.card.id}/review`, {
        method: "POST",
        body: JSON.stringify({ rating }),
      });
      const outcome = rating === "again" ? "wrong" : "correct";
      await request(`/api/study/sessions/${session.id}/grade`, {
        method: "POST",
        body: JSON.stringify({ outcome }),
      });
      await loadProgress();
    } catch (error) {
      alert(error.message);
    }
  });
});

await loadProgress();
setInterval(() => loadProgress().catch(console.error), 5000);
