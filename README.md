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
