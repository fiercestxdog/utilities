#!/usr/bin/env python3
"""
langgraph_agent.py — LangGraph multi-agent system with human-in-the-loop

Architecture:
    START
      └-- orchestrator  (routes the task to researcher first)
            └-- researcher  (sub-agent: analyses the topic, produces research)
                  └-- human_review  (interrupt — waits for human approval)
                        ├-- (approved) --► writer  (sub-agent: produces final output)
                        │                     └-- END
                        └-- (rejected) --► researcher  (revise and retry)

Agents:
    orchestrator    Routes and coordinates. Adds framing context to the task.
    researcher      Sub-agent that researches / analyses a topic using the LLM.
    writer          Sub-agent that drafts a polished final response from research.

Human input:
    The graph pauses at `human_review` using langgraph.types.interrupt().
    The caller resumes execution by invoking with Command(resume=feedback).

Usage:
    python langgraph_agent.py                         # interactive demo
    python langgraph_agent.py --task "your topic"     # non-interactive one-shot

Requires:
    pip install langgraph langchain-openai python-dotenv
    OPENAI_API_KEY in environment or .env file
"""

import os
import argparse
from typing import TypedDict, Literal
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

load_dotenv(dotenv_path=r"C:\python\.env")


# -----------------------------------------------------------------------------
# STATE
# -----------------------------------------------------------------------------

class AgentState(TypedDict):
    task: str           # original user task
    framed_task: str    # orchestrator-enriched version of the task
    research: str       # researcher sub-agent output
    draft: str          # writer sub-agent output
    feedback: str       # human reviewer feedback (empty = approved)
    revision: int       # how many revision loops have occurred


# -----------------------------------------------------------------------------
# LLM
# -----------------------------------------------------------------------------

def get_llm() -> ChatOpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY not found. Add it to C:\\python\\.env")
    return ChatOpenAI(model="gpt-4o-mini", temperature=0.3, api_key=api_key)


# -----------------------------------------------------------------------------
# NODES
# -----------------------------------------------------------------------------

def orchestrator(state: AgentState) -> AgentState:
    """
    Orchestrator node. Frames the raw task with scope and instructions
    so the researcher sub-agent has clear direction.
    """
    llm = get_llm()
    messages = [
        SystemMessage(content=(
            "You are a project orchestrator. Your job is to frame a user task "
            "into a clear, scoped research brief. Be concise — 2-4 sentences."
        )),
        HumanMessage(content=f"Task: {state['task']}"),
    ]
    response = llm.invoke(messages)
    framed = response.content.strip()
    print(f"\n[ORCHESTRATOR] Framed task:\n  {framed}")
    return {**state, "framed_task": framed, "revision": 0}


def researcher(state: AgentState) -> AgentState:
    """
    Researcher sub-agent. Analyses the framed task and produces structured research.
    On revision loops, incorporates the human's feedback.
    """
    llm = get_llm()

    context = state["framed_task"]
    if state.get("feedback") and state["revision"] > 0:
        context += f"\n\nRevision #{state['revision']} — Human feedback: {state['feedback']}"

    messages = [
        SystemMessage(content=(
            "You are a research analyst. Given a brief, produce structured research: "
            "key facts, important considerations, and any caveats. Use bullet points. "
            "Be thorough but concise."
        )),
        HumanMessage(content=context),
    ]
    response = llm.invoke(messages)
    research = response.content.strip()
    print(f"\n[RESEARCHER] Research complete ({len(research)} chars).")
    return {**state, "research": research, "feedback": ""}


def human_review(state: AgentState) -> Command[Literal["researcher", "writer"]]:
    """
    Human-in-the-loop node. Pauses the graph via interrupt() and waits for
    the human to approve or request changes.

    Returns a Command that routes to:
      - 'writer'     if the human approves (empty input or 'ok'/'yes'/'approve')
      - 'researcher' if the human requests changes (any other non-empty input)
    """
    print(f"\n[HUMAN REVIEW] Research to review:\n")
    print("-" * 60)
    print(state["research"])
    print("-" * 60)

    # Pause and ask for feedback; resumes when Command(resume=...) is called
    feedback: str = interrupt(
        "Review the research above. Press Enter / type 'ok' to approve, "
        "or type revision instructions to request changes."
    )

    feedback = feedback.strip()
    approved = feedback.lower() in ("", "ok", "yes", "approve", "y")

    if approved:
        print("[HUMAN REVIEW] Approved — routing to writer.")
        return Command(goto="writer", update={**state, "feedback": ""})
    else:
        print(f"[HUMAN REVIEW] Changes requested — routing back to researcher.")
        return Command(
            goto="researcher",
            update={**state, "feedback": feedback, "revision": state["revision"] + 1},
        )


def writer(state: AgentState) -> AgentState:
    """
    Writer sub-agent. Consumes the approved research and produces a polished
    final response ready for the user.
    """
    llm = get_llm()
    messages = [
        SystemMessage(content=(
            "You are a professional writer. Using the research provided, write a "
            "clear, well-structured response to the original task. Use markdown. "
            "Include an introduction, body, and conclusion."
        )),
        HumanMessage(content=(
            f"Original task: {state['task']}\n\n"
            f"Research:\n{state['research']}"
        )),
    ]
    response = llm.invoke(messages)
    draft = response.content.strip()
    print(f"\n[WRITER] Draft complete ({len(draft)} chars).")
    return {**state, "draft": draft}


# -----------------------------------------------------------------------------
# GRAPH ASSEMBLY
# -----------------------------------------------------------------------------

def build_graph() -> StateGraph:
    """
    Assemble and compile the agent graph with an in-memory checkpointer.
    The checkpointer is required for interrupt() to work.
    """
    builder = StateGraph(AgentState)

    builder.add_node("orchestrator", orchestrator)
    builder.add_node("researcher",   researcher)
    builder.add_node("human_review", human_review)
    builder.add_node("writer",       writer)

    builder.add_edge(START,          "orchestrator")
    builder.add_edge("orchestrator", "researcher")
    builder.add_edge("researcher",   "human_review")
    # human_review routes dynamically via Command(goto=...) — no static edges needed
    builder.add_edge("writer",       END)

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


# -----------------------------------------------------------------------------
# RUNNER  (interactive human-in-the-loop loop)
# -----------------------------------------------------------------------------

def run_interactive(task: str, thread_id: str = "demo-1") -> str:
    """
    Run the full agent pipeline interactively, handling the human_review interrupt.

    Args:
        task:      The user's original task string.
        thread_id: Thread identifier for the checkpointer (allows resuming).

    Returns:
        The final draft produced by the writer sub-agent.
    """
    graph  = build_graph()
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: AgentState = {
        "task":        task,
        "framed_task": "",
        "research":    "",
        "draft":       "",
        "feedback":    "",
        "revision":    0,
    }

    print(f"\n{'=' * 60}")
    print(f"TASK: {task}")
    print(f"{'=' * 60}")

    # -- Phase 1: run until interrupt -----------------------------------------
    for event in graph.stream(initial_state, config, stream_mode="values"):
        pass   # progress printed inside nodes

    # -- Phase 2: human review loop -------------------------------------------
    while True:
        current = graph.get_state(config)

        # If the graph is done there are no more interrupts
        if not current.next:
            break

        # Prompt the human
        pending_interrupt = current.tasks[0].interrupts[0] if current.tasks else None
        prompt_text = pending_interrupt.value if pending_interrupt else "Approve? "
        feedback = input(f"\n>>> {prompt_text}\n>>> ").strip()

        # Resume with the human's response
        for event in graph.stream(Command(resume=feedback), config, stream_mode="values"):
            pass

    final = graph.get_state(config).values
    draft = final.get("draft", "")

    print(f"\n{'=' * 60}")
    print("FINAL OUTPUT")
    print(f"{'=' * 60}")
    print(draft)
    return draft


def run_noninteractive(task: str, feedback: str = "", thread_id: str = "ci-1") -> str:
    """
    Run without blocking for user input — used by tests and CI.

    Args:
        task:      The user's task.
        feedback:  Pre-supplied human feedback ('ok' = approve, anything else = revise).
        thread_id: Thread identifier.

    Returns:
        Final draft string.
    """
    graph  = build_graph()
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: AgentState = {
        "task":        task,
        "framed_task": "",
        "research":    "",
        "draft":       "",
        "feedback":    "",
        "revision":    0,
    }

    for _ in graph.stream(initial_state, config, stream_mode="values"):
        pass

    for _ in graph.stream(Command(resume=feedback), config, stream_mode="values"):
        pass

    return graph.get_state(config).values.get("draft", "")


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="LangGraph multi-agent system with human-in-the-loop review",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python langgraph_agent.py
  python langgraph_agent.py --task "Explain the benefits of solar energy"
        """,
    )
    parser.add_argument(
        "--task", default=None,
        help="Task to process (omit for interactive prompt)"
    )
    args = parser.parse_args()

    task = args.task or input("Enter task: ").strip()
    if not task:
        raise SystemExit("No task provided.")

    run_interactive(task)


if __name__ == "__main__":
    main()
