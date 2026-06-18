# Export App Design

## Goal

Allow users to select a third-party application installed on the active Android device and export its complete APK set to a chosen local folder.

## User Interface

- Add a dedicated `导出应用` navigation tab.
- Show installed third-party applications in a read-only package-name drop-down.
- Add a read-only target-folder field and a `选择文件夹` button.
- Add an `导出到目标文件夹` action button.
- Refresh the application list when the active device changes or the global refresh action runs.

## Application Discovery

- Query the active device with `adb -s <serial> shell pm list packages -3`.
- Parse only `package:<package-name>` lines.
- Sort and de-duplicate package names before displaying them.
- Preserve the current selection when it remains available after a refresh.
- Clear the list when no usable device is selected or the query fails.

## Export Flow

1. Require an active device, a selected package, and an existing target folder.
2. Query all APK paths with `adb -s <serial> shell pm path <package-name>`.
3. Parse every `package:<device-path>` line, including `base.apk` and split APKs.
4. Create `<target-folder>/<package-name>/` locally.
5. Pull each APK into that package folder while preserving its device-side file name.

The export runs in a background thread. The export button remains disabled until the operation finishes, then is restored on every completion path.

## Validation And Errors

- Show a warning before starting when the device, package, or target folder is missing.
- Treat an empty or malformed `pm path` result as a failed export.
- Log every ADB query and pull operation in the existing log panel.
- Continue pulling remaining APKs if one APK fails, then report the export as partially failed with counts.
- Report missing ADB, process launch errors, directory creation failures, and pull failures without freezing the UI.
- Report the final package directory after a complete success.

## Components

- Keep ADB output parsing in pure helper functions so it can be tested without Tkinter or a connected device.
- Add export-specific state and widgets to `AdbInstallerApp`, following the existing feature-panel pattern.
- Keep UI updates on the Tkinter main thread through `root.after`.
- Use explicit ADB subprocess calls for the multi-step export flow because it needs the output of `pm path` before constructing pull commands.

## Testing

- Test parsing, sorting, and de-duplication of third-party package output.
- Test parsing of base and split APK paths from `pm path` output.
- Test rejection of malformed or empty APK-path output.
- Test that export creates the package directory and pulls every APK using its original file name.
- Test complete success, partial pull failure, missing selection, and button restoration.
- Extend navigation tests to cover the new feature panel.

## Documentation

- Update the Chinese README with application discovery, target-folder selection, complete APK-set export, and output-directory behavior.
