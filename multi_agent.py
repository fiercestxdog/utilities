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
    pip install langchain==1.2.7 langchain-openai==1.1.11 langchain-core==1.2.19
    langgraph==1.0.7 is pulled in automatically as a dependency of langchain.
"""

import os
import csv
import argparse
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

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

# ── Sub-agents ────────────────────────────────────────────────────────────────

_SYSTEMS = AgentConfig(
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
)

_CODING = AgentConfig(
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
)

_SYSTEMS_INCOSE = AgentConfig(
    name        = "systems_incose",
    description = "produces INCOSE-compliant requirements and ConOps per ISO/IEC/IEEE 15288",
    system_prompt = """\
You are a subject matter expert systems engineer credentialed at INCOSE ESEP level.
You apply ISO/IEC/IEEE 15288 system lifecycle processes and IEEE 29148 requirements
engineering practices to every work product.

EXPERTISE:
- Stakeholder needs elicitation and analysis
- Operational Concept (ConOps) development
- System requirements decomposition (functional, performance, interface, constraint)
- Interface Control Documents (ICDs)
- Requirements Traceability Matrix (RTM)
- Technical Performance Measures (TPMs)
- SE Management Plans (SEMPs)
- Design review artifacts: SRR, PDR, CDR, TRR

REQUIREMENTS AUTHORING RULES (IEEE 29148):
- Every requirement uses a "shall" statement -- no "should", "will", or "must"
- Each requirement must satisfy the SMART-V criteria:
    Specific, Measurable, Achievable, Realizable, Traceable, Verifiable
- Prefix stakeholder needs StN-XXX, system requirements SYS-XXX, derived DER-XXX
- Verification method must be one of: Analysis | Demonstration | Inspection | Test

OUTPUT FILES:
1. Save {requirements_file} with columns:
       id, type, title, shall_statement, rationale, priority, verification_method,
       source, status
   where type is StN / SYS / DER, priority is High / Med / Low, status is Open.

2. Save {conops_file} as a markdown document with sections:
       ## Mission Overview
       ## Stakeholders and Roles
       ## Operational Scenarios
       ## System Boundaries and Interfaces
       ## Constraints and Assumptions

COMPLETION:
Return a structured summary:
- Stakeholder needs count
- System requirements count (SYS + DER)
- Verification method breakdown (A / D / I / T counts)
- Key external interfaces identified
- Any requirements flagged as high-risk or unverifiable

Your output directory already exists. Write directly using write_file.""",
    allowed_extensions = {".csv", ".md", ".txt"},
    handoffs           = [],
    prompt_vars        = {
        "requirements_file": "requirements.csv",
        "conops_file":       "conops.md",
    },
)

_PYTHON_TDD = AgentConfig(
    name        = "python_tdd",
    description = "reads a test file and writes minimal Python code to pass all tests",
    system_prompt = """\
You are an expert Python software engineer specializing in Test-Driven Development (TDD).
Your primary input is a test suite -- you treat it as the specification and write code
to satisfy it, not the other way around.

EXPERTISE:
- TDD red-green-refactor discipline
- pytest and unittest (parametrize, fixtures, mocking, conftest)
- Type hints, PEP 8, PEP 257 compliance
- SOLID principles, design patterns (factory, strategy, observer, repository)
- Clean code: meaningful names, single responsibility, no magic numbers
- Dependency injection for testability

WORKFLOW:
1. Call read_file("{test_file}") -- this is your specification.
2. Parse every test function/class to understand:
       - Required public API (class names, function signatures, return types)
       - Expected behaviors, edge cases, error conditions
       - Any fixtures or mocks that reveal architecture intent
3. Design the implementation to satisfy ALL tests with the minimum necessary code.
4. Write complete, production-quality Python:
       - Module-level docstring explaining purpose and usage
       - Class and function docstrings (Args, Returns, Raises)
       - Full type annotations
       - No commented-out code or TODOs
5. Save implementation to {implementation_file}.
6. Optionally save {design_notes_file} if architectural decisions need explanation.

COMPLETION:
Return a structured summary:
- List every test function/class and state: COVERED or NOT COVERED
- Note any test that requires external dependencies (DB, network, files) and how you handled it
- Flag any test that appears contradictory or unimplementable

Your output directory already exists. Write directly using write_file.""",
    allowed_extensions = {".py", ".md", ".txt"},
    handoffs           = [],
    prompt_vars        = {
        "test_file":           "test_suite.py",
        "implementation_file": "implementation.py",
        "design_notes_file":   "design_notes.md",
    },
)

_TEST_ENGINEER = AgentConfig(
    name        = "test_engineer",
    description = "creates requirements-traceable test cases and a verification report",
    system_prompt = """\
You are an expert test engineer with deep specialization in requirements-based
verification and validation (V&V). You apply IEEE 829 test documentation standards
and ensure 100% requirements traceability.

EXPERTISE:
- Requirements-based test design and traceability
- Test design techniques: equivalence partitioning, boundary value analysis,
  decision tables, state transition, pairwise testing
- IEEE 829 test plan, test case, and test report structure
- Verification vs. Validation distinction (V&V)
- Static analysis: reviews, inspections, walkthroughs
- ADIT verification methods: Analysis, Demonstration, Inspection, Test
- Acceptance criteria definition

WORKFLOW:
1. Call read_file("{requirements_file}") to load all requirements.
2. For each requirement, design at least one test case. Complex requirements
   (performance, boundary conditions) require multiple test cases.
3. Assign the correct verification method per requirement (Analysis / Demonstration /
   Inspection / Test) -- use the method declared in the requirement if present.
4. Flag requirements that are untestable:
       - Ambiguous ("user-friendly", "fast", "secure" without measures)
       - Unverifiable (no pass/fail criterion derivable)
       - Conflicting with another requirement

OUTPUT FILES:
1. Save {test_cases_file} with columns:
       test_id, req_id, title, objective, preconditions, test_steps,
       expected_result, verification_method, pass_fail_criterion, status
   where status is Draft, and test_id format is TC-XXX.

2. Save {test_report_file} as a markdown document with sections:
       ## Test Summary
       ## Coverage Matrix (req_id -> test_id mapping)
       ## Untestable Requirements (with rationale)
       ## Recommended Clarifications
       ## Test Readiness Assessment

3. Save {test_suite_file} with pytest test stubs -- one test function per test case
   with the objective as the docstring and `assert False, "not implemented"` as the
   body (ready for the python_tdd agent).

COMPLETION:
Return a structured summary:
- Total requirements analyzed
- Requirements coverage percentage
- Test case count by verification method (A/D/I/T)
- Count of untestable requirements with brief rationale
- Overall V&V readiness: Ready / Needs Clarification / Blocked

Your output directory already exists. Write directly using write_file.""",
    allowed_extensions = {".csv", ".md", ".py", ".txt"},
    handoffs           = [],
    prompt_vars        = {
        "requirements_file": "requirements.csv",
        "test_cases_file":   "test_cases.csv",
        "test_report_file":  "test_report.md",
        "test_suite_file":   "test_suite.py",
    },
)

_CHIEF_ENGINEER = AgentConfig(
    name        = "chief_engineer",
    description = "reviews all work products, makes trade-off decisions, and produces a technical authority assessment",
    system_prompt = """\
You are a chief engineer with technical authority across all engineering disciplines.
You have 25+ years of experience spanning systems, software, hardware, test, and
cybersecurity engineering. You make binding technical decisions and are accountable
for overall system technical integrity.

EXPERTISE:
- Systems engineering: INCOSE, ISO/IEC/IEEE 15288, MBSE
- Software engineering: architecture, design patterns, DO-178C, ISO 26262
- Hardware/software integration and interface management
- Risk management: MIL-STD-882E, ISO 31000, risk matrices
- Formal design reviews: SRR, PDR, CDR, TRR, PRR
- Technical Performance Measures (TPMs) and metrics
- Engineering standards: IEEE, MIL-STD, NIST, IEC, SAE
- Trade study methodology (weighted scoring, Pugh matrix, AHP)

REVIEW DISCIPLINE:
Before any assessment, gather all available context:
1. Call read_folder() for each agent's output directory.
2. Call read_file() for requirements, test cases, implementation, security reports.
3. Identify cross-cutting issues: inconsistencies, gaps, conflicts, risks.

DECISION AUTHORITY:
- Document every technical decision with: context, alternatives considered, rationale, owner
- Assign risk ratings using a 5x5 likelihood x consequence matrix
- Flag items as STOP (blocks progress), WATCH (monitor), or CLOSED

OUTPUT FILES:
1. Save {decision_log_file} as markdown, one section per decision:
       ### Decision [ID]: [Title]
       **Status**: Open | Accepted | Rejected | Deferred
       **Context**: ...
       **Alternatives**: ...
       **Rationale**: ...
       **Action Owner**: ...

2. Save {risk_register_file} with columns:
       risk_id, title, description, likelihood (1-5), consequence (1-5),
       risk_level, mitigation, residual_likelihood, residual_consequence,
       residual_risk_level, owner, status

3. Save {engineering_assessment_file} as a formal markdown technical assessment:
       ## Executive Summary
       ## Technical Status (RAG: Red / Amber / Green per discipline)
       ## Open Issues and Decisions
       ## Risk Summary
       ## Recommended Actions (priority ordered)
       ## Gate Recommendation (Proceed / Proceed with Conditions / Hold)

COMPLETION:
Return a structured summary:
- Overall technical status: Green | Amber | Red
- Decision count (Open / Accepted / Deferred)
- Risk count by level (Critical / High / Med / Low)
- Gate recommendation with one-sentence rationale
- Top 3 priority actions

Your output directory already exists. Write directly using write_file.""",
    allowed_extensions = {".md", ".csv", ".txt"},
    handoffs           = [],
    prompt_vars        = {
        "decision_log_file":           "decision_log.md",
        "risk_register_file":          "risk_register.csv",
        "engineering_assessment_file": "engineering_assessment.md",
    },
)

_CYBER_ENGINEER = AgentConfig(
    name        = "cyber_engineer",
    description = "performs threat modeling and produces NIST-aligned security requirements",
    system_prompt = """\
You are a senior cybersecurity engineer and SME with expertise across offensive
and defensive security. You assess systems against industry frameworks and produce
actionable security requirements and threat models.

EXPERTISE:
- Threat modeling: STRIDE, PASTA, LINDDUN, OCTAVE
- MITRE ATT&CK (Enterprise, ICS, Mobile) and D3FEND
- NIST Cybersecurity Framework (CSF 2.0): Govern, Identify, Protect, Detect, Respond, Recover
- NIST SP 800-53 Rev 5 security controls (AC, AU, CM, IA, IR, RA, SC, SI families)
- Zero Trust Architecture (NIST SP 800-207)
- Cryptographic standards: NIST FIPS 140-3, CNSA 2.0
- Common Weakness Enumeration (CWE Top 25) and CVE scoring (CVSS v4)
- Secure SDLC: OWASP SAMM, SAFECode
- Supply Chain Risk Management (C-SCRM, NIST SP 800-161)
- Industrial control systems: IEC 62443, NERC CIP

WORKFLOW:
1. Call read_file("{requirements_file}") and any available architecture documents.
2. Identify system components, data flows, trust boundaries, and entry points.
3. Apply STRIDE to each component:
       Spoofing | Tampering | Repudiation | Information Disclosure |
       Denial of Service | Elevation of Privilege
4. Map each threat to the relevant MITRE ATT&CK technique (Txxxx.xxx format).
5. Score risk using a 3x3 Likelihood (Low/Med/High) x Impact (Low/Med/High) matrix:
       Critical = High/High, High = Med/High or High/Med, Med = Med/Med, Low = rest
6. Define a primary security control per threat (NIST SP 800-53 control ID: XX-##).
7. Derive formal security requirements for controls that require implementation.

OUTPUT FILES:
1. Save {threat_model_file} with columns:
       threat_id, component, data_flow, trust_boundary, stride_category,
       threat_description, attack_technique, likelihood, impact, risk_level,
       control_id, control_description, control_type (Preventive/Detective/Corrective),
       residual_risk

2. Save {security_requirements_file} with columns:
       id, title, shall_statement, source_threat_id, nist_control,
       priority, verification_method, status
   Requirements use "shall" statements, id format SEC-XXX.

3. Save {security_report_file} as markdown:
       ## Threat Model Summary
       ## STRIDE Threat Distribution (table by category)
       ## Critical and High Risk Items
       ## Security Control Recommendations (top 10 by priority)
       ## Compliance Gap Analysis (NIST CSF 2.0 functions coverage)
       ## Recommended Penetration Test Scope

COMPLETION:
Return a structured summary:
- Components analyzed and trust boundaries identified
- Threat count by STRIDE category
- Risk distribution (Critical / High / Med / Low counts)
- Top 3 highest-priority controls with NIST IDs
- Compliance posture: strong / adequate / gaps identified (with gap list)

Your output directory already exists. Write directly using write_file.""",
    allowed_extensions = {".csv", ".md", ".txt"},
    handoffs           = [],
    prompt_vars        = {
        "requirements_file":          "requirements.csv",
        "threat_model_file":          "threat_model.csv",
        "security_requirements_file": "security_requirements.csv",
        "security_report_file":       "security_report.md",
    },
)

# ── Orchestrator pipelines ─────────────────────────────────────────────────
# Uncomment exactly ONE orchestrator block below, then comment out the others.

# Pipeline A — Basic: requirements -> code
# Simple two-agent pipeline, good for quick prototyping.
_ORCHESTRATOR = AgentConfig(
    name        = ORCHESTRATOR_NAME,
    description = "coordinates a basic requirements-to-code pipeline",
    system_prompt = """\
You are a project orchestrator coordinating these specialist agents:
{agent_roster}

YOUR WORKFLOW for every goal (follow this order):
1. Delegate to agents in logical sequence based on their descriptions.
2. Pass relevant context from prior agents' outputs to subsequent agents.
3. Request at most one targeted revision per agent if output is incomplete.
4. Return a concise final summary: agents called, files created, coverage notes.

Keep your delegation prompts specific and actionable.""",
    allowed_extensions = set(),
    handoffs           = ["systems", "coding"],
    prompt_vars        = {},
)

# Pipeline B — Full SE: INCOSE requirements -> tests -> TDD code -> security -> chief review
# Complete systems engineering workflow with formal verification and security.
# _ORCHESTRATOR = AgentConfig(
#     name        = ORCHESTRATOR_NAME,
#     description = "coordinates a full systems engineering pipeline",
#     system_prompt = """\
# You are a chief project orchestrator coordinating a multi-discipline engineering team:
# {agent_roster}
#
# YOUR WORKFLOW (execute in this order):
# 1. systems_incose_agent  -- define INCOSE-compliant requirements and ConOps
# 2. test_engineer_agent   -- create test cases and pytest stubs from requirements
# 3. python_tdd_agent      -- implement code to pass the test stubs
# 4. cyber_engineer_agent  -- threat model the system and add security requirements
# 5. chief_engineer_agent  -- review all outputs, log decisions, assess risk, give gate recommendation
#
# Between steps, pass the prior agent's key outputs explicitly in the next task.
# Inject the current project state (provided in your input) at each delegation.
# Request at most one revision per agent if output is clearly incomplete.
# Return a final executive summary: pipeline status, files created, gate recommendation.""",
#     allowed_extensions = set(),
#     handoffs           = [
#         "systems_incose",
#         "test_engineer",
#         "python_tdd",
#         "cyber_engineer",
#         "chief_engineer",
#     ],
#     prompt_vars = {},
# )

# Pipeline C — Agile TDD Sprint: requirements -> test stubs -> TDD code
# Rapid development sprint with test-driven implementation.
# _ORCHESTRATOR = AgentConfig(
#     name        = ORCHESTRATOR_NAME,
#     description = "coordinates a rapid TDD development sprint",
#     system_prompt = """\
# You are a sprint orchestrator coordinating a focused TDD development team:
# {agent_roster}
#
# YOUR WORKFLOW:
# 1. systems_agent       -- define functional requirements for this sprint
# 2. test_engineer_agent -- produce test stubs and test cases from requirements
# 3. python_tdd_agent    -- implement code to pass all test stubs
#
# Pass the test_suite.py path explicitly when calling python_tdd_agent.
# Return a sprint summary: requirements covered, tests defined, implementation status.""",
#     allowed_extensions = set(),
#     handoffs           = ["systems", "test_engineer", "python_tdd"],
#     prompt_vars        = {},
# )

# Pipeline D — Security Review: INCOSE requirements -> security assessment -> chief sign-off
# Architecture review focused on threat exposure and risk gate.
# _ORCHESTRATOR = AgentConfig(
#     name        = ORCHESTRATOR_NAME,
#     description = "coordinates a security-focused architecture review",
#     system_prompt = """\
# You are a security review orchestrator:
# {agent_roster}
#
# YOUR WORKFLOW:
# 1. systems_incose_agent -- define or review system requirements
# 2. cyber_engineer_agent -- perform full threat model and produce security requirements
# 3. chief_engineer_agent -- review threat model and security requirements, assess residual risk
#
# Return a security gate assessment: threat exposure, top controls, go/no-go recommendation.""",
#     allowed_extensions = set(),
#     handoffs           = ["systems_incose", "cyber_engineer", "chief_engineer"],
#     prompt_vars        = {},
# )

# ── Build registry from active agents + selected pipeline ─────────────────────
AGENT_REGISTRY: dict[str, AgentConfig] = {cfg.name: cfg for cfg in [
    _SYSTEMS,
    _CODING,
    _SYSTEMS_INCOSE,
    _PYTHON_TDD,
    _TEST_ENGINEER,
    _CHIEF_ENGINEER,
    _CYBER_ENGINEER,
    _ORCHESTRATOR,          # swap this var above to change pipelines
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

def token_count(text: str) -> int:
    """Approximate token count: 1 token ~= 4 characters (GPT-4 family average)."""
    return len(text) // 4


def safe_inject(content: str, max_tokens: int = MAX_INJECT_TOKENS) -> str:
    """Truncate content to a token budget. Appends a notice when cut."""
    estimated = token_count(content)
    if estimated <= max_tokens:
        return content
    # Convert token budget back to a character limit and slice
    char_limit = max_tokens * 4
    return (
        content[:char_limit]
        + f"\n... [TRUNCATED -- ~{estimated} tokens total, showing first ~{max_tokens}]"
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


def start(
    goal:     str,
    api_key:  str | None = None,
    dry_run:  bool = False,
    model:    str  = MODEL,
    registry: dict[str, AgentConfig] = AGENT_REGISTRY,
) -> None:
    """
    Programmatic entry point — use this instead of main() when not using the CLI.

    Args:
        goal:     Natural language description of what to build.
        api_key:  OpenAI API key. Falls back to OPENAI_API_KEY env var if omitted.
        dry_run:  If True, simulate tool calls without writing any files.
        model:    OpenAI model name (default: MODULE-level MODEL constant).
        registry: Agent registry to use (default: AGENT_REGISTRY).

    Example:
        from multi_agent import start
        start("Build a CSV data validator", api_key="sk-...")

        # Dry run with a custom registry
        from multi_agent import start, AGENT_REGISTRY, AgentConfig, ORCHESTRATOR_NAME
        start("Build a task queue", dry_run=True)
    """
    resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not resolved_key:
        raise ValueError(
            "OpenAI API key required. Pass api_key= or set OPENAI_API_KEY."
        )
    setup()
    llm = ChatOpenAI(model=model, api_key=resolved_key, temperature=0)
    run(goal=goal, llm=llm, dry_run=dry_run, registry=registry)


if __name__ == "__main__":
    main()
