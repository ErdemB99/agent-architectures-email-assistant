from __future__ import annotations

from typing import Optional, Sequence

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .prompts import (
    SYSTEM_MAIL_REPLY,
    SYSTEM_SUMMARIZER,
    SYSTEM_NEW_MAIL,
    SYSTEM_REVISE,
)

SYSTEM_ASSISTANT = (
    "Du bist ein präziser, höflicher E-Mail-Assistent. "
    "Erfinde nichts. Formuliere Unsicheres transparent und vorsichtig."
)


def sanitize(text: Optional[str]) -> str:
    if not text:
        return ""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\u200b", "").replace("\u200e", "").replace("\u200f", "")
    return t.strip()


def ask(llm: ChatOpenAI, messages: Sequence[object]) -> str:
    res = llm.invoke(list(messages)).content
    return (res or "").strip()


def summarize_text(llm: ChatOpenAI, original_text: str) -> str:
    original_text = sanitize(original_text)
    return ask(
        llm,
        [
            SystemMessage(content=SYSTEM_ASSISTANT),
            SystemMessage(content=SYSTEM_SUMMARIZER),
            HumanMessage(content=f"ORIGINALMAIL:\n{original_text}"),
        ],
    )


def write_reply_mail(
    llm: ChatOpenAI,
    original: str,
    extra: str = "",
    summary_context: Optional[str] = None,
) -> str:
    original = sanitize(original)
    extra = sanitize(extra)
    summary_context = sanitize(summary_context)

    summary_section = f"\n\nZUSAMMENFASSUNG:\n{summary_context}" if summary_context else ""
    message = (
        f"ORIGINALMAIL:\n{original}{summary_section}\n\n"
        f"USER_INPUT (Stil, Wünsche, Rahmenbedingungen):\n{extra or '–'}"
    )

    return ask(
        llm,
        [
            SystemMessage(content=SYSTEM_ASSISTANT),
            SystemMessage(content=SYSTEM_MAIL_REPLY),
            HumanMessage(content=message),
        ],
    )


def write_new_mail(llm: ChatOpenAI, brief: str) -> str:
    brief = sanitize(brief)
    message = (
        "USER_INPUT (Zweck, Empfänger, Ton, Punkte, Sprache etc.):\n"
        f"{brief}\n\n"
        "Hinweis: keine Annahmen ohne Grundlage; bei Lücken neutral bleiben."
    )

    return ask(
        llm,
        [
            SystemMessage(content=SYSTEM_ASSISTANT),
            SystemMessage(content=SYSTEM_NEW_MAIL),
            HumanMessage(content=message),
        ],
    )


def revise_mail(llm: ChatOpenAI, draft: str, feedback: str) -> str:
    draft = sanitize(draft)
    feedback = sanitize(feedback or "")

    if not feedback:
        return draft

    message = f"ENTWURF:\n{draft}\n\nFEEDBACK:\n{feedback}"

    return ask(
        llm,
        [
            SystemMessage(content=SYSTEM_ASSISTANT),
            SystemMessage(content=SYSTEM_REVISE),
            HumanMessage(content=message),
        ],
    )