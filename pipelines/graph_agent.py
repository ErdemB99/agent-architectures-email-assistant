from dataclasses import dataclass
from typing import Annotated, Optional

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from .prompts import (
    GENERAL_SYSTEM_PROMPT,
    SYSTEM_NEW_MAIL,
    REPLY_DECISION_PROMPT,
    SYSTEM_REVISE,
    SYSTEM_MAIL_REPLY,
    SYSTEM_SUMMARIZER,
)


# -------------------- State
@dataclass(kw_only=True)
class AgentState:
    messages: Annotated[list[AnyMessage], add_messages]
    uploaded_mail: str = ""
    draft: str = ""


llm: Optional[ChatOpenAI] = None
_CURRENT_STATE: Optional[AgentState] = None


def _require_llm() -> ChatOpenAI:
    if llm is None:
        raise RuntimeError("LLM nicht initialisiert")
    return llm


# -------------------- Tools
class SummaryArgs(BaseModel):
    mail: str = Field(..., description="Voller Mailtext")


@tool("summary", args_schema=SummaryArgs)
def tool_summary(mail: str) -> str:
    """Erzeugt eine prägnante Zusammenfassung der übergebenen E-Mail."""
    _llm = _require_llm()
    if not (mail or "").strip():
        return "Bitte lade zuerst eine Mail hoch."

    msgs = [
        SystemMessage(content=SYSTEM_SUMMARIZER),
        HumanMessage(content=f"Originalmail:\n{mail}"),
    ]
    return _llm.invoke(msgs).content.strip()


class ReplyArgs(BaseModel):
    mail: str = Field(..., description="Originalmail")
    extra: Optional[str] = Field("", description="Zusatzinfos (Ton, Termine, Punkte)")
    summary: Optional[str] = Field(None, description="Optionale Kurzfassung")


@tool("reply", args_schema=ReplyArgs)
def tool_reply(mail: str, extra: Optional[str] = "", summary: Optional[str] = None) -> str:
    """Erstellt eine Antwortmail auf die Originalmail; optional mit Zusatzinfos und/oder Kurzfassung."""
    _llm = _require_llm()
    if not (mail or "").strip():
        return "Bitte lade zuerst eine Mail hoch."

    msgs: list[AnyMessage] = [
        SystemMessage(content=SYSTEM_MAIL_REPLY),
        SystemMessage(content=REPLY_DECISION_PROMPT),
        SystemMessage(content=f"MAIL (Kontext für Antwort):\n{mail}"),
    ]

    if summary:
        msgs.append(SystemMessage(content=f"SUMMARY:\n{summary}"))

    if (extra or "").strip():
        msgs.append(SystemMessage(content=f"USER_INPUT:\n{extra}"))
        msgs.append(
            SystemMessage(content="HINWEIS: Wenn USER_INPUT gesetzt ist, KEINE weitere 'ASK:'-Rückfrage ausgeben.")
        )

    if _CURRENT_STATE is not None and _CURRENT_STATE.messages:
        msgs += _CURRENT_STATE.messages[-6:]

    return _llm.invoke(msgs).content.strip()


class NewArgs(BaseModel):
    brief: str = Field(..., description="Kurzbriefing (Empfänger/Zweck/Ton/Punkte)")


@tool("new", args_schema=NewArgs)
def tool_new(brief: str) -> str:
    """Verfasst eine neue E-Mail auf Basis eines Kurzbriefings."""
    _llm = _require_llm()
    msgs = [
        SystemMessage(content=SYSTEM_NEW_MAIL),
        HumanMessage(content=f"USER_INPUT:\n{brief}"),
    ]
    return _llm.invoke(msgs).content.strip()


class ReviseArgs(BaseModel):
    draft: str = Field(..., description="Bestehender E-Mail-Entwurf")
    feedback: Optional[str] = Field("", description="Konkrete Änderungswünsche")


@tool("revise", args_schema=ReviseArgs)
def tool_revise(draft: str, feedback: Optional[str] = "") -> str:
    """Überarbeitet einen vorhandenen Entwurf anhand von Feedback."""
    _llm = _require_llm()
    if not (draft or "").strip():
        return "Kein Entwurf vorhanden. Soll ich zuerst einen erstellen?"

    msgs = [
        SystemMessage(content=SYSTEM_REVISE),
        HumanMessage(content=f"ENTWURF:\n{draft}\n\nFEEDBACK:\n{feedback or '–'}"),
    ]
    return _llm.invoke(msgs).content.strip()


class GeneralArgs(BaseModel):
    question: str = Field(..., description="Freitext-Frage")
    mail: Optional[str] = Field(None, description="E-Mail-Text, falls relevant")


@tool("general", args_schema=GeneralArgs)
def tool_general(question: str, mail: Optional[str] = None) -> str:
    """Beantwortet allgemeine Fragen; optional unter Bezug auf eine E-Mail."""
    _llm = _require_llm()
    sys = SystemMessage(content=GENERAL_SYSTEM_PROMPT)

    if (mail or "").strip():
        human = HumanMessage(content=f"MAIL (optional):\n{mail}\n\nFRAGE:\n{question}")
    else:
        human = HumanMessage(content=question)

    return _llm.invoke([sys, human]).content.strip()


TOOLS = [tool_summary, tool_reply, tool_new, tool_revise, tool_general]


# -------------------- System
AGENT_SYSTEM = """Rolle: Intent-Agent für einen E-Mail-Assistenten mit Tool-Aufrufen.
Kontext-Flags: has_mail={has_mail}, has_draft={has_draft}

Aufgabe:
    - Wähle passende Tool-Aufrufe:
      summary(mail) | reply(mail, extra?, summary?) | new(brief) | revise(draft, feedback?) | general(question, mail?).
      Mehrere Aufrufe sind erlaubt, wenn nötig.
    - Für reply gelten strikt die Regeln aus REPLY_DECISION_PROMPT: genau eine 'ASK:'-Rückfrage nur bei kritischen Lücken;
    - liegt danach eine Nutzerantwort vor, erzeuge die finale Antwortmail.

Zulässigkeit:
- Wenn has_mail = false: summary und reply sind unzulässig.
- Wenn has_draft = false: revise ist unzulässig.

Definitionen:
- general: Frage/Bitte ohne E-Mail zu verfassen/überarbeiten (inkl. Fragen zur hochgeladenen Mail).
- summary: Kurzfassung der hochgeladenen Mail.
- reply: Antwort auf die hochgeladene Mail.
- new: neue, unabhängige Mail verfassen.
- revise: vorhandenen ENTWURF überarbeiten.

Sprachregel:
    - Bei Antwortmails: Sprache wie die Originalmail (sofern nicht anders vorgegeben). Sonst Sprache wie die Nutzer:in.

Ausgabe:
    - Gib nur die inhaltliche Antwort (Mail/Entwurf/Zusammenfassung/kurze Rückfrage) aus – keine Meta-Kommentare.
"""


def _make_llm_with_tools(model: ChatOpenAI, state: AgentState):
    has_mail = bool(state.uploaded_mail.strip())
    has_draft = bool(state.draft.strip())

    context_lines = []
    if has_mail:
        context_lines.append(f"MAIL:\n{state.uploaded_mail}")
    if has_draft:
        context_lines.append(f"DRAFT:\n{state.draft}")

    if context_lines:
        joined = "\n\n".join(context_lines)
        context_block = f"\n\nKontext:\n{joined}"
    else:
        context_block = ""

    sys = SystemMessage(content=AGENT_SYSTEM.format(has_mail=has_mail, has_draft=has_draft) + context_block)
    return model.bind_tools(TOOLS), sys


def agent(state: AgentState, model: ChatOpenAI):
    global _CURRENT_STATE
    _CURRENT_STATE = state

    llm_with_tools, sys = _make_llm_with_tools(model, state)
    response = llm_with_tools.invoke([sys] + state.messages)
    return {"messages": [response]}


# -------------------------------- GRAPH
def build_app(model: ChatOpenAI):
    global llm
    llm = model

    g = StateGraph(AgentState)
    g.add_node("agent", lambda s: agent(s, model))
    g.add_node("tools", ToolNode(TOOLS))

    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", tools_condition)
    g.add_edge("tools", "agent")

    app = g.compile()

    try:
        png = app.get_graph().draw_mermaid_png()
        with open("stategraph_agent.png", "wb") as f:
            f.write(png)
        print("Graph als stategraph_agent.png gespeichert")
    except Exception as e:
        print(e)

    return app