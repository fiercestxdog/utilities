"""
Markdown Compressor - LLM-based context compression for markdown files.

Quick Start:
    from tools.md_compressor import MarkdownCompressor

    # Using workspace LLMEngine (Gemini -> Groq -> Ollama fallback)
    compressor = MarkdownCompressor()
    result = compressor.compress("CLAUDE.md")
    print(result.compressed)
    print(result.stats())

    # Using OpenAI directly
    compressor = MarkdownCompressor(provider="openai", model="gpt-4o-mini")
    result = compressor.compress("CLAUDE.md")
    result.save("CLAUDE_MINI.md")

CLI:
    python -m tools.md_compressor CLAUDE.md
    python -m tools.md_compressor CLAUDE.md --mode aggressive
    python -m tools.md_compressor CLAUDE.md --provider openai --model gpt-4o-mini
"""

from .compressor import (
    MarkdownCompressor,
    CompressionResult,
    count_tokens,
    chunk_by_headers,
    load_system_prompt,
    compress_with_openai,
    compress_with_llmengine,
)

__all__ = [
    "MarkdownCompressor",
    "CompressionResult",
    "count_tokens",
    "chunk_by_headers",
    "load_system_prompt",
    "compress_with_openai",
    "compress_with_llmengine",
]
