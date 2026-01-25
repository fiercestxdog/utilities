# Work Prompt Generator

A web-based UI for generating and managing work-related prompts using a card interface. Designed for GitHub Pages hosting.

## Features

- **Card-based UI**: Browse prompts organized by theme
- **Search & Filter**: Real-time search across titles, details, and themes
- **Theme Filter**: Dropdown to filter by category
- **Favorites**: Star prompts to pin them to the top (persists in localStorage)
- **Copy to Clipboard**: One-click copy of prompt content
- **Keyboard Shortcuts**: Power-user navigation
- **Modal Navigation**: Browse prompts without closing the modal
- **Responsive Design**: Works on desktop and mobile devices
- **Submit Stub**: Placeholder for custom submission logic

## Quick Start

### GitHub Pages

1. Push all files to your GitHub repository
2. Enable GitHub Pages in repository settings
3. Access at `https://username.github.io/repository-name/prompt-generator.html`

### Local Testing

1. Open `prompt-generator.html` in your web browser
2. Note: Due to CORS, you may need to use a local server:
   ```bash
   python -m http.server 8000
   # Then open http://localhost:8000/prompt-generator.html
   ```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `/` | Focus search box |
| `Esc` | Close modal / unfocus search |
| `C` | Copy prompt (when modal open) |
| `←` | Previous prompt (when modal open) |
| `→` | Next prompt (when modal open) |

## Features Detail

### Search & Filter
- Type in the search box to filter prompts in real-time
- Searches across title, details, and theme
- Use the dropdown to filter by specific theme
- Click the Favorites button to show only starred prompts

### Favorites
- Click the star (★) on any card to favorite it
- Favorited prompts appear at the top of the list
- Favorites persist in browser localStorage
- Toggle "Favorites" button to show only favorites

### Copy to Clipboard
- Click "Copy to Clipboard" in the modal
- Copies title + details formatted for pasting
- Visual feedback confirms successful copy

### Submit (Stub)
- The Submit button is a placeholder for custom logic
- Modify `submitPrompt()` in the HTML to add your integration
- Examples: open external URL, send to API, etc.

## Using the Python Helper Script

The `prompt_manager.py` script lets you manage prompts from the command line.

### List all prompts
```bash
python prompt_manager.py list
```

### Add a new prompt
```bash
python prompt_manager.py add
```
You'll be prompted to enter:
- Theme (e.g., "Leadership", "Strategy", "Productivity")
- Title
- Details (press Enter twice when done)

### Update an existing prompt
```bash
python prompt_manager.py update 0
```
Replace `0` with the index of the prompt you want to update (use `list` to see indices).

### Delete a prompt
```bash
python prompt_manager.py delete 0
```

### Export prompts to text file
```bash
python prompt_manager.py export
```
Creates `prompts_export.txt` with all prompts in readable format.

## File Structure

```
prompt-generator.html  # Main web interface
prompts.json          # Prompt data (editable)
prompt_manager.py     # Python management script
README.md            # This file
```

## Customization

### Editing prompts.json directly

You can also edit `prompts.json` manually. Each prompt has this structure:

```json
{
  "theme": "Category name",
  "title": "Prompt title",
  "details": "Full prompt description with details"
}
```

### Modifying the UI

- **Colors**: Edit the CSS gradient and color values in `prompt-generator.html`
- **Layout**: Adjust `grid-template-columns` in `.cards-grid` for different card sizes
- **Themes**: Add custom theme colors by modifying `.card-theme` and `.modal-theme`

### Implementing Submit

Edit the `submitPrompt()` function in the HTML:

```javascript
function submitPrompt() {
    const prompt = filteredPrompts[currentPromptIndex];

    // Example: Open in ChatGPT
    window.open(`https://chat.openai.com/?q=${encodeURIComponent(prompt.details)}`);

    // Example: Send to API
    fetch('https://your-api.com/submit', {
        method: 'POST',
        body: JSON.stringify(prompt)
    });
}
```

## Requirements

- Modern web browser (Chrome, Firefox, Safari, Edge)
- Python 3.6+ (for the management script, optional)
- No external dependencies required!

## Tips

- Start with 5-10 prompts for best card layout
- Keep titles concise (under 60 characters)
- Use bullet points or numbered lists in details for clarity
- Group related prompts with the same theme for easy filtering
- Use favorites to keep your most-used prompts accessible
