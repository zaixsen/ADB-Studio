# Uninstall Package List Design

## Goal

Add an application uninstall area driven by a dedicated root-level
`uninstall_packages.txt` file.

## Behavior

- Read one Android package name per line.
- Ignore blank lines and lines whose first non-whitespace character is `#`.
- Remove surrounding whitespace and duplicate package names while preserving order.
- Populate a read-only package dropdown whenever the application refreshes.
- Run `adb -s <device> uninstall <package>` for the selected package.
- Show a warning when no package is selected.
- Log a clear message when the configuration file is missing or empty.

## Files

- `uninstall_packages.txt`: user-editable uninstall-only package list.
- `scripts/package_config.py`: configuration parsing isolated from the UI.
- `scripts/main.py`: dropdown, uninstall button, refresh integration, and command call.
- `scripts/tests/test_package_config.py`: parser tests compatible with Python 2.7.

