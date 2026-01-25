"""Test the OpenWebUI tool functions."""
import sys
sys.path.insert(0, r"C:\python")

from tools.ppt_viewer.openwebui_tool import Tools

def test_generate_slideshow():
    """Test that generate_slideshow returns proper instructions."""
    print("=" * 60)
    print("TEST 1: generate_slideshow()")
    print("=" * 60)

    tool = Tools()
    result = tool.generate_slideshow("Python Programming", num_slides=5)

    print(result[:500])
    print("...")

    assert "JSON" in result
    assert "Python Programming" in result
    assert "5 slides" in result
    print("\n[PASS] generate_slideshow() returns valid instructions\n")

def test_render_slideshow_valid_json():
    """Test rendering with valid JSON input."""
    print("=" * 60)
    print("TEST 2: render_slideshow() with valid JSON")
    print("=" * 60)

    tool = Tools()

    test_json = '''[
        {"title": "Welcome", "content": "<ul><li>Introduction to testing</li><li>Why tests matter</li></ul>"},
        {"title": "Key Concepts", "content": "<ul><li>Unit tests</li><li>Integration tests</li></ul>"},
        {"title": "Summary", "content": "<ul><li>Tests improve quality</li><li>Start testing today</li></ul>"}
    ]'''

    result = tool.render_slideshow(test_json, "Test Presentation")

    # Check HTML structure
    assert "<!DOCTYPE html>" in result
    assert "Test Presentation" in result
    assert "Welcome" in result
    assert "Key Concepts" in result
    assert "const slides =" in result

    print("[PASS] HTML generated successfully")
    print(f"[PASS] Output length: {len(result)} characters\n")

def test_render_slideshow_with_markdown_wrapper():
    """Test that markdown code blocks are stripped."""
    print("=" * 60)
    print("TEST 3: render_slideshow() with ```json wrapper")
    print("=" * 60)

    tool = Tools()

    # Simulate LLM output with markdown code blocks
    test_json = '''Here's the JSON:

```json
[
    {"title": "Slide 1", "content": "<p>Content here</p>"}
]
```

Let me know if you need changes.'''

    result = tool.render_slideshow(test_json, "Wrapped Test")

    assert "<!DOCTYPE html>" in result
    assert "Slide 1" in result
    print("[PASS] Markdown code blocks stripped successfully\n")

def test_render_slideshow_invalid_json():
    """Test error handling for invalid JSON."""
    print("=" * 60)
    print("TEST 4: render_slideshow() with invalid JSON")
    print("=" * 60)

    tool = Tools()

    result = tool.render_slideshow("not valid json {{{", "Bad Input")

    assert "Error parsing" in result
    print(f"[PASS] Error handled gracefully: {result[:60]}...\n")

def test_render_slideshow_empty_array():
    """Test error handling for empty array."""
    print("=" * 60)
    print("TEST 5: render_slideshow() with empty array")
    print("=" * 60)

    tool = Tools()

    result = tool.render_slideshow("[]", "Empty")

    assert "Error" in result
    print(f"[PASS] Empty array handled: {result}\n")

def test_full_html_output():
    """Generate and save a full HTML file for manual inspection."""
    print("=" * 60)
    print("TEST 6: Full HTML output (saved to file)")
    print("=" * 60)

    tool = Tools()
    tool.valves.output_dir = r"C:\python\tools\ppt_viewer\output"

    test_json = '''[
        {"title": "Introduction to Testing", "content": "<ul><li>Why testing matters</li><li>Types of tests</li><li>Best practices</li></ul>"},
        {"title": "Unit Testing", "content": "<ul><li>Test individual functions</li><li>Fast and isolated</li><li>Use assertions</li></ul>"},
        {"title": "Integration Testing", "content": "<ul><li>Test components together</li><li>Verify interfaces</li><li>Database connections</li></ul>"},
        {"title": "Summary", "content": "<ul><li><strong>Start small</strong> with unit tests</li><li><strong>Build up</strong> to integration</li><li><strong>Automate</strong> everything</li></ul>"}
    ]'''

    result = tool.render_slideshow(test_json, "Testing Best Practices")

    print(result[:200])
    print("...\n")

    assert "Slideshow saved" in result or "<!DOCTYPE html>" in result
    print("[PASS] Full HTML generated and saved\n")

def main():
    print("\nOpenWebUI Tool Tests")
    print("=" * 60 + "\n")

    test_generate_slideshow()
    test_render_slideshow_valid_json()
    test_render_slideshow_with_markdown_wrapper()
    test_render_slideshow_invalid_json()
    test_render_slideshow_empty_array()
    test_full_html_output()

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)

if __name__ == "__main__":
    main()
