# PPT Viewer

Generate HTML slideshow presentations from any topic using an LLM.

## Features

- Single-file HTML output (no dependencies except html2canvas CDN)
- Keyboard navigation (arrows, space, Home/End, number keys)
- Touch/swipe support for mobile
- Slide transitions (fade, slide-left, slide-up)
- Progress bar with click-to-jump
- Deep linking via URL hash (#slide-3)
- Fullscreen mode (F key)
- Export slide as PNG
- Responsive design with collapsible sidebar

## Usage

### Quick Start (Python Script)

```bash
python create_slideshow.py
```

Enter a topic when prompted, and the script will:
1. Generate slide content via LLM
2. Inject it into the HTML template
3. Save to `output/<topic>.html`

### OpenWebUI Integration

1. Go to Admin → Functions → Add Function
2. Paste the contents of `openwebui_tool.py`
3. Configure valves (optional):
   - `output_dir`: Where to save HTML files
   - `base_url`: URL prefix for accessing saved files
4. Enable the tool

The tool provides two functions:
- `generate_slideshow(topic)` - Returns instructions for the LLM to create slide JSON
- `render_slideshow(slides_json, title)` - Converts JSON into complete HTML

### Manual (Copy Prompt)

1. Copy the contents of `PROMPT.md` to your LLM
2. Add your topic at the end
3. Paste the returned JSON into `sample_presentation.html` (replace the `slides` array)

## Files

| File | Description |
|------|-------------|
| `PROMPT.md` | LLM prompt for generating slide JSON |
| `create_slideshow.py` | Python script to automate generation |
| `sample_presentation.html` | HTML template with all features |
| `openwebui_tool.py` | OpenWebUI tool integration |
| `sync_template.py` | Sync HTML template changes to OpenWebUI tool |
| `test_openwebui_tool.py` | Test suite for OpenWebUI tool |
| `output/` | Generated slideshows |

## Development

After modifying `sample_presentation.html`, sync changes to the OpenWebUI tool:

```bash
python sync_template.py
python test_openwebui_tool.py  # Verify
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `→` `↓` `Space` `PageDown` | Next slide |
| `←` `↑` `PageUp` | Previous slide |
| `Home` | First slide |
| `End` | Last slide |
| `1-9` | Jump to slide N |
| `F` | Toggle fullscreen |
| `Esc` | Exit fullscreen |
