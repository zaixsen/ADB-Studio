# Device Connection Design

## Goal

Allow users to select an already detected ADB device for normal operations and optionally connect to an Android device over the network by entering its IP address.

## User Interface

- Keep the existing detected-device drop-down as the active device selector.
- Add a network address input near the device controls.
- Add a `连接 IP` button next to the input.
- Accept either an IPv4 address such as `192.168.1.100` or an address with a port such as `192.168.1.100:5555`.
- When the port is omitted, use port `5555`.

## Behavior

### Detected Devices

- Devices returned by `adb devices` remain available in the existing drop-down.
- Selecting one changes the serial passed to later commands through `adb -s <serial>`.
- Selecting an existing USB or network device does not execute `adb connect`.

### IP Connection

- Validate and normalize the entered network address before starting a command.
- Execute `adb connect <address>` without a device selector.
- Run the connection command in a background thread so the UI remains responsive.
- Disable the connection button while the command is running.
- Write the command output and errors to the existing log panel.
- On success, refresh the detected-device list and select the connected network address when it appears.

## Validation And Errors

- Reject an empty address.
- Accept IPv4 addresses with an optional port from `1` through `65535`.
- Reject malformed addresses and invalid ports before invoking ADB.
- Show a warning for invalid user input.
- Report missing ADB, process errors, and unsuccessful connection output in the log.
- Restore the connection button after every completion path.

## Testing

- Test normalization of an IP without a port to port `5555`.
- Test preservation of an explicitly supplied valid port.
- Test rejection of malformed IP addresses and invalid ports.
- Test that an existing detected-device selection does not call `adb connect`.
- Test that an IP connection invokes `adb connect <normalized-address>` and schedules a device refresh.

## Documentation

- Update the Chinese README with detected-device selection and optional IP connection instructions.
