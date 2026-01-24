"""Generate an HTML slideshow from a topic using LLM."""
import sys
sys.path.insert(0, r"C:\python")
from tools.ai_chat.llm_engine import LLMEngine
from pathlib import Path

PROMPT_FILE = Path(__file__).parent / "PROMPT.md"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

def main():
    topic = input("What would you like the slideshow topic to be? ").strip()
    if not topic:
        print("No topic provided. Exiting.")
        return

    llm = LLMEngine()
    print(f"\nGenerating slides for: {topic}...")

    # Step 1: Generate slide content
    slides = llm.chat(f"""Create 5-7 slides for a presentation about: {topic}

Use this exact format:
[SLIDE 1: Title]
- Bullet point
- Another point

[SLIDE 2: Next Title]
- Content here

IMPORTANT: Use plain text only. Do NOT use markdown like **bold** or *italics*.
Include an intro slide, 3-5 content slides, and a conclusion/summary slide.""", temp_history=[])

    print("Slides generated. Creating HTML...")

    # Step 2: Generate HTML using the prompt template
    prompt_template = PROMPT_FILE.read_text(encoding='utf-8')
    html = llm.chat(f"""{prompt_template}

---
## SLIDE CONTENT TO USE:

{slides}

Generate the complete HTML file now. Output ONLY the HTML code, no explanation.""", temp_history=[])

    # Extract HTML from response (handle markdown code blocks)
    if "```html" in html:
        html = html.split("```html")[1].split("```")[0]
    elif "```" in html:
        html = html.split("```")[1].split("```")[0]

    # Remove any LLM header like [model-name]
    if html.strip().startswith("[") and "]" in html[:50]:
        html = html.split("]", 1)[1]

    # Save
    safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)[:40].strip().replace(" ", "_")
    output_file = OUTPUT_DIR / f"{safe_name}.html"
    output_file.write_text(html.strip(), encoding='utf-8')

    print(f"\nSlideshow saved to: {output_file}")

if __name__ == "__main__":
    main()
