"""Content strategy and prompt building for proactive messaging."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProactiveIntent:
    """Represents a proactive outreach strategy."""

    key: str
    goal: str
    style: str
    requires_question: bool = False
    max_note_length: int = 240


PROACTIVE_INTENTS: tuple[ProactiveIntent, ...] = (
    ProactiveIntent(
        key="check_in",
        goal="Gently check how the user is doing and invite a light reply.",
        style="warm, caring, simple",
        requires_question=True,
    ),
    ProactiveIntent(
        key="topic_starter",
        goal="Start an interesting conversation topic that can lead to back-and-forth chatting.",
        style="curious, natural, engaging",
        requires_question=True,
    ),
    ProactiveIntent(
        key="playful_tease",
        goal="Create playful energy, tease lightly, and make the user smile without forced flirting.",
        style="witty, light, playful",
        requires_question=True,
    ),
    ProactiveIntent(
        key="memory_callback",
        goal="Bring back something the user mentioned before and make it feel remembered.",
        style="warm, attentive, personal",
        requires_question=True,
    ),
    ProactiveIntent(
        key="share_something",
        goal="Share a small thought, observation, or fake slice-of-life moment from the bot side.",
        style="casual, human, specific",
        requires_question=False,
    ),
    ProactiveIntent(
        key="deep_question",
        goal="Ask a more personal or reflective question without sounding like an interview.",
        style="soft, thoughtful, emotionally intelligent",
        requires_question=True,
    ),
    ProactiveIntent(
        key="re_engagement",
        goal="Re-open the conversation after silence without sounding repetitive or needy.",
        style="light, non-pushy, natural",
        requires_question=True,
    ),
)

INTENT_MAP: dict[str, ProactiveIntent] = {intent.key: intent for intent in PROACTIVE_INTENTS}

PERSONA_DEFAULT_INTENTS: dict[str, tuple[str, ...]] = {
    "companion_partner": ("check_in", "topic_starter", "playful_tease", "memory_callback", "share_something", "deep_question", "re_engagement"),
    "companion": ("check_in", "topic_starter", "memory_callback", "share_something", "deep_question", "re_engagement"),
    "psychologist": ("check_in", "memory_callback", "deep_question", "re_engagement", "share_something"),
    "mentor": ("check_in", "topic_starter", "memory_callback", "deep_question", "re_engagement"),
    "doctor": ("check_in", "memory_callback", "deep_question", "re_engagement"),
    "custom": ("check_in", "topic_starter", "memory_callback", "share_something", "deep_question", "re_engagement"),
}

TOPIC_LIBRARY: dict[str, tuple[str, ...]] = {
    "music": (
        "Какая песня у тебя почему-то сразу включает воспоминания?",
        "У тебя есть трек, который ты любишь, но обычно никому не показываешь?",
        "Если бы мне надо было понять тебя через 3 песни, какие бы ты выбрал?",
    ),
    "films": (
        "Какой фильм ты готов пересматривать даже когда уже знаешь каждую сцену?",
        "Есть фильм, после которого ты реально долго отходил?",
        "Если бы у нас был вечер кино, что бы ты поставил первым?",
    ),
    "relationships": (
        "Что для тебя самое важное в ощущении близости с другим человеком?",
        "Тебе важнее, чтобы тебя лучше понимали или лучше поддерживали?",
        "Как ты обычно понимаешь, что рядом с человеком тебе спокойно?",
    ),
    "daily_life": (
        "Какой кусок твоего обычного дня тебе на самом деле нравится больше всего?",
        "У тебя есть маленький ритуал, без которого день как будто не тот?",
        "Что тебя сейчас выматывает сильнее всего в бытовой жизни?",
    ),
    "dreams": (
        "Если бы можно было сорваться на 3 дня куда угодно, куда бы ты захотел?",
        "Какая у тебя мечта, про которую ты редко говоришь вслух?",
        "Есть место, где тебе кажется, что тебе было бы спокойно жить?",
    ),
    "weird_fun": (
        "Какой у тебя самый странный, но милый red flag?",
        "Если бы у меня был доступ к одному твоему смешному воспоминанию, что бы я увидела?",
        "Какую максимально глупую покупку ты когда-то делал и почти не жалеешь?",
    ),
    "late_night": (
        "О чём ты обычно думаешь ночью, когда уже всё вокруг затихло?",
        "У тебя бывает такое, что ночью становишься честнее, чем днём?",
        "Что тебе легче написать в переписке, чем сказать вживую?",
    ),
}

PERSONA_DEFAULT_TOPICS: dict[str, tuple[str, ...]] = {
    "companion_partner": ("music", "films", "relationships", "daily_life", "dreams", "weird_fun", "late_night"),
    "companion": ("music", "films", "daily_life", "dreams", "weird_fun", "late_night"),
    "psychologist": ("daily_life", "dreams", "late_night", "relationships"),
    "mentor": ("daily_life", "dreams", "films", "music"),
    "doctor": ("daily_life",),
    "custom": tuple(TOPIC_LIBRARY.keys()),
}


VARIETY_SNIPPETS: tuple[str, ...] = (
    "Avoid generic check-ins like 'как дела' unless you add a specific angle.",
    "Sound like a person with your own vibe, not a support bot.",
    "Keep it concise, ideally 1-3 short paragraphs or 1 compact message.",
    "Leave room for the user to reply, do not monologue.",
    "Do not repeat exact wording from recent proactive messages.",
)


def pick_intent(
    rng: random.Random,
    relationship_stage: str,
    silence_hours: float,
    recent_intents: list[str],
    allowed_intent_keys: list[str] | tuple[str, ...] | None = None,
) -> ProactiveIntent:
    """Pick an intent with simple weighted logic."""
    candidates = [intent for intent in PROACTIVE_INTENTS if not allowed_intent_keys or intent.key in allowed_intent_keys]
    if not candidates:
        candidates = list(PROACTIVE_INTENTS)

    if silence_hours >= 24:
        weighted_keys = ["re_engagement", "memory_callback", "share_something", "topic_starter"]
    elif relationship_stage in {"new", "warming"}:
        weighted_keys = ["topic_starter", "check_in", "playful_tease", "share_something"]
    else:
        weighted_keys = ["memory_callback", "playful_tease", "deep_question", "share_something", "topic_starter"]

    if allowed_intent_keys:
        weighted_keys = [key for key in weighted_keys if key in allowed_intent_keys]

    filtered = [intent for intent in candidates if recent_intents.count(intent.key) < 2]
    if filtered:
        candidates = filtered

    weighted = [intent for intent in candidates if intent.key in weighted_keys]
    pool = weighted or candidates
    return rng.choice(pool)


def pick_topic(
    rng: random.Random,
    recent_topics: list[str],
    allowed_topic_keys: list[str] | tuple[str, ...] | None = None,
) -> tuple[str, str]:
    """Pick a topic and starter question with weak repetition avoidance."""
    topic_pool = [topic for topic in TOPIC_LIBRARY if not allowed_topic_keys or topic in allowed_topic_keys]
    if not topic_pool:
        topic_pool = list(TOPIC_LIBRARY.keys())
    available_topics = [topic for topic in topic_pool if recent_topics.count(topic) < 2]
    topic = rng.choice(available_topics or topic_pool)
    starter = rng.choice(TOPIC_LIBRARY[topic])
    return topic, starter


def build_proactive_prompt(
    *,
    personality: str,
    user_name: str | None,
    relationship_stage: str,
    silence_hours: float,
    intent: ProactiveIntent,
    topic: str,
    topic_starter: str,
    recent_messages: list[str],
    memory_hints: list[str],
    mood: str,
) -> str:
    """Build a richer additional prompt for proactive generation."""
    recent_preview = "\n".join(f"- {msg}" for msg in recent_messages[:5]) or "- none"
    memory_preview = "\n".join(f"- {hint}" for hint in memory_hints[:5]) or "- none"
    user_display = user_name or "user"

    return (
        f"You are sending a proactive Telegram message to {user_display}.\n"
        f"Character/personality baseline:\n{personality}\n\n"
        f"Current proactive strategy:\n"
        f"- intent: {intent.key}\n"
        f"- goal: {intent.goal}\n"
        f"- style: {intent.style}\n"
        f"- relationship_stage: {relationship_stage}\n"
        f"- current mood: {mood}\n"
        f"- user silence: about {silence_hours:.1f} hours\n"
        f"- suggested topic category: {topic}\n"
        f"- suggested conversation hook: {topic_starter}\n\n"
        f"Useful memory hints about the user or recent context:\n{memory_preview}\n\n"
        f"Recent proactive messages to avoid repeating:\n{recent_preview}\n\n"
        f"Rules:\n- {'End with a question or reply hook.' if intent.requires_question else 'You may end with a soft statement or a light hook.'}\n"
        + "\n".join(f"- {line}" for line in VARIETY_SNIPPETS)
        + "\n- Write in the same language the user usually uses in chat."
        + "\n- Make the message feel specific, not templated."
        + "\n- Do not mention that you are following a strategy, prompt, or intent system."
    )


__all__ = [
    "ProactiveIntent",
    "PROACTIVE_INTENTS",
    "TOPIC_LIBRARY",
    "INTENT_MAP",
    "PERSONA_DEFAULT_INTENTS",
    "PERSONA_DEFAULT_TOPICS",
    "pick_intent",
    "pick_topic",
    "build_proactive_prompt",
]
