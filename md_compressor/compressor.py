"""
Markdown Compressor - LLM-based context compression for markdown files.

Uses intelligent prompt-based compression to reduce token count while
preserving actionable information for downstream LLM tasks.

Supports: OpenAI, Groq, Gemini, Ollama (via LLMEngine)
"""

import re
import argparse
from pathlib import Path
from typing import Literal

# Optional imports
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


# =============================================================================
# PROMPT LOADING
# =============================================================================

PROMPT_FILE = Path(__file__).parent / "COMPRESSION_PROMPT.md"

def load_system_prompt(mode: Literal["normal", "aggressive", "structure"] = "normal") -> str:
    """Load the compression system prompt from COMPRESSION_PROMPT.md."""

    if not PROMPT_FILE.exists():
        raise FileNotFoundError(f"Compression prompt not found: {PROMPT_FILE}")

    content = PROMPT_FILE.read_text(encoding="utf-8")

    # Extract the main system prompt (between first ``` and ```)
    match = re.search(r"## System Prompt\s*```(.*?)```", content, re.DOTALL)
    if not match:
        raise ValueError("Could not parse system prompt from COMPRESSION_PROMPT.md")

    base_prompt = match.group(1).strip()

    # Add mode-specific instructions
    if mode == "aggressive":
        aggressive_match = re.search(
            r"## Variant: Aggressive Mode.*?```(.*?)```",
            content, re.DOTALL
        )
        if aggressive_match:
            base_prompt += "\n\n" + aggressive_match.group(1).strip()

    elif mode == "structure":
        structure_match = re.search(
            r"## Variant: Structure-Preserving Mode.*?```(.*?)```",
            content, re.DOTALL
        )
        if structure_match:
            base_prompt += "\n\n" + structure_match.group(1).strip()

    return base_prompt


# =============================================================================
# TOKEN COUNTING
# =============================================================================

def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    """Count tokens using tiktoken (falls back to word estimate)."""
    if TIKTOKEN_AVAILABLE:
        try:
            enc = tiktoken.encoding_for_model(model)
            return len(enc.encode(text))
        except KeyError:
            # Model not found, use cl100k_base (GPT-4 encoding)
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
    else:
        # Rough estimate: ~4 chars per token
        return len(text) // 4


# =============================================================================
# CHUNKING
# =============================================================================

def chunk_by_headers(text: str, max_tokens: int = 6000, model: str = "gpt-4o-mini") -> list[str]:
    """
    Split markdown into chunks by headers, respecting token limits.

    Tries to keep sections together, only splitting if a section exceeds max_tokens.
    """
    # Split by h2 headers, keeping the delimiter
    sections = re.split(r'(^## .+$)', text, flags=re.MULTILINE)

    chunks = []
    current_chunk = ""

    for i, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue

        # Check if adding this section exceeds limit
        potential_chunk = current_chunk + "\n\n" + section if current_chunk else section

        if count_tokens(potential_chunk, model) > max_tokens:
            # Save current chunk if non-empty
            if current_chunk:
                chunks.append(current_chunk.strip())

            # Check if section itself is too large
            if count_tokens(section, model) > max_tokens:
                # Split large section by paragraphs
                paragraphs = section.split("\n\n")
                sub_chunk = ""
                for para in paragraphs:
                    if count_tokens(sub_chunk + "\n\n" + para, model) > max_tokens:
                        if sub_chunk:
                            chunks.append(sub_chunk.strip())
                        sub_chunk = para
                    else:
                        sub_chunk = sub_chunk + "\n\n" + para if sub_chunk else para
                current_chunk = sub_chunk
            else:
                current_chunk = section
        else:
            current_chunk = potential_chunk

    # Don't forget the last chunk
    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


# =============================================================================
# COMPRESSION BACKENDS
# =============================================================================

def compress_with_openai(
    text: str,
    model: str = "gpt-4o-mini",
    mode: Literal["normal", "aggressive", "structure"] = "normal",
    api_key: str | None = None
) -> str:
    """Compress using OpenAI API."""
    if not OPENAI_AVAILABLE:
        raise ImportError("OpenAI library not installed. Run: pip install openai")

    client = OpenAI(api_key=api_key) if api_key else OpenAI()
    system_prompt = load_system_prompt(mode)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        temperature=0
    )

    return response.choices[0].message.content


def compress_with_llmengine(
    text: str,
    mode: Literal["normal", "aggressive", "structure"] = "normal",
    force_local: bool = False
) -> str:
    """Compress using the workspace LLMEngine (Gemini/Groq/Ollama)."""
    # Import here to avoid circular dependency
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from tools.ai_chat.llm_engine import LLMEngine

    engine = LLMEngine(force_local=force_local)
    system_prompt = load_system_prompt(mode)

    # Build history with system prompt
    history = [{"role": "system", "content": system_prompt}]

    response = engine.chat(text, temp_history=history)

    # Strip the model header prefix if present (e.g., "[gemini-2.5-flash] ")
    if response.startswith("["):
        response = re.sub(r'^\[[^\]]+\]\s*', '', response)

    return response


# =============================================================================
# MAIN COMPRESSOR CLASS
# =============================================================================

class MarkdownCompressor:
    """
    High-level markdown compression interface.

    Example:
        compressor = MarkdownCompressor(provider="openai", model="gpt-4o-mini")
        result = compressor.compress("path/to/file.md")
        print(result.compressed)
        print(f"Reduced from {result.original_tokens} to {result.compressed_tokens}")
    """

    def __init__(
        self,
        provider: Literal["openai", "llmengine", "groq", "gemini", "local"] = "llmengine",
        model: str | None = None,
        mode: Literal["normal", "aggressive", "structure"] = "normal",
        api_key: str | None = None,
        chunk_size: int = 6000
    ):
        """
        Initialize the compressor.

        Args:
            provider: LLM provider to use
                - "openai": Use OpenAI API directly (requires OPENAI_API_KEY)
                - "llmengine": Use workspace LLMEngine (Gemini -> Groq -> Ollama)
                - "groq": Alias for llmengine
                - "gemini": Alias for llmengine
                - "local": Force local Ollama via llmengine
            model: Model to use (only for openai provider)
            mode: Compression mode
                - "normal": ~50% compression, balanced
                - "aggressive": ~70% compression, minimal prose
                - "structure": ~30% compression, preserves hierarchy
            api_key: API key override (openai only)
            chunk_size: Max tokens per chunk for large documents
        """
        self.provider = provider
        self.model = model or "gpt-4o-mini"
        self.mode = mode
        self.api_key = api_key
        self.chunk_size = chunk_size

    def compress(self, input_path: str | Path) -> "CompressionResult":
        """
        Compress a markdown file.

        Args:
            input_path: Path to the markdown file

        Returns:
            CompressionResult with compressed text and statistics
        """
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        original = input_path.read_text(encoding="utf-8")
        compressed = self.compress_text(original)

        return CompressionResult(
            original=original,
            compressed=compressed,
            source_file=input_path,
            model=self.model if self.provider == "openai" else "llmengine",
            mode=self.mode
        )

    def compress_text(self, text: str) -> str:
        """
        Compress markdown text directly.

        Args:
            text: Markdown text to compress

        Returns:
            Compressed markdown text
        """
        original_tokens = count_tokens(text, self.model)

        # Check if chunking is needed
        if original_tokens > self.chunk_size:
            chunks = chunk_by_headers(text, self.chunk_size, self.model)
            compressed_chunks = []

            for i, chunk in enumerate(chunks, 1):
                print(f"  Compressing chunk {i}/{len(chunks)}...")
                compressed_chunk = self._compress_single(chunk)
                compressed_chunks.append(compressed_chunk)

            return "\n\n".join(compressed_chunks)
        else:
            return self._compress_single(text)

    def _compress_single(self, text: str) -> str:
        """Compress a single chunk of text."""
        if self.provider == "openai":
            return compress_with_openai(
                text,
                model=self.model,
                mode=self.mode,
                api_key=self.api_key
            )
        elif self.provider == "local":
            return compress_with_llmengine(text, mode=self.mode, force_local=True)
        else:
            # llmengine, groq, gemini all use the same fallback chain
            return compress_with_llmengine(text, mode=self.mode)


class CompressionResult:
    """Result of a compression operation with statistics."""

    def __init__(
        self,
        original: str,
        compressed: str,
        source_file: Path | None = None,
        model: str = "unknown",
        mode: str = "normal"
    ):
        self.original = original
        self.compressed = compressed
        self.source_file = source_file
        self.model = model
        self.mode = mode

        # Calculate statistics
        self.original_tokens = count_tokens(original)
        self.compressed_tokens = count_tokens(compressed)
        self.original_chars = len(original)
        self.compressed_chars = len(compressed)

    @property
    def token_reduction(self) -> float:
        """Percentage of tokens removed."""
        if self.original_tokens == 0:
            return 0.0
        return (1 - self.compressed_tokens / self.original_tokens) * 100

    @property
    def char_reduction(self) -> float:
        """Percentage of characters removed."""
        if self.original_chars == 0:
            return 0.0
        return (1 - self.compressed_chars / self.original_chars) * 100

    def save(self, output_path: str | Path | None = None) -> Path:
        """
        Save compressed output to file.

        Args:
            output_path: Output path (defaults to {original}_compressed.md)

        Returns:
            Path to saved file
        """
        if output_path is None:
            if self.source_file:
                output_path = self.source_file.with_stem(self.source_file.stem + "_compressed")
            else:
                output_path = Path("compressed_output.md")

        output_path = Path(output_path)
        output_path.write_text(self.compressed, encoding="utf-8")
        return output_path

    def stats(self) -> str:
        """Return formatted statistics string."""
        return f"""Compression Statistics:
  Original:   {self.original_tokens:,} tokens / {self.original_chars:,} chars
  Compressed: {self.compressed_tokens:,} tokens / {self.compressed_chars:,} chars
  Reduction:  {self.token_reduction:.1f}% tokens / {self.char_reduction:.1f}% chars
  Model:      {self.model}
  Mode:       {self.mode}"""

    def __repr__(self) -> str:
        return f"<CompressionResult {self.original_tokens}→{self.compressed_tokens} tokens ({self.token_reduction:.1f}% reduction)>"


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Compress markdown files for LLM context windows",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python compressor.py CLAUDE.md
  python compressor.py CLAUDE.md -o CLAUDE_MINI.md
  python compressor.py CLAUDE.md --mode aggressive --provider openai
  python compressor.py CLAUDE.md --provider local  # Use local Ollama
        """
    )

    parser.add_argument("input", help="Input markdown file")
    parser.add_argument("-o", "--output", help="Output file (default: {input}_compressed.md)")
    parser.add_argument(
        "--provider",
        choices=["openai", "llmengine", "groq", "gemini", "local"],
        default="llmengine",
        help="LLM provider (default: llmengine)"
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="Model for OpenAI provider (default: gpt-4o-mini)"
    )
    parser.add_argument(
        "--mode",
        choices=["normal", "aggressive", "structure"],
        default="normal",
        help="Compression mode (default: normal)"
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=6000,
        help="Max tokens per chunk (default: 6000)"
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only show token counts, don't compress"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compress but don't save output"
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        return 1

    # Stats-only mode
    if args.stats_only:
        text = input_path.read_text(encoding="utf-8")
        tokens = count_tokens(text)
        chars = len(text)
        print(f"File: {input_path}")
        print(f"Tokens: {tokens:,}")
        print(f"Characters: {chars:,}")
        return 0

    # Compress
    print(f"Compressing: {input_path}")
    print(f"Provider: {args.provider} | Mode: {args.mode}")

    compressor = MarkdownCompressor(
        provider=args.provider,
        model=args.model,
        mode=args.mode,
        chunk_size=args.chunk_size
    )

    result = compressor.compress(input_path)

    print()
    print(result.stats())

    if not args.dry_run:
        output_path = result.save(args.output)
        print(f"\nSaved to: {output_path}")

    return 0


if __name__ == "__main__":
    exit(main())
