# Button Navigation UI Design

## Goal

Reduce interface clutter by showing one operation panel at a time and giving the log area substantially more space.

## Layout

- Use a resizable `760x720` window with a `680x600` minimum size.
- Keep device selection, refresh, and ADB restart controls at the top.
- Add four navigation buttons: Install APK, Uninstall App, Push File, and Pull File.
- Display only the selected operation panel in the middle area.
- Highlight the active navigation button.
- Keep an expanded log panel below the operation area and add a Clear Log button.
- Open the Install APK panel by default.

## Behavior

- Switching panels must preserve entered values and selections.
- Existing ADB operations and configuration behavior remain unchanged.
- Chinese labels and messages are stored correctly as UTF-8 source text.

