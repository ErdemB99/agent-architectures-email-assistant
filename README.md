# Bachelor Thesis – Design, Implementation, and Evaluation of Agent-Based Chatbot Architectures

This repository contains the implementation of my bachelor thesis at **Berliner Hochschule für Technik**. The thesis builds an **email assistant** as a practical reference system and uses it to empirically compare **three orchestration architectures** under controlled conditions.

The core objective is to evaluate the trade-offs between **response quality**, **latency**, **token cost**, and **user experience** when moving from a non-agent baseline to more agentic orchestration approaches.

**Implemented reference architectures:**

1. **Monolith (baseline):** UI-/code-driven flow without agent planning
2. **Routing graph:** deterministic intent classification + specialized execution nodes
3. **Single agent with tool use:** agent decides which tools to call and may chain tool steps

---

## Email Assistant Capabilities

- **Summarize** an email  
- **Draft a reply** to an email  
- **Write a new email** from a short brief
- **Revise** an existing draft based on user feedback  

---

## Background / References

The design choices and orchestration patterns are informed by established agent workflow patterns and the underlying frameworks:

- Anthropic (2024): *Building Effective Agents* — agentic workflow patterns and routing-style architectures  
- LangGraph docs: *Workflows & Agents* — graph-based orchestration patterns  
- LangChain docs: *Tool calling* — structured tool/function invocation  

---

## Compared Architectures

### 1) Monolith (Baseline)

A direct implementation where the user flow is controlled by UI/code logic (no agentic planning).

- **Pros:** simplest, fastest, lowest overhead  
- **Cons:** least flexible  

### 2) Router + Specialized Nodes (Routing Graph)

A router classifies each request into exactly one intent (e.g., general/summary/reply/new/revise) and forwards it to a dedicated node.

- **Pros:** structured and predictable, moderate overhead  
- **Cons:** depends on correct intent classification  

### 3) Single Agent with Tool Use (Agentic)

A single agent decides which tool(s) to call (summary/reply/new/revise/general) and may chain tool calls when needed.

- **Pros:** most flexible interaction  
- **Cons:** highest overhead (latency/tokens), increased variability  

---

## Evaluation Method (Short)

- Same tasks, prompts/output formats, and model settings; **only orchestration differs**.  
- Metrics: **latency (seconds)** and **token usage**; plus a small qualitative preference vote.  
- Test set: **real and synthetically generated emails**.  

---

## Evaluation (Snapshot)

The three architectures were evaluated on **10 test cases**. Due to sample size, the results are not intended for inferential statistical claims, but they provide robust indicators for **latency** and **token usage (cost)**.

**Representative example (single test case):**

| Task | Baseline (Latency / Tokens) | Routing (Latency / Tokens) | Single-Agent (Latency / Tokens) |
|---|---:|---:|---:|
| Summarization | 1.96s / 317 | 2.10s / 615 | 5.03s / 1916 |
| Reply | 2.47s / 481 | 2.30s / 1044 | 6.10s / 3031 |
| Revision | 2.11s / 363 | 2.57s / 1218 | 5.38s / 3872 |

In this example, routing required **+1,716 tokens** compared to baseline, and the single-agent variant **+7,658 tokens**. Total latency was **6.54s (baseline)**, **6.97s (routing)**, and **16.51s (single-agent)**.

Across all test cases, the pattern was consistent: **baseline is fastest and cheapest**, **routing provides the best quality/efficiency balance**, and **single-agent is most flexible but most expensive** in latency and tokens.

---

## Tech Stack

- Python
- Streamlit
- LangChain / LangGraph
- OpenAI model endpoint via `langchain-openai`

---

## Setup & Run

### 1) Create a virtual environment

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2) Install dependencies

``` bash
pip install -r requirements.txt
```

### 3) Configure environment variables

Create a `.env` file in the project root:

``` env
OPENAI_API_KEY=YOUR_KEY_HERE
```

### 4) Run the application

Baseline (monolith):

``` bash
streamlit run app.py
```

Agent / routing variant:

``` bash
streamlit run app_agent.py
```
