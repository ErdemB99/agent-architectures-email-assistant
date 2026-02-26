import os
import time

import streamlit as st
from dotenv import load_dotenv
from langchain_community.callbacks import get_openai_callback
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from pipelines.graph_routing import build_app
# from pipelines.graph_agent import build_app


@st.cache_resource
def init_llm() -> ChatOpenAI:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.error("OPENAI_API_KEY fehlt in .env")
        st.stop()
    return ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=api_key)


@st.cache_resource
def init_app(llm: ChatOpenAI):
    # App einmal bauen (Graph/Agent), nicht bei jedem Rerun neu
    return build_app(llm)


def init_state() -> None:
    s = st.session_state

    s.setdefault("llm", init_llm())
    s.setdefault("app", init_app(s["llm"]))

    s.setdefault(
        "state",
        {
            "messages": [],
            "uploaded_mail": "",
            "draft": "",
            "router": {"type": "general", "logic": ""},
        },
    )
    s.setdefault("chat", [])
    s.setdefault("mail_text", "")
    s.setdefault("started", False)
    s.setdefault("mail_set", False)


def reset_start_flow() -> None:
    st.session_state.started = False
    st.session_state.mail_set = False
    st.session_state.mail_text = st.session_state.state.get("uploaded_mail", "")


def main() -> None:
    init_state()
    st.title("📧 Dein Mail-Assistent")

    # Start-Flow: Mail setzen oder ohne Mail starten
    if not st.session_state.started:
        with st.expander("📥 Originalmail eingeben", expanded=not st.session_state.mail_set):
            st.session_state.mail_text = st.text_area(
                "Bitte füge hier den Text der Mail ein, auf die du antworten möchtest",
                value=st.session_state.mail_text,
                height=300,
            )

            c1, c2 = st.columns(2)
            with c1:
                start_with_mail = st.button(
                    "▶️ Starten",
                    type="primary",
                    use_container_width=True,
                    disabled=not st.session_state.mail_text.strip(),
                )
            with c2:
                start_without_mail = st.button("▶️ Ohne Mail starten", use_container_width=True)

            if start_with_mail:
                st.session_state.state["uploaded_mail"] = st.session_state.mail_text.strip()
                st.session_state.mail_set = True
                st.session_state.started = True
                st.rerun()

            if start_without_mail:
                st.session_state.state["uploaded_mail"] = ""
                st.session_state.mail_set = False
                st.session_state.started = True
                st.rerun()

        st.stop()

    st.caption("✅ Mail im Kontext" if st.session_state.mail_set else "ℹ️ Chat ohne Mail.")

    # Chat-Historie rendern
    for m in st.session_state.chat:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    # Begrüßung nur einmal
    if not st.session_state.chat:
        hello = "Hallo! Ich helfe dir, **auf eine Mail zu antworten** oder **eine neue Mail zu erstellen**."
        st.session_state.chat.append({"role": "assistant", "content": hello})
        with st.chat_message("assistant"):
            st.markdown(hello)

    # Sidebar actions
    with st.sidebar:
        if st.button("✏️ Mail ändern / neu setzen"):
            reset_start_flow()
            st.rerun()

    # User input
    prompt = st.chat_input("Schreib hier … z. B. „Fass die Mail zusammen“ oder „Schreib eine Antwort“.")
    if not prompt:
        return

    st.session_state.chat.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    state = st.session_state.state
    prev_len = len(state["messages"])
    state["messages"].append(HumanMessage(content=prompt))

    # Assistant streaming
    with st.chat_message("assistant"):
        text_placeholder = st.empty()
        meta_placeholder = st.empty()

        streamed_text = ""
        last_values = None

        t0 = time.perf_counter()
        with get_openai_callback() as cb:
            for values in st.session_state.app.stream(state, stream_mode="values"):
                last_values = values
                msgs = values.get("messages", [])
                new_ai = [m for m in msgs[prev_len:] if isinstance(m, AIMessage)]
                if new_ai:
                    streamed_text = "\n\n".join(m.content for m in new_ai)
                    text_placeholder.markdown(streamed_text)

        latency = time.perf_counter() - t0
        meta_placeholder.caption(f"⏱️ {latency:.2f}s · 🔤 {cb.total_tokens} Tokens")

    if last_values is None:
        return

    st.session_state.state = dict(last_values)

    if streamed_text:
        st.session_state.chat.append({"role": "assistant", "content": streamed_text})
        st.session_state.chat.append({"role": "assistant", "content": f"⏱️ {latency:.2f}s · 🔤 {cb.total_tokens}"})


if __name__ == "__main__":
    main()