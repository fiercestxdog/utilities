# PowerPoint to HTML Viewer - LLM Prompt

Use this prompt to generate an HTML presentation viewer from slide content.

---

## Prompt

You are a web developer creating a self-contained HTML presentation viewer. Generate a single HTML file that displays slides with navigation controls.

### Input Format

I will provide slide content in this format:

```
[SLIDE 1: Title of Slide]
- Bullet point one
- Bullet point two
  - Sub-bullet
- Bullet point three

[IMAGE: description or URL]

[SLIDE 2: Another Title]
Content for slide 2...
```

**IMPORTANT: Use plain text only. Do NOT use markdown formatting like **bold**, *italics*, or `code`. The HTML generator handles all styling.**

### Required Layout

Create a responsive HTML page with this structure:

```
+------------------+----------------------------------------+
|                  |                                        |
|  AGENDA PANE     |           SLIDE VIEWER                 |
|  (left sidebar)  |           (main area)                  |
|                  |                                        |
|  - Slide 1 *     |    +----------------------------+      |
|  - Slide 2       |    |                            |      |
|  - Slide 3       |    |      Slide Content         |      |
|  - Slide 4       |    |                            |      |
|                  |    +----------------------------+      |
|                  |                                        |
|                  |    [Progress Bar =============>]       |
|                  |                                        |
|                  |    [ < Prev ]  3/10  [ Next > ]        |
|                  |                                        |
+------------------+----------------------------------------+
```

**Agenda Pane (Left Sidebar)**:
- Fixed width (~250px), full height
- Lists all slide titles as clickable links
- Highlights current slide
- Scrollable if many slides
- Collapsible on mobile (hamburger menu)

**Slide Viewer (Main Area)**:
- Displays current slide content centered
- Maintains aspect ratio (16:9 recommended)
- Scales content to fit viewport

**Navigation Controls (Below Slide)**:
- Previous/Next buttons
- Current slide indicator (e.g., "3 of 10")
- Progress bar showing position

### Required Features

#### 1. Keyboard Navigation
```javascript
// Must support:
// - ArrowRight / ArrowDown / Spacebar / PageDown → Next slide
// - ArrowLeft / ArrowUp / PageUp → Previous slide
// - Home → First slide
// - End → Last slide
// - Escape → Exit fullscreen
// - F → Toggle fullscreen
// - Number keys (1-9) → Jump to slide N
```

#### 2. Progress Bar
- Visual indicator below the slide
- Shows current position as filled portion
- Clickable to jump to approximate position

#### 3. Deep Linking
- URL updates with slide number: `file.html#slide-3`
- Loading URL with hash jumps to that slide
- Browser back/forward buttons work correctly

#### 4. Touch/Swipe Support
- Swipe left → Next slide
- Swipe right → Previous slide
- Works on mobile and touch-enabled devices

#### 5. Fullscreen Mode
- Button to enter fullscreen
- Keyboard shortcut (F key)
- Hides agenda pane in fullscreen
- ESC to exit

#### 6. Slide Transitions
- Configurable transition effect between slides
- Support at minimum: `none`, `fade`, `slide-left`, `slide-up`
- Set via config variable at top of script:
```javascript
const CONFIG = {
    transition: 'fade',      // 'none' | 'fade' | 'slide-left' | 'slide-up'
    transitionDuration: 300, // milliseconds
    // ... other config options
};
```

#### 7. Export Slide as Image
- Button to capture current slide as PNG
- Uses html2canvas or similar approach
- Downloads with filename like `slide-3.png`
- Include this library inline or via CDN:
```html
<script src="https://html2canvas.hertzen.com/dist/html2canvas.min.js"></script>
```

### Styling Requirements

**Theme**:
- Clean, modern design
- Dark sidebar (#1a1a2e or similar)
- Light slide background (#ffffff)
- Accent color for highlights and buttons
- Sans-serif fonts (system font stack)

**Responsive Design**:
- Desktop: Sidebar visible, full layout
- Tablet: Collapsible sidebar
- Mobile: Sidebar hidden by default, hamburger toggle

**Slide Styling**:
- Title: Large, bold, accent color
- Body text: Readable size (1.2-1.5rem)
- Bullets: Proper indentation, custom markers
- Images: Centered, max-width contained

### Code Structure

Organize the HTML file with clear sections for maintainability:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Presentation Title</title>
    <style>
        /* =========================
           1. CSS Variables / Theme
           2. Reset & Base Styles
           3. Layout (Sidebar, Main)
           4. Slide Styles
           5. Navigation Controls
           6. Transitions
           7. Responsive / Mobile
           ========================= */
    </style>
</head>
<body>
    <!-- Sidebar / Agenda -->
    <!-- Main Viewer -->
    <!-- Navigation Controls -->

    <script>
        // =========================
        // CONFIG
        // =========================
        const CONFIG = {
            transition: 'fade',
            transitionDuration: 300,
            startSlide: 1
        };

        // =========================
        // SLIDE DATA
        // =========================
        const slides = [
            { title: "...", content: "..." },
            // ...
        ];

        // =========================
        // NAVIGATION LOGIC
        // =========================

        // =========================
        // KEYBOARD HANDLERS
        // =========================

        // =========================
        // TOUCH HANDLERS
        // =========================

        // =========================
        // EXPORT FUNCTIONALITY
        // =========================

        // =========================
        // INITIALIZATION
        // =========================
    </script>
</body>
</html>
```

### Example Output

For this input:
```
[SLIDE 1: Welcome to Our Product]
- Revolutionary new approach
- Built for scale
- Easy to use

[SLIDE 2: Key Features]
- Feature A: Does amazing things
- Feature B: Saves time
- Feature C: Reduces cost
```

Generate a complete HTML file implementing all requirements above.

---

## Usage Notes

1. Copy this prompt to your LLM
2. Append your slide content at the end
3. The LLM will generate a complete HTML file
4. Save as `.html` and open in any browser

## Future Extensibility

This prompt is designed for easy extension. To add features, append to the "Required Features" section:

```markdown
#### 8. [New Feature Name]
- Description of behavior
- Technical requirements
- Example code if helpful
```

Planned future features:
- [ ] Presenter notes (toggleable panel)
- [ ] Thumbnail previews in agenda
- [ ] Dark/light theme toggle
- [ ] Zoom controls
- [ ] Annotation mode
- [ ] Timer display
