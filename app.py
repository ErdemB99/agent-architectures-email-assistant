import os
import time

import streamlit as st
from dotenv import load_dotenv
from langchain_community.callbacks import get_openai_callback
from langchain_openai import ChatOpenAI

from pipelines.monolith import (
    summarize_text,
    write_reply_mail,
    write_new_mail,
    revise_mail,
)


STATE_KEYS = [
    "phase",
    "original_letter",
    "summary",
    "want_summary",
    "extra",
    "brief",
    "draft",
    "metrics",
]


def init_state() -> None:
    s = st.session_state
    s.setdefault("phase", "start")
    s.setdefault("original_letter", "")
    s.setdefault("summary", "")
    s.setdefault("want_summary", False)
    s.setdefault("extra", "")
    s.setdefault("brief", "")
    s.setdefault("draft", "")
    s.setdefault("metrics", None)


def reset_state() -> None:
    for k in STATE_KEYS:
        st.session_state.pop(k, None)
    init_state()


@st.cache_resource
def init_llm() -> ChatOpenAI:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.error("OPENAI_API_KEY fehlt in .env")
        st.stop()
    return ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=api_key)


def main() -> None:
    llm = init_llm()
    init_state()
    p = st.session_state

    if p.phase == "start":
        st.title("📧 Dein Mail-Assistent")
        st.write("Hallo! Ich helfe dir, **auf eine Mail zu antworten** oder **eine neue Mail zu erstellen**.")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("📩 Auf eine Mail antworten", type="primary", use_container_width=True):
                p.phase = "mail_input"
                st.rerun()
        with c2:
            if st.button("✍️ Neue Mail erstellen", use_container_width=True):
                p.phase = "new_mail"
                st.rerun()

    elif p.phase == "mail_input":
        st.subheader("📥 Originalmail eingeben")
        p.original_letter = st.text_area(
            "Bitte füge hier den Text der Mail ein, auf die du antworten möchtest",
            value=p.original_letter,
            height=300,
        )

        c1, c2 = st.columns(2)
        if c1.button("⬅️ Zurück", use_container_width=True):
            p.phase = "start"
            st.rerun()
        if c2.button("➡️ Weiter", type="primary", use_container_width=True):
            if not p.original_letter.strip():
                st.warning("Bitte zuerst die Mail einfügen.")
            else:
                p.phase = "summary_choice"
                st.rerun()

    elif p.phase == "summary_choice":
        st.subheader("📝 Zusammenfassung erstellen?")
        st.write("Möchtest du eine kurze Zusammenfassung der Mail sehen, bevor ich den Entwurf schreibe?")

        c1, c2, c3 = st.columns(3)
        if c1.button("✅ Ja, bitte", use_container_width=True):
            p.want_summary = True
            p.phase = "summary_view"
            st.rerun()
        if c2.button("⏭️ Nein, direkt zum Entwurf", use_container_width=True):
            p.want_summary = False
            p.summary = ""
            p.phase = "context_input"
            st.rerun()
        if c3.button("⬅️ Zurück", use_container_width=True):
            p.phase = "mail_input"
            st.rerun()

    elif p.phase == "summary_view":
        st.subheader("📝 Zusammenfassung")
        with st.spinner("Erzeuge Zusammenfassung …"):
            t0 = time.perf_counter()
            with get_openai_callback() as cb:
                p.summary = summarize_text(llm, p.original_letter)
            latency = time.perf_counter() - t0
            p.metrics = {"op": "summary", "latency": latency, "tokens": cb.total_tokens}

        st.text_area("Kurzfassung", p.summary, height=160, disabled=True)
        st.caption(f"⏱️ {p.metrics['latency']:.2f}s · 🔤 {p.metrics['tokens']} Tokens")

        c1, c2 = st.columns(2)
        if c1.button("⬅️ Zurück", use_container_width=True):
            p.phase = "summary_choice"
            st.rerun()
        if c2.button("➡️ Weiter", type="primary", use_container_width=True):
            p.phase = "context_input"
            st.rerun()

    elif p.phase == "context_input":
        if p.summary:
            st.subheader("📝 Zusammenfassung")
            st.text_area("Kurzfassung", p.summary, height=140, disabled=True)

        st.subheader("🧩 Zusatzinfos für die Antwort")
        p.extra = st.text_area(
            "Zusatzinfos",
            value=p.extra,
            height=140,
            placeholder="Ton, Termin, Punkte …",
        )

        c1, c2 = st.columns(2)
        if c1.button("⬅️ Zurück", use_container_width=True):
            p.phase = "summary_choice"
            st.rerun()
        if c2.button("✍️ Entwurf generieren", type="primary", use_container_width=True):
            t0 = time.perf_counter()
            with get_openai_callback() as cb:
                p.draft = write_reply_mail(llm, p.original_letter, p.extra, p.summary or None)
            latency = time.perf_counter() - t0
            p.metrics = {"op": "reply", "latency": latency, "tokens": cb.total_tokens}

            p.phase = "edit_draft"
            st.rerun()

    elif p.phase == "new_mail":
        st.subheader("🆕 Neue Mail – kurze Beschreibung")
        p.brief = st.text_area(
            "Beschreibung",
            value=p.brief,
            height=200,
            placeholder="z. B. an HR, höflich, Rückmeldung bis Freitag …",
        )

        c1, c2 = st.columns(2)
        if c1.button("⬅️ Zurück", use_container_width=True):
            p.phase = "start"
            st.rerun()
        if c2.button("✍️ Entwurf erstellen", type="primary", use_container_width=True):
            if not p.brief.strip():
                st.warning("Bitte eine kurze Beschreibung eingeben.")
            else:
                t0 = time.perf_counter()
                with get_openai_callback() as cb:
                    p.draft = write_new_mail(llm, p.brief)
                latency = time.perf_counter() - t0
                p.metrics = {"op": "new", "latency": latency, "tokens": cb.total_tokens}

                p.phase = "edit_draft"
                st.rerun()

    elif p.phase == "edit_draft":
        st.subheader("✉️ Entwurf")
        st.code(p.draft, language="markdown")

        if p.metrics:
            st.caption(f"⏱️ {p.metrics['latency']:.2f}s · 🔤 {p.metrics['tokens']} Tokens")

        fb = st.text_area(
            "Anpassungswünsche (optional)",
            height=120,
            placeholder="z. B. kürzer, Termin explizit 10:00 Uhr, auf Englisch",
        )

        c1, c2, c3 = st.columns(3)
        if c1.button("🔄 Überarbeiten", use_container_width=True):
            t0 = time.perf_counter()
            with get_openai_callback() as cb:
                p.draft = revise_mail(llm, p.draft, fb or "")
            latency = time.perf_counter() - t0
            p.metrics = {"op": "revise", "latency": latency, "tokens": cb.total_tokens}
            st.rerun()

        if c2.button("✅ Final", type="primary", use_container_width=True):
            p.phase = "finished"
            st.rerun()

        if c3.button("🔄 Neu starten", use_container_width=True):
            reset_state()
            st.rerun()

    elif p.phase == "finished":
        st.subheader("✅ Fertig")
        st.success("Der Entwurf ist final. Du kannst ihn jetzt kopieren und versenden.")
        st.code(p.draft, language="markdown")

        if p.metrics:
            st.caption(f"⏱️ {p.metrics['latency']:.2f}s · 🔤 {p.metrics['tokens']} Tokens")

        if st.button("🔄 Neu starten"):
            reset_state()
            st.rerun()


if __name__ == "__main__":
    main()