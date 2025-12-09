# Color System Guide

## Overview

The Discord Soundboard Bot now features a flexible color system that allows you to:
- Create custom button colors with custom names
- Assign RGB/HEX colors to override Bootstrap class styling
- Have fallback to Bootstrap classes when no custom color is set

## How It Works

### Settings Panel

In the Settings tab, you can manage available button colors:

1. **Color Name**: A unique identifier for the color (e.g., "primary", "danger", "my-blue")
2. **Custom Color**: Optional RGB or HEX value (e.g., "rgb(255, 0, 0)" or "#FF0000")
3. **Preview**: Live preview showing how the color will look
4. **Remove**: Delete a color from the available list

### Color Priority

- If a custom RGB/HEX value is set, it will be used for the button background
- If no custom color is set, Bootstrap class styling is used (btn-primary, btn-danger, etc.)
- Text color automatically adjusts based on background luminance for readability

### Example Colors

**Bootstrap Default Colors (no custom RGB needed):**
- primary (blue)
- secondary (gray)
- success (green)
- danger (red)
- warning (yellow)
- info (cyan)
- dark (dark gray)

**Custom Colors (with RGB):**
- "neon-pink": rgb(255, 0, 127)
- "forest-green": #2D5016
- "sky-blue": rgb(135, 206, 250)

## Button Selection

When editing buttons, the color dropdown shows all available colors with previews. Select any color to assign it to the button.

## Migration

All existing configurations have been automatically migrated to the new format:
- Old string format: `"color": "primary"`
- New format: Colors are stored as objects with `name` and `rgb` fields

## Tips

1. **Use meaningful names**: "accent", "highlight", "error" are better than "color1", "color2"
2. **Test contrast**: Ensure text is readable on your chosen background color
3. **Bootstrap fallback**: If you remove the custom RGB value, it reverts to Bootstrap styling
4. **Minimum one color**: You must have at least one color available for buttons
