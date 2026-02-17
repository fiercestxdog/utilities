# Utilities

A collection of useful tools and prompts.

## Tools

### [ppt_viewer](./ppt_viewer/)

Generate HTML slideshow presentations from any topic using an LLM. Features keyboard navigation, touch support, transitions, fullscreen mode, and PNG export.

```bash
cd ppt_viewer
python create_slideshow.py
```

### [PromptGenerator](./PromptGenerator/)

Work prompt management with a card-based web UI. Features search, filtering, favorites, copy to clipboard, and keyboard shortcuts. Designed for GitHub Pages hosting.

**[Live Demo](https://fiercestxdog.github.io/utilities/PromptGenerator/prompt-generator.html)** (once GitHub Pages is enabled)

```bash
cd PromptGenerator
python -m http.server 8000
# Open http://localhost:8000/prompt-generator.html
```

### [flashcard_app](./flashcard_app/)

Flashcard study app with spaced repetition (SM-2), four study modes, and a glassmorphism neon theme. Upload any CSV (question,answer per line) to start studying. Features LaTeX math rendering via KaTeX and inline code formatting.

**Study Modes**: Classic Flip, Quiz (type answer with keyword matching), Match Game (timed pair matching), Speed Round (timed know-it/don't-know-it)

**[Live Demo](https://fiercestxdog.github.io/utilities/flashcard_app/)** | Includes a sample `flashcards.csv` deck
