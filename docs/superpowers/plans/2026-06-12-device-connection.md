# Device Connection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add detected-device selection and optional IPv4 ADB network connection with automatic refresh and selection.

**Architecture:** Keep the existing device drop-down as the single active-device selector. Add a pure address-normalization helper and a background `adb connect` action in `AdbInstallerApp`; after a successful connection, refresh devices while preferring the normalized network serial.

**Tech Stack:** Python 2/3, Tkinter/ttk, subprocess, threading, unittest

---

### Task 1: Network Address Validation

**Files:**
- Modify: `scripts/main.py`
- Create: `scripts/tests/test_device_connection.py`

- [ ] **Step 1: Write failing normalization tests**

Add tests that import `normalize_network_address` and assert:

```python
self.assertEqual("192.168.1.20:5555", normalize_network_address("192.168.1.20"))
self.assertEqual("192.168.1.20:4444", normalize_network_address("192.168.1.20:4444"))
```

Also assert that empty input, malformed IPv4 octets, extra separators, port `0`, and port `65536` raise `ValueError`.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m unittest scripts.tests.test_device_connection`

Expected: import failure because `normalize_network_address` does not exist.

- [ ] **Step 3: Implement the minimal pure helper**

In `scripts/main.py`, add `normalize_network_address(value)` that trims whitespace, separates an optional port, verifies exactly four numeric IPv4 octets in `0..255`, verifies a numeric port in `1..65535`, defaults to `5555`, and returns `<ip>:<port>`.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `python -m unittest scripts.tests.test_device_connection`

Expected: all address normalization tests pass.

### Task 2: Connection Command And Device Preference

**Files:**
- Modify: `scripts/main.py`
- Modify: `scripts/tests/test_device_connection.py`

- [ ] **Step 1: Write failing connection behavior tests**

Create lightweight fake variables, buttons, roots, and subprocess objects. Assert that:

```python
app.start_connect_thread()
self.assertEqual(["adb", "connect", "192.168.1.20:5555"], popen_calls[0])
self.assertEqual("192.168.1.20:5555", app.preferred_device_serial)
```

Assert that `refresh_data()` selects a detected item ending in `(192.168.1.20:5555)` when `preferred_device_serial` is set, then clears the preference. Assert that merely calling `on_device_selected()` never invokes `adb connect`.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m unittest scripts.tests.test_device_connection`

Expected: failures because the connection action and preferred-device behavior do not exist.

- [ ] **Step 3: Implement background connection behavior**

Add `network_address` and `preferred_device_serial` state. Implement `start_connect_thread()` to validate input, show a warning on `ValueError`, disable the button, execute `adb connect <normalized-address>` without `-s`, collect stdout/stderr, treat return code `0` as success, store the preferred serial, schedule `refresh_data`, log failures, and always restore the button through `root.after`.

Update `refresh_data()` to select a device whose parsed serial equals `preferred_device_serial`; otherwise preserve the prior selection or choose the first device.

- [ ] **Step 4: Run focused and full tests**

Run: `python -m unittest scripts.tests.test_device_connection`

Run: `python -m unittest discover -s scripts/tests -p "test_*.py"`

Expected: all tests pass.

### Task 3: Device Toolbar Controls

**Files:**
- Modify: `scripts/main.py`
- Modify: `scripts/tests/test_device_connection.py`

- [ ] **Step 1: Add a failing UI construction test**

Use fake ttk widgets to verify that application initialization creates an editable network address variable and a connection button whose command is `start_connect_thread`.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m unittest scripts.tests.test_device_connection`

Expected: failure because the IP controls are absent.

- [ ] **Step 3: Add toolbar controls**

Add a compact second toolbar row containing an `IP 地址:` entry and `连接 IP` button. Keep the detected device drop-down, refresh button, and restart button unchanged as the primary device-selection workflow.

- [ ] **Step 4: Run focused and full tests**

Run: `python -m unittest scripts.tests.test_device_connection`

Run: `python -m unittest discover -s scripts/tests -p "test_*.py"`

Expected: all tests pass.

### Task 4: Chinese User Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update usage instructions**

Document that detected USB/network devices are selected from the existing drop-down and all operations target that selection. Document optional IP input, default port `5555`, accepted `IP:port` syntax, and the requirement that the target device already accepts wireless ADB connections.

- [ ] **Step 2: Verify repository state**

Run: `git diff --check`

Run: `python -m unittest discover -s scripts/tests -p "test_*.py"`

Expected: no whitespace errors and all tests pass.

- [ ] **Step 3: Commit implementation**

```bash
git add scripts/main.py scripts/tests/test_device_connection.py README.md docs/superpowers/plans/2026-06-12-device-connection.md
git commit -m "feat: add ADB device connection controls"
```
