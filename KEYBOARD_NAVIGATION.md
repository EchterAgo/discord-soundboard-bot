# Keyboard Navigation Guide

## Overview
The Discord Soundboard web interface now features comprehensive keyboard navigation, making it fully usable without a mouse.

## Global Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl + F` | Focus search box |
| `?` | Toggle help panel |
| `S` | Toggle settings panel |
| `1` | Switch to Custom Buttons view |
| `2` | Switch to Recent Sounds view |
| `3` | Switch to All Sounds view |
| `Escape` | Close modals, panels, and dropdowns |

## Navigation

### Tab Navigation
- Press `Tab` to move forward through interactive elements
- Press `Shift + Tab` to move backward
- All buttons, inputs, and controls are keyboard accessible
- Clear visual focus indicators show your current position

### Button Grid Navigation
When focused on any sound button:
- `Arrow Right` - Move to next button
- `Arrow Left` - Move to previous button  
- `Arrow Down` - Move down one row
- `Arrow Up` - Move up one row
- `Home` - Jump to first button
- `End` - Jump to last button
- `Enter` or `Space` - Play the focused sound

### Search Box Navigation
- Type to search and filter sounds
- `Arrow Down` - Navigate down through search results
- `Arrow Up` - Navigate up through search results
- `Enter` - Play selected sound (or top result if none selected)
- `Escape` - Close search dropdown

## Play Mode Modifiers

You can override the current play mode using modifier keys:
- `Ctrl + Click/Enter` - Play in Instant mode (interrupts current playback)
- `Shift + Click/Enter` - Play in Queue mode (adds to end of queue)
- `Ctrl + Shift + Click/Enter` - Play in Play Next mode

## Modal Dialog Navigation

When editing buttons:
- `Tab` / `Shift + Tab` - Navigate through form fields
- Focus is trapped within the modal for better accessibility
- `Escape` - Cancel and close modal
- First focusable element is automatically focused when modal opens

### Button Editor
- Navigate through label, sound, and color fields
- Use arrow keys in sound dropdown to select sounds
- `Enter` to select a sound from the dropdown
- Color buttons can be activated with `Enter` or `Space`

## Accessibility Features

### Visual Focus Indicators
- High-contrast focus outlines (3px blue border)
- Glow effect on focused elements
- Selected dropdown items highlighted in blue
- Buttons slightly elevated when focused

### ARIA Attributes
- All interactive elements have proper `aria-label` attributes
- Buttons include `aria-pressed` states
- Modal has `role="dialog"` and `aria-modal="true"`
- View toggle buttons have `aria-pressed` state

### Focus Management
- Modal focus trap prevents tabbing outside dialog
- Focus returns to logical elements after actions
- First element auto-focused when modals/dropdowns open
- Proper tabindex on all interactive elements

## Tips for Keyboard Users

1. **Quick Sound Search**: Press `Ctrl + F` to immediately start searching
2. **Rapid Navigation**: Use number keys (1, 2, 3) to quickly switch between views
3. **Grid Navigation**: Arrow keys work naturally - navigate just like moving a cursor
4. **Play Mode Toggle**: Header button is keyboard accessible to change modes
5. **Edit Mode**: All editing functions work with keyboard only
6. **Settings Access**: Press `S` from anywhere to access settings

## Screen Reader Support

The interface includes:
- Descriptive labels for all controls
- ARIA landmarks and roles
- Semantic HTML structure
- Focus management for dynamic content
- Status updates for queue changes

## Browser Compatibility

Full keyboard navigation works in:
- Chrome/Edge (Chromium)
- Firefox
- Safari
- All modern browsers with JavaScript enabled

Note: Some visual focus indicators use `:focus-visible` which shows focus only for keyboard navigation, not mouse clicks.
