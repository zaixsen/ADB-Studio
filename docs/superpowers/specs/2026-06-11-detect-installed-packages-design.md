# Detect Installed Packages Design

## Goal

Show installed packages matching configurable prefixes in the existing uninstall dropdown.

## Behavior

- Read prefixes from root-level `uninstall_package_prefixes.txt`.
- On refresh, query all packages on the selected device with
  `adb -s <serial> shell pm list packages` to avoid excluding matching system packages.
- Parse `package:<name>` lines and keep names beginning with any configured prefix.
- Merge detected names with `uninstall_packages.txt`, preserving order and removing duplicates.
- Continue showing configured names when no device is connected or detection fails.
- Refresh the package list after a successful uninstall command completes.

## Structure

- `uninstall_package_prefixes.txt`: one package prefix per line.
- `scripts/package_config.py`: parse prefixes, device output, and merge package names.
- `scripts/main.py`: execute the device query and update the existing dropdown.
- `scripts/tests/test_package_config.py`: parsing and merge tests.
