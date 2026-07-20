"""Voice command layer that keeps study sessions local to Hermes."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from hermes_voice.kit import session as sm
from hermes_voice.kit.ports import ResponderPort
from hermes_voice.study.store import StudyConflictError, StudyNotFoundError, StudyStore

_START_PATTERNS = (
    re.compile(r"^(?:hermes[,\s]+)?(?:start\s+)?(?:a\s+)?study(?:ing)?(?:\s+session)?(?:\s+(?:with|from|on))?\s+(?:my\s+)?(.+?)(?:\s+deck)?[.!?]*$", re.IGNORECASE),
    re.compile(r"^(?:hermes[,\s]+)?study\s+(?:my\s+)?(.+?)(?:\s+deck)?[.!?]*$", re.IGNORECASE),
)


class StudyResponder:
    """Intercept explicit study commands before forwarding to Telegram."""

    def __init__(self, *, store: StudyStore, delegate: ResponderPort, emit: Callable[[sm.Event], None]) -> None:
        self._store = store
        self._delegate = delegate
        self._emit = emit

    async def send(self, text: str) -> None:
        response = self._handle(text)
        if response is None:
            await self._delegate.send(text)
            return
        self._emit(sm.AgentSpeakable(text=response, message_id=0))
        self._emit(sm.TurnSettled())

    async def reset(self, chat_key: str) -> None:
        await self._delegate.reset(chat_key)

    async def close(self) -> None:
        await self._delegate.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def _handle(self, text: str) -> str | None:
        normalized = _normalize(text)
        active = self._store.current_session()

        if normalized in {"list my decks", "list decks", "what decks do i have", "show my decks"}:
            return self._deck_list()

        if active is not None:
            response = self._handle_active(active, normalized)
            if response is not None:
                return response

        deck_name = _start_deck_name(text)
        if deck_name is None:
            if normalized in {"start studying", "start a study session", "study"}:
                return "Which deck would you like to study?"
            return None

        try:
            session = self._store.start_session_by_name(deck_name)
        except StudyNotFoundError:
            return f"I could not find a deck named {deck_name}. {self._deck_list()}"
        except StudyConflictError as exc:
            return str(exc)
        return self._question_prompt(session, prefix="Starting your study session.")

    def _handle_active(self, session: dict[str, Any], normalized: str) -> str | None:
        session_id = str(session["id"])
        card = session.get("card")

        if normalized in {"show answer", "reveal answer", "what is the answer", "answer"}:
            revealed = self._store.reveal_answer(session_id)
            current = revealed["card"]
            answer = str(current["answer"])
            notes = str(current["notes"]).strip()
            suffix = f" Notes: {notes}" if notes else ""
            return f"The answer is: {answer}.{suffix} Say correct, wrong, or skip."

        if normalized in {"correct", "right", "i got it right", "that was correct", "mark correct"}:
            return self._grade(session_id, "correct")
        if normalized in {"wrong", "incorrect", "i got it wrong", "that was wrong", "mark wrong"}:
            return self._grade(session_id, "wrong")
        if normalized in {"skip", "skipped", "skip card", "next card"}:
            return self._grade(session_id, "skipped")
        if normalized in {"repeat", "repeat question", "repeat the question", "say the question again"}:
            if card is None:
                return "This study session is finished."
            return f"Question: {card['question']}"
        if normalized in {"read notes", "show notes", "what are the notes"}:
            if card is None:
                return "This study session is finished."
            notes = str(card["notes"]).strip()
            return notes if notes else "This card does not have notes."
        if normalized in {"how am i doing", "study progress", "session progress", "what is my score"}:
            return self._progress(session)
        if normalized in {"end study session", "stop studying", "finish study session", "quit studying"}:
            finished = self._store.finish_session(session_id)
            return f"Study session ended. {self._summary(finished)}"
        return None

    def _grade(self, session_id: str, outcome: str) -> str:
        updated = self._store.grade(session_id, outcome)  # type: ignore[arg-type]
        if updated["status"] == "finished":
            return f"{outcome.capitalize()} recorded. {self._summary(updated)}"
        return self._question_prompt(updated, prefix=f"{outcome.capitalize()} recorded.")

    def _question_prompt(self, session: dict[str, Any], *, prefix: str) -> str:
        card = session["card"]
        progress = session["progress"]
        return f"{prefix} Card {progress['current']} of {progress['total']}. Question: {card['question']}"

    def _progress(self, session: dict[str, Any]) -> str:
        progress = session["progress"]
        return f"You have completed {progress['completed']} of {progress['total']} cards. {progress['correct']} correct, {progress['wrong']} wrong, and {progress['skipped']} skipped."

    def _summary(self, session: dict[str, Any]) -> str:
        progress = session["progress"]
        return f"You reviewed {progress['completed']} cards: {progress['correct']} correct, {progress['wrong']} wrong, and {progress['skipped']} skipped."

    def _deck_list(self) -> str:
        decks = self._store.list_decks()
        if not decks:
            return "You do not have any study decks yet. Open the Study page to create one."
        rendered = ", ".join(f"{deck['name']} with {deck['card_count']} cards" for deck in decks)
        return f"Your decks are: {rendered}."


def _normalize(text: str) -> str:
    value = text.casefold().strip()
    value = re.sub(r"^(?:hey\s+)?hermes[,\s]+", "", value)
    value = re.sub(r"[.!?]+$", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _start_deck_name(text: str) -> str | None:
    value = text.strip()
    for pattern in _START_PATTERNS:
        match = pattern.match(value)
        if match is not None:
            deck_name = re.sub(r"\s+deck$", "", match.group(1), flags=re.IGNORECASE)
            return deck_name.strip(" .,!?")
    return None
