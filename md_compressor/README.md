# Markdown Compressor

LLM-based context compression for markdown files. Reduces token count while preserving actionable information for downstream LLM tasks.

## Features

- **Intelligent compression**: Uses LLM to identify and remove low-value content while preserving critical information
- **Multiple modes**: Normal (~50%), Aggressive (~70%), Structure-preserving (~30%)
- **Provider flexibility**: Works with OpenAI, Gemini, Groq, or local Ollama
- **Large file support**: Automatic chunking for documents exceeding token limits
- **Token statistics**: Before/after token counts and reduction percentages

## Installation

```bash
pip install tiktoken  # Optional, for accurate token counting
pip install openai    # If using OpenAI provider
```

## CLI Usage

```bash
# Using default provider (LLMEngine with Gemini/Groq/Ollama fallback)
python compressor.py CLAUDE.md

# Using OpenAI
python compressor.py CLAUDE.md --provider openai --model gpt-4o-mini

# Aggressive compression (70%+)
python compressor.py CLAUDE.md --mode aggressive

# Structure-preserving (keeps hierarchy)
python compressor.py CLAUDE.md --mode structure

# Check token count only
python compressor.py CLAUDE.md --stats-only

# Specify output file
python compressor.py CLAUDE.md -o CLAUDE_MINI.md
```

## Python Usage

```python
from compressor import MarkdownCompressor

# Using OpenAI
compressor = MarkdownCompressor(provider="openai", model="gpt-4o-mini")
result = compressor.compress("CLAUDE.md")

print(result.compressed)       # The compressed markdown
print(result.stats())          # Token/char reduction stats
result.save("CLAUDE_MINI.md")  # Save to file

# Using LLMEngine (requires workspace setup)
compressor = MarkdownCompressor(provider="llmengine", mode="aggressive")
result = compressor.compress("README.md")
```

## Compression Modes

| Mode | Target Reduction | Use Case |
|------|------------------|----------|
| `normal` | ~50% | General documentation, balanced |
| `aggressive` | ~70% | Maximum compression, keeps only essentials |
| `structure` | ~30% | API docs, specs where hierarchy matters |

## How It Works

The compressor uses a carefully crafted system prompt (see `COMPRESSION_PROMPT.md`) that instructs the LLM to:

**Preserve:**
- File paths, URLs, commands, code snippets
- Function/class names, version numbers
- Error messages and solutions

**Remove:**
- Redundant explanations
- Marketing language, filler words
- Verbose transitions
- Obvious/inferable information

## Requirements

- Python 3.10+
- `tiktoken` (optional, for accurate token counting)
- One of: `openai`, `groq`, `google-genai`, or local Ollama
