"""
Sync HTML template changes into the OpenWebUI tool.

Run this after modifying sample_presentation.html to update openwebui_tool.py.
"""
import re
from pathlib import Path

TOOL_FILE = Path(__file__).parent / "openwebui_tool.py"
TEMPLATE_FILE = Path(__file__).parent / "sample_presentation.html"


def extract_template_from_html(html_content: str) -> str:
    """
    Convert HTML template to a Python f-string for embedding in the tool.

    - Escapes curly braces ({{ and }})
    - Replaces the slides array with {slides_json} placeholder
    - Replaces the title with {title} placeholder
    """
    # Escape all curly braces for f-string
    template = html_content.replace("{", "{{").replace("}", "}}")

    # Find and replace the slides array definition
    # Pattern: const slides = [...]; (multiline)
    slides_pattern = r"const slides = \[.*?\];"

    # Check if pattern exists
    if not re.search(slides_pattern, template, re.DOTALL):
        print("Warning: Could not find 'const slides = [...];' in template")
        print("Looking for alternative patterns...")

        # Try alternate patterns
        alt_patterns = [
            r"const slides = \[[\s\S]*?\];",
            r"let slides = \[[\s\S]*?\];",
        ]
        for alt in alt_patterns:
            if re.search(alt, template, re.DOTALL):
                slides_pattern = alt
                print(f"Found pattern: {alt[:30]}...")
                break

    template = re.sub(
        slides_pattern,
        "const slides = {slides_json};",
        template,
        flags=re.DOTALL
    )

    # Replace title tag content
    template = re.sub(
        r"<title>.*?</title>",
        "<title>{title}</title>",
        template
    )

    return template


def update_tool_file(new_template: str) -> bool:
    """Update the _generate_html method in openwebui_tool.py."""

    tool_content = TOOL_FILE.read_text(encoding='utf-8')

    # Find the _generate_html method and its return string
    # Pattern matches: def _generate_html...return f'''...'''
    method_pattern = r"(def _generate_html\(self, slides: list, title: str\) -> str:\s+slides_json = json\.dumps\(slides, indent=8\)\s+return f''').*?(''')"

    match = re.search(method_pattern, tool_content, re.DOTALL)

    if not match:
        print("Error: Could not find _generate_html method in tool file")
        return False

    # Build the new method content
    new_method = match.group(1) + new_template + match.group(2)

    # Replace in the file
    new_tool_content = re.sub(method_pattern, new_method, tool_content, flags=re.DOTALL)

    TOOL_FILE.write_text(new_tool_content, encoding='utf-8')
    return True


def main():
    print("=" * 60)
    print("Syncing HTML template to OpenWebUI tool")
    print("=" * 60)

    # Check files exist
    if not TEMPLATE_FILE.exists():
        print(f"Error: Template file not found: {TEMPLATE_FILE}")
        return False

    if not TOOL_FILE.exists():
        print(f"Error: Tool file not found: {TOOL_FILE}")
        return False

    print(f"Template: {TEMPLATE_FILE.name}")
    print(f"Tool:     {TOOL_FILE.name}")
    print()

    # Read template
    html_content = TEMPLATE_FILE.read_text(encoding='utf-8')
    print(f"Read template: {len(html_content)} characters")

    # Convert to f-string template
    template = extract_template_from_html(html_content)
    print(f"Converted template: {len(template)} characters")

    # Verify placeholders
    if "{slides_json}" not in template:
        print("Error: {slides_json} placeholder not found after conversion")
        return False

    if "{title}" not in template:
        print("Error: {title} placeholder not found after conversion")
        return False

    print("[OK] Placeholders verified")

    # Update tool file
    if update_tool_file(template):
        print("[OK] Tool file updated successfully")
        print()
        print("=" * 60)
        print("SYNC COMPLETE")
        print("=" * 60)
        print()
        print("Next steps:")
        print("  1. Run test_openwebui_tool.py to verify")
        print("  2. Commit changes to git")
        return True
    else:
        print("Error: Failed to update tool file")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
