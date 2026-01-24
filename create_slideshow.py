"""Generate an HTML slideshow from a topic using LLM."""
import sys
import re
import json
sys.path.insert(0, r"C:\python")
from tools.ai_chat.llm_engine import LLMEngine
from pathlib import Path

PROMPT_FILE = Path(__file__).parent / "PROMPT.md"
TEMPLATE_FILE = Path(__file__).parent / "sample_presentation.html"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

def main():
    if not TEMPLATE_FILE.exists():
        print(f"Error: Template file not found at {TEMPLATE_FILE}")
        return

    topic = input("What would you like the slideshow topic to be? ").strip()
    if not topic:
        print("No topic provided. Exiting.")
        return

    llm = LLMEngine()
    print(f"\nGenerating slide content for: {topic}...")

    # Load the system prompt
    system_prompt = PROMPT_FILE.read_text(encoding='utf-8')

    # Generate JSON content
    response = llm.chat(f"""{system_prompt}

TOPIC: {topic}
""", temp_history=[])

    # Clean response (remove markdown code blocks if present)
    json_str = response.strip()
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0]
    elif "```" in json_str:
        json_str = json_str.split("```")[1].split("```")[0]
    
    json_str = json_str.strip()

    # Validate JSON
    try:
        slide_data = json.loads(json_str)
        print(f"Successfully generated {len(slide_data)} slides.")
    except json.JSONDecodeError as e:
        print(f"Error parsing LLM response as JSON: {e}")
        print("Raw response preview:", json_str[:500])
        return

    # Read Template
    template_content = TEMPLATE_FILE.read_text(encoding='utf-8')

    # Inject JSON into template using Regex
    # Matches: const slides = [ ... ]; (dotall to match newlines)
    # We use a specific lookahead/behind or just replace the variable assignment
    pattern = r"const\s+slides\s*=\s*\[.*?\];"
    replacement = f"const slides = {json.dumps(slide_data, indent=4)};"
    
    new_html = re.sub(pattern, replacement, template_content, flags=re.DOTALL)

    # Save
    safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)[:40].strip().replace(" ", "_")
    output_file = OUTPUT_DIR / f"{safe_name}.html"
    output_file.write_text(new_html, encoding='utf-8')

    print(f"\nSlideshow saved to: {output_file}")

if __name__ == "__main__":
    main()
