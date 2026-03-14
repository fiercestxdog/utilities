#!/usr/bin/env python3
"""
multi_agent.py — LangChain 1.x multi-agent system (GPT-4o)

Architecture:
    Orchestrator Agent
        ├── Systems Engineering Agent  →  output/systems/
        └── Coding Agent               →  output/coding/

Context sharing:
    Orchestrator owns a shared state dict updated after every agent call.
    Before calling each sub-agent, a token-capped state summary is injected
    into the task prompt so agents have full awareness of prior work.
    Sub-agents are STATELESS — each call starts fresh with no memory.
    Files are the durable record; shared state is the in-memory index.

Token safety:
    All file content and state summaries pass through safe_inject() before
    any LLM call, hard-capped at MAX_INJECT_TOKENS / STATE_SUMMARY_TOKENS.

Work log:
    Every file read/write is appended to output/work_log.csv.

Usage:
    python multi_agent.py --goal "Build a CSV data validator tool"
    python multi_agent.py --goal "..." --dry-run
    python multi_agent.py --goal "..." --api-key sk-...

Install:
    pip install langchain==1.2.7 langchain-openai==1.1.11 langchain-core==1.2.19 tiktoken==0.12.0
    langgraph==1.0.7 is pulled in automatically as a dependency of langchain.
"""

import os
import csv
import argparse
from pathlib import Path
from datetime import datetime

import tiktoken
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_core.tools import StructuredTool
from langchain_core.messages import HumanMessage


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR             = Path(__file__).parent
OUTPUT_DIR           = BASE_DIR / "output"
WORK_LOG             = OUTPUT_DIR / "work_log.csv"
MODEL                = "gpt-4o"
MAX_INJECT_TOKENS    = 2000   # max tokens for file content injected into any prompt
STATE_SUMMARY_TOKENS = 800    # max tokens for state summary injected per call

AGENT_DIRS: dict[str, Path] = {
    "systems": OUTPUT_DIR / "systems",
    "coding":  OUTPUT_DIR / "coding",
}

# Each agent may only write files with these extensions
ALLOWED_WRITE_EXTENSIONS: dict[str, set[str]] = {
    "systems": {".csv", ".md", ".txt"},
    "coding":  {".py", ".html", ".md", ".txt"},
}


# ─────────────────────────────────────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────────────────────────────────────

def setup() -> None:
    """Create output directories and initialize the work log if needed."""
    for d in [OUTPUT_DIR, *AGENT_DIRS.values()]:
        d.mkdir(parents=True, exist_ok=True)
    if not WORK_LOG.exists():
        with open(WORK_LOG, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["timestamp", "agent", "action", "file", "note"])


# ─────────────────────────────────────────────────────────────────────────────
# SHARED STATE
# ─────────────────────────────────────────────────────────────────────────────

# Single source of truth for all completed work.
# Only orchestrator tooling writes to this; sub-agents never touch it directly.
state: dict = {
    "goal":  "",
    "steps": [],   # list of {agent, action, file, summary}
}


def record_step(agent: str, action: str, file: str, summary: str) -> None:
    """Update shared state and append a row to the work log."""
    state["steps"].append(
        {"agent": agent, "action": action, "file": file, "summary": summary}
    )
    with open(WORK_LOG, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(
            [datetime.now().isoformat(), agent, action, file, summary]
        )


def build_state_summary() -> str:
    """
    Compact text snapshot of all completed work.
    Token-capped before injection so it never blows out a prompt budget.
    """
    lines = [f"GOAL: {state['goal']}"]
    if state["steps"]:
        lines.append("WORK COMPLETED SO FAR:")
        for s in state["steps"]:
            line = f"  [{s['agent'].upper()}] {s['summary']}"
            if s["file"]:
                line += f"  ->  {s['file']}"
            lines.append(line)
    else:
        lines.append("No work completed yet.")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# TOKEN MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

try:
    _enc = tiktoken.encoding_for_model(MODEL)
except KeyError:
    _enc = tiktoken.get_encoding("cl100k_base")   # GPT-4 family fallback


def token_count(text: str) -> int:
    return len(_enc.encode(text))


def safe_inject(content: str, max_tokens: int = MAX_INJECT_TOKENS) -> str:
    """
    Truncate content to stay within a token budget before injecting into a prompt.
    Appends a visible notice when truncation occurs.
    """
    tokens = _enc.encode(content)
    if len(tokens) <= max_tokens:
        return content
    truncated = _enc.decode(tokens[:max_tokens])
    return (
        truncated
        + f"\n... [TRUNCATED — {len(tokens)} tokens total, showing first {max_tokens}]"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TOOL FACTORY  (one sandboxed set of tools per agent)
# ─────────────────────────────────────────────────────────────────────────────

def make_file_tools(agent_name: str, dry_run: bool = False) -> list:
    """
    Build [read_folder, read_file, write_file] tools for one agent.

    Sandboxing rules:
      write_file  → only to this agent's own directory, allowed extensions only
      read_file   → own directory first, then sibling directories (read-only)
                    Enables cross-agent collaboration: coding agent can read
                    systems agent's requirements.csv without any special wiring.
    """
    sandbox  = AGENT_DIRS[agent_name]
    allowed  = ALLOWED_WRITE_EXTENSIONS[agent_name]
    all_dirs = list(AGENT_DIRS.values())

    # ── read_folder ───────────────────────────────────────────────────────────
    def read_folder(subfolder: str = "") -> str:
        """List files in this agent's output directory."""
        target = sandbox / subfolder if subfolder else sandbox
        if not target.exists():
            return f"Directory not found: {target}"
        files = sorted(f for f in target.iterdir() if f.is_file())
        if not files:
            return "Directory is empty."
        return "\n".join(f"{f.name}  ({f.stat().st_size} bytes)" for f in files)

    # ── read_file ─────────────────────────────────────────────────────────────
    def read_file(filename: str) -> str:
        """
        Read a file by name. Searches own folder first, then other agents'
        folders for cross-agent collaboration. Content is token-limited.
        """
        candidates = [sandbox / filename] + [d / filename for d in all_dirs]
        for path in candidates:
            if path.exists() and path.is_file():
                try:
                    raw = path.read_text(encoding="utf-8")
                    injected = safe_inject(raw)
                    origin = "own" if path.parent == sandbox else path.parent.name
                    record_step(
                        agent_name, "read_file", path.name,
                        f"Read {filename} ({token_count(raw)} tokens, from {origin} folder)"
                    )
                    return injected
                except Exception as e:
                    return f"Error reading {filename}: {e}"
        return f"File not found: {filename}"

    # ── write_file ────────────────────────────────────────────────────────────
    def write_file(filename: str, content: str) -> str:
        """Write content to a file in this agent's output directory."""
        ext = Path(filename).suffix.lower()
        if ext not in allowed:
            return (
                f"Extension '{ext}' not allowed for {agent_name} agent. "
                f"Allowed: {sorted(allowed)}"
            )
        path = sandbox / filename
        if dry_run:
            record_step(
                agent_name, "write_file[DRY]", filename,
                f"DRY RUN: would write {filename} ({len(content.splitlines())} lines)"
            )
            return f"[DRY RUN] Would write → {path}"
        path.write_text(content, encoding="utf-8")
        lines = len(content.splitlines())
        record_step(
            agent_name, "write_file", filename,
            f"Wrote {filename} ({lines} lines, {token_count(content)} tokens)"
        )
        return f"Success: wrote {filename} ({lines} lines) → {path}"

    return [
        StructuredTool.from_function(
            func=read_folder,
            name="read_folder",
            description=(
                "List files in this agent's output directory. "
                "Optionally pass a subfolder name."
            ),
        ),
        StructuredTool.from_function(
            func=read_file,
            name="read_file",
            description=(
                "Read a file by name. Searches own folder first, then other "
                "agents' folders for cross-agent collaboration. "
                "Large files are automatically token-truncated."
            ),
        ),
        StructuredTool.from_function(
            func=write_file,
            name="write_file",
            description=(
                f"Write content to a file in this agent's output directory. "
                f"Allowed extensions for {agent_name}: {sorted(allowed)}"
            ),
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPTS
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPTS = {

    "systems": """\
You are a senior systems engineer. Your job is to translate a project goal
into clear, structured requirements that a developer can implement directly.

RULES:
- Produce 5-10 concrete, testable requirements.
- Save them as requirements.csv with exactly these columns:
    id, title, description, priority, status
  where priority is High / Med / Low and status is Open.
- Do not add extra columns or change column names.
- After saving, return a 2-3 sentence summary of what you defined.

Your output directory already exists. Write directly using write_file.""",

    "coding": """\
You are a senior Python engineer. Your job is to implement working code
that satisfies the project requirements.

RULES:
- Always start by calling read_file("requirements.csv") to load requirements.
- Write clean, well-documented Python (docstrings + inline comments).
- Save your implementation to a descriptively named .py file.
- After saving, return a brief summary: what you built and which
  requirement IDs your implementation covers.

Your output directory already exists. Write directly using write_file.""",

    "orchestrator": """\
You are a project orchestrator coordinating two specialist agents:
  - systems_agent  — breaks goals into requirements, writes requirements.csv
  - coding_agent   — reads requirements and writes Python implementation

YOUR WORKFLOW for every goal (follow this order):
1. Call systems_agent with the goal to define and save requirements.
2. Call coding_agent to implement the requirements.
3. If a key requirement is clearly unaddressed in the code, request one
   targeted revision from coding_agent (pass specific feedback). Max 1 revision.
4. Return a concise final project summary:
   agents called, files created, requirement coverage notes.

Keep your delegation prompts specific and actionable.""",

}


# ─────────────────────────────────────────────────────────────────────────────
# AGENT FACTORY
# ─────────────────────────────────────────────────────────────────────────────

def build_agent(role: str, llm: ChatOpenAI, tools: list):
    """Build a stateless LangChain 1.x agent graph for the given role."""
    return create_agent(llm, tools=tools, system_prompt=SYSTEM_PROMPTS[role])


# ─────────────────────────────────────────────────────────────────────────────
# AGENT INVOCATION  (stateless — every call is a fresh graph run)
# ─────────────────────────────────────────────────────────────────────────────

def invoke_agent(agent, task: str, label: str) -> str:
    """
    Stream an agent graph run, printing tool activity in real time.
    Returns the agent's final text response.
    """
    print(f"\n{'─' * 60}")
    print(f"[{label.upper()}]")
    print(f"{task[:200]}")
    print(f"{'─' * 60}")

    final_state = None
    for step in agent.stream(
        {"messages": [HumanMessage(content=task)]},
        stream_mode="values",
    ):
        final_state = step
        msgs = step.get("messages", [])
        if not msgs:
            continue
        last = msgs[-1]

        # Print tool calls as they happen
        if hasattr(last, "tool_calls") and last.tool_calls:
            for tc in last.tool_calls:
                args_preview = ", ".join(
                    f"{k}={repr(v)[:40]}" for k, v in tc["args"].items()
                )
                print(f"  -> {tc['name']}({args_preview})")

        # Print tool results
        elif hasattr(last, "tool_call_id") and last.tool_call_id:
            print(f"      = {str(last.content)[:120]}")

    if final_state:
        return final_state["messages"][-1].content
    return "(no response)"


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR TOOLS  (sub-agents wrapped as callable tools)
# ─────────────────────────────────────────────────────────────────────────────

def make_orchestrator_tools(llm: ChatOpenAI, dry_run: bool = False) -> list:
    """
    Wrap each sub-agent as a LangChain tool the orchestrator agent can call.

    Context injection:
      - systems_agent receives the raw goal only (no history needed on first call).
      - coding_agent always receives the current state summary prepended to its
        task — so it knows what the systems agent produced without being told.
      - Both are token-capped before injection.
    """
    systems_agent = build_agent("systems", llm, make_file_tools("systems", dry_run))
    coding_agent  = build_agent("coding",  llm, make_file_tools("coding",  dry_run))

    def call_systems_agent(task: str) -> str:
        """Delegate a requirements definition task to the systems engineering agent."""
        output = invoke_agent(systems_agent, task, "systems agent")
        record_step("systems", "agent_call", "", output[:300])
        return output

    def call_coding_agent(task: str) -> str:
        """Delegate a coding task to the Python coding agent."""
        # Inject current state so the coding agent knows what requirements exist
        ctx       = safe_inject(build_state_summary(), max_tokens=STATE_SUMMARY_TOKENS)
        full_task = f"{ctx}\n\n---\nTASK: {task}"
        output    = invoke_agent(coding_agent, full_task, "coding agent")
        record_step("coding", "agent_call", "", output[:300])
        return output

    return [
        StructuredTool.from_function(
            func=call_systems_agent,
            name="systems_agent",
            description=(
                "Delegate to the systems engineering agent. It will define "
                "requirements and save them to requirements.csv. "
                "Pass a clear task description that includes the full project goal."
            ),
        ),
        StructuredTool.from_function(
            func=call_coding_agent,
            name="coding_agent",
            description=(
                "Delegate to the Python coding agent. It reads requirements.csv "
                "and writes .py implementation files. "
                "Current project context is injected automatically."
            ),
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────────────────────────────────────

def run(goal: str, llm: ChatOpenAI, dry_run: bool = False) -> None:
    state["goal"] = goal
    record_step("orchestrator", "start", "", f"Goal received: {goal}")

    orchestrator = build_agent(
        "orchestrator", llm, make_orchestrator_tools(llm, dry_run)
    )

    initial_task = (
        f"Goal: {goal}\n\n"
        f"{build_state_summary()}\n\n"
        "Execute the full workflow: define requirements → implement code → final summary."
    )

    print(f"\n{'=' * 60}")
    print(f"GOAL: {goal}")
    if dry_run:
        print("MODE: DRY RUN (no files will be written)")
    print(f"{'=' * 60}")

    final_summary = invoke_agent(orchestrator, initial_task, "orchestrator")

    print(f"\n{'=' * 60}")
    print("FINAL SUMMARY")
    print(f"{'=' * 60}")
    print(final_summary)
    print(f"\nWork log : {WORK_LOG}")
    print(f"Outputs  : {OUTPUT_DIR}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-agent system: orchestrator → systems engineer + coder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python multi_agent.py --goal "Build a CSV data validator tool"
  python multi_agent.py --goal "Build a task queue manager" --dry-run
        """,
    )
    parser.add_argument("--goal",    required=True, help="Project goal for the agents")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate without writing files")
    parser.add_argument("--api-key", default=None,
                        help="OpenAI API key (or set OPENAI_API_KEY env var)")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit(
            "OpenAI API key required.\n"
            "  Option 1: --api-key sk-...\n"
            "  Option 2: set the OPENAI_API_KEY environment variable"
        )

    setup()
    llm = ChatOpenAI(model=MODEL, api_key=api_key, temperature=0)
    run(goal=args.goal, llm=llm, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
