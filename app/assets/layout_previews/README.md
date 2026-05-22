# Layout Preview Images

This folder contains custom preview images for the parser layout options in RaceVault.

## How to Add Custom Images

### File Naming Convention
Place your preview images in this directory with these exact filenames:

- **layout_a.png** - For Layout A (standard format)
- **layout_b.png** - For Layout B (extended format)  
- **layout_c.png** - For Provincial M14 format
- **layout_d.png** - For 2KM format
- **auto_detect.png** - For Auto-detect option

### Image Specifications

**Recommended dimensions:** 300×200 pixels or larger
- Images will be scaled to fit the preview panel
- Supports: PNG, JPG, JPEG, GIF, BMP, and other Qt-supported formats

### What to Show in Your Images

Show a **sample page or table** from each layout type so users can visually distinguish between them:

1. **layout_a.png** - Screenshot or mockup of Layout A PDF format
2. **layout_b.png** - Screenshot or mockup of Layout B PDF format
3. **layout_c.png** - Screenshot or mockup of Provincial M14 PDF format
4. **layout_d.png** - Screenshot or mockup of 2KM race results format
5. **auto_detect.png** - A generic image showing the auto-detection concept

### Example Process

1. Take a screenshot of a sample PDF page from each layout
2. Crop/resize to appropriate dimensions (e.g., 400×300 px)
3. Save as PNG with the names above
4. Place in this folder
5. Restart RaceVault - the preview will now show your images!

### Fallback Behavior

If an image file is missing or invalid:
- The system automatically falls back to the colored text-based preview
- No errors will occur - the GUI continues to work normally

### Tips for Better Previews

- **Use actual PDF samples** - Show real examples from your PDFs
- **Highlight key differences** - Make layouts visually distinct
- **Consistent styling** - Use similar backgrounds/framing for all images
- **Include headers/tables** - Show the actual structure of each layout
- **Add annotations** - Optional: add text labels to highlight features

## Current Status

📁 This folder is ready to receive your custom images.
If no custom images are present, colored placeholder previews are shown.
