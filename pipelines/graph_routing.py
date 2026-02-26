from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Annotated, Any, Dict, Literal

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from .prompts import (
    ROUTER_SYSTEM_PROMPT,
    SYSTEM_SUMMARIZER,
    SYSTEM_MAIL_REPLY,
    GENERAL_SYSTEM_PROMPT,
    SYSTEM_REVISE,
    REPLY_DECISION_PROMPT,
    SYSTEM_NEW_MAIL,
)


class Router(BaseModel):
    """Klassifiziert die Nutzeranfrage."""
    type: Literal["general", "summary", "reply", "new", "revise"]
    logic: str = ""


@dataclass(kw_only=True)
class AgentState:
    messages: Annotated[list[AnyMessage], add_messages]
    uploaded_mail: str = ""
    draft: str = ""
    router: Dict[str, Any] = field(default_factory=lambda: {"type": "general", "logic": ""})


def last_user_message(messages: list[AnyMessage]) -> str:
    """Gibt den Text der letzten Nutzer-Nachricht zurück (oder leeren String)."""
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            return (m.content or "").strip()
    return ""


# -------------------------------- NODES
def agent(state: AgentState, llm: ChatOpenAI) -> dict:
    """Analysiert die Nutzeranfrage und bestimmt das Routing."""
    has_mail = bool((state.uploaded_mail or "").strip())
    has_draft = bool((state.draft or "").strip())

    sys = SystemMessage(
        content=ROUTER_SYSTEM_PROMPT.format(
            has_mail=has_mail,
            has_draft=has_draft,
        )
    )
    messages = [sys] + state.messages

    try:
        decision: Router = llm.with_structured_output(Router).invoke(messages)
        router_dict = decision.dict()

        rtype = router_dict.get("type", "general")
        if rtype in ("summary", "reply") and not has_mail:
            router_dict = {"type": "general", "logic": f"{rtype} unzulässig ohne Mail"}
        elif rtype == "revise" and not has_draft:
            router_dict = {"type": "general", "logic": "revise unzulässig ohne Entwurf"}
    except Exception:
        router_dict = {"type": "general", "logic": "fallback"}

    return {"router": router_dict}


def route_query(state: AgentState) -> Literal["summary", "reply", "new", "revise", "general"]:
    """Leitet zum passenden Knoten weiter."""
    if isinstance(state.router, dict):
        rtype = state.router.get("type", "general")
        if rtype in ("summary", "reply", "new", "revise", "general"):
            return rtype 
    return "general"


def node_summary(state: AgentState, llm: ChatOpenAI) -> dict:
    """Fasst die hochgeladene Mail kurz zusammen."""
    mail = (state.uploaded_mail or "").strip()
    if not mail:
        return {"messages": [AIMessage(content="Bitte lade zuerst eine Mail hoch.")]}

    sys_summarizer = SystemMessage(content=SYSTEM_SUMMARIZER)
    res = llm.invoke(
        [sys_summarizer, HumanMessage(content=f"Originalmail:\n{mail}")]
    ).content.strip()

    return {"messages": [AIMessage(content=f"Zusammenfassung:\n\n{res}")]}
    

def node_reply(state: AgentState, llm: ChatOpenAI) -> dict:
    """Antwortet auf die hochgeladene Mail (ggf. mit GENAU einer Rückfrage, falls nötig)."""
    mail = (state.uploaded_mail or "").strip()
    if not mail:
        return {"messages": [AIMessage(content="Bitte lade zuerst eine Mail hoch.")]}

    sys_reply = SystemMessage(content=SYSTEM_MAIL_REPLY)
    sys_decide = SystemMessage(content=REPLY_DECISION_PROMPT)
    sys_mail = SystemMessage(content=f"MAIL (Kontext für Antwort):\n{mail}")

    messages = [sys_reply, sys_decide, sys_mail] + state.messages
    res = llm.invoke(messages).content.strip()

    if re.match(r"^\s*ASK\s*:", res, flags=re.IGNORECASE):
        question = res.split(":", 1)[1].strip()
        return {"messages": [AIMessage(content=question)]}

    reply_draft = res
    return {
        "messages": [AIMessage(content=f"Entwurf (Antwort):\n\n{reply_draft}")],
        "draft": reply_draft,
    }


def node_new(state: AgentState, llm: ChatOpenAI) -> dict:
    """Verfasst eine neue Mail anhand des letzten Nutzer-Inputs."""
    user_input = last_user_message(state.messages)
    if not user_input:
        return {"messages": [AIMessage(content="Worum geht es in der neuen Mail? Empfänger, Zweck, Ton?")]}

    sys_new = SystemMessage(content=SYSTEM_NEW_MAIL)
    res = llm.invoke(
        [sys_new, HumanMessage(content=f"USER_INPUT:\n{user_input}")]
    ).content.strip()

    return {
        "messages": [AIMessage(content=f"Entwurf (neu):\n\n{res}")],
        "draft": res,
    }


def node_revise(state: AgentState, llm: ChatOpenAI) -> dict:
    """Überarbeitet den vorhandenen Entwurf strikt nach Nutzer-Feedback."""
    draft = (state.draft or "").strip()
    if not draft:
        return {"messages": [AIMessage(content="Kein Entwurf vorhanden. Soll ich zuerst einen erstellen?")]}

    user_input = last_user_message(state.messages)
    sys_revise = SystemMessage(content=SYSTEM_REVISE)
    res = llm.invoke(
        [sys_revise, HumanMessage(content=f"ENTWURF:\n{draft}\n\nFEEDBACK:\n{user_input or '–'}")]
    ).content.strip()

    return {
        "messages": [AIMessage(content=f"Überarbeiteter Entwurf:\n\n{res}")],
        "draft": res,
    }


def node_general(state: AgentState, llm: ChatOpenAI) -> dict:
    """Allgemeiner Assistent (Mailkontext nur nutzen, wenn relevant)."""
    user_input = last_user_message(state.messages)
    sys_general = SystemMessage(content=GENERAL_SYSTEM_PROMPT)

    mail = (state.uploaded_mail or "").strip()
    if mail:
        human = HumanMessage(
            content=(
                f"MAIL (optional, nur falls relevant):\n{mail}\n\n"
                f"FRAGE:\n{user_input or '–'}"
            )
        )
    else:
        human = HumanMessage(content=user_input or "–")

    res = llm.invoke([sys_general, human]).content.strip()
    return {"messages": [AIMessage(content=res)]}


# -------------------------------- GRAPH
def build_app(llm: ChatOpenAI):
    """Erstellt und kompiliert den Graphen."""
    g = StateGraph(AgentState)

    g.add_node("agent", lambda s: agent(s, llm))
    g.add_node("summary", lambda s: node_summary(s, llm))
    g.add_node("reply", lambda s: node_reply(s, llm))
    g.add_node("new", lambda s: node_new(s, llm))
    g.add_node("revise", lambda s: node_revise(s, llm))
    g.add_node("general", lambda s: node_general(s, llm))

    g.set_entry_point("agent")
    g.add_conditional_edges("agent", route_query)

    for n in ["summary", "reply", "new", "revise", "general"]:
        g.add_edge(n, END)

    app = g.compile()

    try:
        png = app.get_graph().draw_mermaid_png()
        with open("stategraph_routing.png", "wb") as f:
            f.write(png)
        print("Graph als stategraph_routing.png gespeichert")
    except Exception as e:
        print(e)

    return app