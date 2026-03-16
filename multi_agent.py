#!/usr/bin/env python3
"""
multi_agent.py — LangChain 1.x multi-agent system (GPT-4o)

Architecture:
    Orchestrator Agent
        ├── Systems Engineering Agent  ->  output/systems/
        └── Coding Agent               ->  output/coding/

Agent configuration:
    All agents are defined in AGENT_REGISTRY as AgentConfig dataclasses.
    Adding a new agent is a single block — no other code needs to change.
    The orchestrator's prompt and tool list are generated from the registry
    at build time, so they stay in sync automatically.

    Each AgentConfig declares:
      name               unique id and output subfolder name
      description        one-liner used in the orchestrator's roster and tool docs
      system_prompt      full instructions; use {var} placeholders for dynamic values
      allowed_extensions write sandbox (empty set = read-only agent)
      handoffs           names of agents this agent can delegate to
      prompt_vars        static substitutions resolved at build time
    Agents with handoffs also get {agent_roster} injected automatically.

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
from dataclasses import dataclass, field
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
ORCHESTRATOR_NAME    = "orchestrator"  # which registry entry drives the top-level run


# ─────────────────────────────────────────────────────────────────────────────
# AGENT CONFIG  (single source of truth for every agent)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AgentConfig:
    """
    Defines one agent's complete identity.

    Fields:
        name               Unique id. Also used as the output subfolder name and
                           the tool name exposed to the orchestrator ({name}_agent).
        description        One-liner describing what this agent does.
                           Shown in the orchestrator's roster and as the tool docstring.
        system_prompt      Full instruction string for the LLM. Supports {var}
                           placeholders resolved at build time via prompt_vars.
                           Agents with handoffs also receive {agent_roster} automatically.
        allowed_extensions Set of file extensions this agent may write.
                           Empty set = read-only (e.g. orchestrator).
        handoffs           Ordered list of agent names this agent can delegate to.
                           Drives tool creation — no other wiring needed.
        prompt_vars        Static key/value substitutions resolved in system_prompt
                           at build time. Dynamic values (like agent_roster) are
                           injected automatically and do not need to appear here.
    """
    name:               str
    description:        str
    system_prompt:      str
    allowed_extensions: set[str]         = field(default_factory=set)
    handoffs:           list[str]        = field(default_factory=list)
    prompt_vars:        dict[str, str]   = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# AGENT REGISTRY
# To add a new agent: add an AgentConfig entry below and reference its name in
# the orchestrator's handoffs list. Nothing else needs to change.
# ─────────────────────────────────────────────────────────────────────────────

AGENT_REGISTRY: dict[str, AgentConfig] = {cfg.name: cfg for cfg in [

    AgentConfig(
        name        = "systems",
        description = "breaks goals into requirements, writes {requirements_file}",
        system_prompt = """\
You are a senior systems engineer. Your job is to translate a project goal
into clear, structured requirements that a developer can implement directly.

RULES:
- Produce 5-10 concrete, testable requirements.
- Save them as {requirements_file} with exactly these columns:
    id, title, description, priority, status
  where priority is High / Med / Low and status is Open.
- Do not add extra columns or change column names.
- After saving, return a 2-3 sentence summary of what you defined.

Your output directory already exists. Write directly using write_file.""",
        allowed_extensions = {".csv", ".md", ".txt"},
        handoffs           = [],
        prompt_vars        = {"requirements_file": "requirements.csv"},
    ),

    AgentConfig(
        name        = "coding",
        description = "reads {requirements_file} and writes Python implementation",
        system_prompt = """\
You are a senior Python engineer. Your job is to implement working code
that satisfies the project requirements.

RULES:
- Always start by calling read_file("{requirements_file}") to load requirements.
- Write clean, well-documented Python (docstrings + inline comments).
- Save your implementation to a descriptively named .py file.
- After saving, return a brief summary: what you built and which
  requirement IDs your implementation covers.

Your output directory already exists. Write directly using write_file.""",
        allowed_extensions = {".py", ".html", ".md", ".txt"},
        handoffs           = [],
        prompt_vars        = {"requirements_file": "requirements.csv"},
    ),

    AgentConfig(
        name        = ORCHESTRATOR_NAME,
        description = "coordinates all specialist agents toward the project goal",
        system_prompt = """\
You are a project orchestrator coordinating these specialist agents:
{agent_roster}

YOUR WORKFLOW for every goal (follow this order):
1. Delegate to agents in logical sequence based on their descriptions.
2. Pass relevant context from prior agents' outputs to subsequent agents.
3. Request at most one targeted revision per agent if output is incomplete.
4. Return a concise final summary: agents called, files created, coverage notes.

Keep your delegation prompts specific and actionable.""",
        allowed_extensions = set(),          # orchestrator does not write files
        handoffs           = ["systems", "coding"],
        prompt_vars        = {},             # {agent_roster} is auto-injected
    ),

]}


# ─────────────────────────────────────────────────────────────────────────────
# SETUP  (derives directories from registry, not hardcoded)
# ─────────────────────────────────────────────────────────────────────────────

def agent_dir(cfg: AgentConfig) -> Path:
    """Output directory for an agent — OUTPUT_DIR / agent.name."""
    return OUTPUT_DIR / cfg.name


def setup() -> None:
    """Create all agent output directories and initialize the work log."""
    dirs = [OUTPUT_DIR] + [
        agent_dir(cfg) for cfg in AGENT_REGISTRY.values()
        if cfg.allowed_extensions          # only agents that write files need a dir
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    if not WORK_LOG.exists():
        with open(WORK_LOG, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["timestamp", "agent", "action", "file", "note"])


# ─────────────────────────────────────────────────────────────────────────────
# SHARED STATE
# ─────────────────────────────────────────────────────────────────────────────

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
    """Compact snapshot of completed work, safe to inject into any prompt."""
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
    _enc = tiktoken.get_encoding("cl100k_base")


def token_count(text: str) -> int:
    return len(_enc.encode(text))


def safe_inject(content: str, max_tokens: int = MAX_INJECT_TOKENS) -> str:
    """Truncate content to a token budget. Appends a notice when cut."""
    tokens = _enc.encode(content)
    if len(tokens) <= max_tokens:
        return content
    truncated = _enc.decode(tokens[:max_tokens])
    return (
        truncated
        + f"\n... [TRUNCATED -- {len(tokens)} tokens total, showing first {max_tokens}]"
    )


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT RESOLUTION  (applies prompt_vars + auto-injects agent_roster)
# ─────────────────────────────────────────────────────────────────────────────

def resolve_prompt(cfg: AgentConfig, registry: dict[str, AgentConfig]) -> str:
    """
    Resolve a config's system_prompt at build time.

    1. If the agent has handoffs, build an {agent_roster} string from the
       descriptions of the target agents and inject it automatically.
    2. Apply any static prompt_vars via str.format().

    This keeps the prompt template readable while making the final string
    fully concrete before it reaches the LLM.
    """
    vars_: dict[str, str] = dict(cfg.prompt_vars)

    if cfg.handoffs:
        roster_lines = [
            f"  - {name}_agent  --  {registry[name].description.format(**registry[name].prompt_vars)}"
            for name in cfg.handoffs
            if name in registry
        ]
        vars_["agent_roster"] = "\n".join(roster_lines)

    return cfg.system_prompt.format(**vars_) if vars_ else cfg.system_prompt


# ─────────────────────────────────────────────────────────────────────────────
# TOOL FACTORY  (sandboxed per agent, derived from AgentConfig)
# ─────────────────────────────────────────────────────────────────────────────

def make_file_tools(cfg: AgentConfig, registry: dict[str, AgentConfig],
                    dry_run: bool = False) -> list:
    """
    Build [read_folder, read_file, write_file] tools for one agent.

    Sandboxing:
      write_file  -> cfg's own directory only, cfg.allowed_extensions only
      read_file   -> own directory first, then all other agent directories
                     (read-only cross-agent access for collaboration)
    """
    sandbox  = agent_dir(cfg)
    allowed  = cfg.allowed_extensions
    all_dirs = [agent_dir(c) for c in registry.values() if c.allowed_extensions]

    def read_folder(subfolder: str = "") -> str:
        """List files in this agent's output directory."""
        target = sandbox / subfolder if subfolder else sandbox
        if not target.exists():
            return f"Directory not found: {target}"
        files = sorted(f for f in target.iterdir() if f.is_file())
        if not files:
            return "Directory is empty."
        return "\n".join(f"{f.name}  ({f.stat().st_size} bytes)" for f in files)

    def read_file(filename: str) -> str:
        """Read a file. Searches own folder first, then all other agent folders."""
        candidates = [sandbox / filename] + [d / filename for d in all_dirs]
        for path in candidates:
            if path.exists() and path.is_file():
                try:
                    raw     = path.read_text(encoding="utf-8")
                    origin  = "own" if path.parent == sandbox else path.parent.name
                    record_step(
                        cfg.name, "read_file", path.name,
                        f"Read {filename} ({token_count(raw)} tokens, from {origin} folder)"
                    )
                    return safe_inject(raw)
                except Exception as e:
                    return f"Error reading {filename}: {e}"
        return f"File not found: {filename}"

    def write_file(filename: str, content: str) -> str:
        """Write content to a file in this agent's output directory."""
        ext = Path(filename).suffix.lower()
        if ext not in allowed:
            return (
                f"Extension '{ext}' not allowed for {cfg.name} agent. "
                f"Allowed: {sorted(allowed)}"
            )
        path = sandbox / filename
        if dry_run:
            record_step(
                cfg.name, "write_file[DRY]", filename,
                f"DRY RUN: would write {filename} ({len(content.splitlines())} lines)"
            )
            return f"[DRY RUN] Would write -> {path}"
        path.write_text(content, encoding="utf-8")
        lines = len(content.splitlines())
        record_step(
            cfg.name, "write_file", filename,
            f"Wrote {filename} ({lines} lines, {token_count(content)} tokens)"
        )
        return f"Success: wrote {filename} ({lines} lines) -> {path}"

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
                f"Allowed extensions: {sorted(allowed)}"
            ),
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# AGENT FACTORY
# ─────────────────────────────────────────────────────────────────────────────

def build_agent(cfg: AgentConfig, llm: ChatOpenAI, tools: list,
                registry: dict[str, AgentConfig]):
    """Build a stateless LangChain 1.x agent graph from an AgentConfig."""
    prompt = resolve_prompt(cfg, registry)
    return create_agent(llm, tools=tools, system_prompt=prompt)


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

        if hasattr(last, "tool_calls") and last.tool_calls:
            for tc in last.tool_calls:
                args_preview = ", ".join(
                    f"{k}={repr(v)[:40]}" for k, v in tc["args"].items()
                )
                print(f"  -> {tc['name']}({args_preview})")

        elif hasattr(last, "tool_call_id") and last.tool_call_id:
            print(f"      = {str(last.content)[:120]}")

    if final_state:
        return final_state["messages"][-1].content
    return "(no response)"


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR TOOLS  (derived from orchestrator_cfg.handoffs — no hardcoding)
# ─────────────────────────────────────────────────────────────────────────────

def make_handoff_tools(orch_cfg: AgentConfig, registry: dict[str, AgentConfig],
                       llm: ChatOpenAI, dry_run: bool = False) -> list:
    """
    Build one callable tool per agent listed in orch_cfg.handoffs.
    The tool name is {agent_name}_agent, the docstring is cfg.description.

    Context injection rule:
      - Agents with predecessors in the handoff list receive the current state
        summary prepended to their task (so they know what prior agents produced).
      - The first agent in the handoff list receives only the raw task.
    """
    tools = []

    for i, target_name in enumerate(orch_cfg.handoffs):
        target_cfg  = registry[target_name]
        sub_tools   = make_file_tools(target_cfg, registry, dry_run)
        sub_agent   = build_agent(target_cfg, llm, sub_tools, registry)
        inject_ctx  = i > 0    # inject state summary for all but the first agent

        def make_caller(agent, name: str, cfg: AgentConfig, with_ctx: bool):
            def call(task: str) -> str:
                if with_ctx:
                    ctx  = safe_inject(build_state_summary(), max_tokens=STATE_SUMMARY_TOKENS)
                    task = f"{ctx}\n\n---\nTASK: {task}"
                output = invoke_agent(agent, task, f"{name} agent")
                record_step(name, "agent_call", "", output[:300])
                return output
            call.__doc__ = cfg.description
            call.__name__ = f"call_{name}_agent"
            return call

        caller = make_caller(sub_agent, target_name, target_cfg, inject_ctx)

        tools.append(StructuredTool.from_function(
            func        = caller,
            name        = f"{target_name}_agent",
            description = (
                f"{target_cfg.description}. "
                f"Writes to: output/{target_name}/. "
                + ("Context from prior agents is injected automatically."
                   if inject_ctx else
                   "Pass the full project goal as the task.")
            ),
        ))

    return tools


# ─────────────────────────────────────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────────────────────────────────────

def run(goal: str, llm: ChatOpenAI, dry_run: bool = False,
        registry: dict[str, AgentConfig] = AGENT_REGISTRY) -> None:

    state["goal"] = goal
    record_step(ORCHESTRATOR_NAME, "start", "", f"Goal received: {goal}")

    orch_cfg     = registry[ORCHESTRATOR_NAME]
    orch_tools   = make_handoff_tools(orch_cfg, registry, llm, dry_run)
    orchestrator = build_agent(orch_cfg, llm, orch_tools, registry)

    initial_task = (
        f"Goal: {goal}\n\n"
        f"{build_state_summary()}\n\n"
        "Execute the full workflow: define requirements -> implement code -> final summary."
    )

    print(f"\n{'=' * 60}")
    print(f"GOAL: {goal}")
    if dry_run:
        print("MODE: DRY RUN (no files will be written)")
    print(f"{'=' * 60}")

    final_summary = invoke_agent(orchestrator, initial_task, ORCHESTRATOR_NAME)

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
        description="Multi-agent system: orchestrator -> systems engineer + coder",
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
