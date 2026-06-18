# Export App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Tkinter workflow that exports every APK belonging to a selected third-party Android package into a user-selected local folder.

**Architecture:** Add pure ADB-output parsers to the existing package helper module, then add an export panel and a background multi-command workflow to `AdbInstallerApp`. Keep subprocess work off the Tk thread and route widget updates back through `root.after`.

**Tech Stack:** Python 2.7/3 standard library, Tkinter/ttk, unittest, ADB package manager and pull commands.

---

### Task 1: Parse Application And APK Path Output

**Files:**
- Modify: `scripts/package_config.py`
- Modify: `scripts/tests/test_package_config.py`

- [ ] **Step 1: Write failing parser tests**

Add tests that pass byte output containing duplicates, whitespace, unrelated lines, `base.apk`, and split APKs. Assert that `parse_adb_packages` returns sorted unique package names and `parse_adb_apk_paths` returns device paths in ADB order while removing duplicates.

```python
self.assertEqual(
    ["com.alpha", "com.zeta"],
    parse_adb_packages(b"package:com.zeta\nnoise\npackage:com.alpha\npackage:com.zeta\n")
)
self.assertEqual(
    ["/data/app/pkg/base.apk", "/data/app/pkg/split_config.en.apk"],
    parse_adb_apk_paths(
        b"package:/data/app/pkg/base.apk\n"
        b"package:/data/app/pkg/split_config.en.apk\n"
    )
)
```

- [ ] **Step 2: Verify the tests fail for missing imports**

Run: `python -m unittest scripts.tests.test_package_config`

Expected: failure because the two parser functions do not exist.

- [ ] **Step 3: Implement the parsers**

Decode through a small local text helper, accept only non-empty `package:` values, de-duplicate values, sort package names, and preserve APK path order.

```python
def parse_adb_packages(output):
    values = _parse_package_values(output)
    return sorted(set(values))


def parse_adb_apk_paths(output):
    paths = []
    for value in _parse_package_values(output):
        if value.endswith(".apk") and value not in paths:
            paths.append(value)
    return paths
```

- [ ] **Step 4: Verify parser tests pass**

Run: `python -m unittest scripts.tests.test_package_config`

Expected: all package helper tests pass.

### Task 2: Implement The Background Export Workflow

**Files:**
- Modify: `scripts/main.py`
- Create: `scripts/tests/test_export_app.py`

- [ ] **Step 1: Write failing export workflow tests**

Create small `ValueHolder`, `FakeButton`, and `ImmediateRoot` test doubles. Patch `subprocess.Popen`, `os.path.isdir`, and `os.makedirs`; assert that `start_export_thread` queries `pm path`, creates `<target>/<package>`, pulls every returned APK to an explicit destination file, reports partial failure, and restores the button.

```python
expected = [
    ["adb", "-s", "device-123", "shell", "pm", "path", "com.example.app"],
    ["adb", "-s", "device-123", "pull", "/data/app/pkg/base.apk",
     os.path.join(target, "com.example.app", "base.apk")],
    ["adb", "-s", "device-123", "pull", "/data/app/pkg/split_config.en.apk",
     os.path.join(target, "com.example.app", "split_config.en.apk")],
]
self.assertEqual(expected, commands)
self.assertEqual("normal", app.export_btn.state)
```

- [ ] **Step 2: Verify the workflow tests fail**

Run: `python -m unittest scripts.tests.test_export_app`

Expected: failure because export state and methods do not exist.

- [ ] **Step 3: Implement validation and export execution**

Add `selected_export_package`, `export_target_dir`, and `export_btn`. Validate device/package/directory before spawning a daemon thread. In the worker, run `pm path`, parse it with `parse_adb_apk_paths`, create the package directory, run one explicit `adb pull <remote> <local-file>` command per APK, count failures, log the final result, and restore the button with `root.after`.

```python
def start_export_thread(self):
    device = self.get_selected_serial()
    package_name = self.selected_export_package.get().strip()
    target_dir = self.export_target_dir.get().strip()
    if not device or not package_name or not os.path.isdir(target_dir):
        messagebox.showwarning("提示", "请选择设备、应用和有效的目标文件夹。")
        return
    self.export_btn.config(state="disabled")
    thread = threading.Thread(
        target=lambda: self._export_app(device, package_name, target_dir))
    thread.daemon = True
    thread.start()
```

- [ ] **Step 4: Verify workflow tests pass**

Run: `python -m unittest scripts.tests.test_export_app`

Expected: complete success and partial-failure tests pass.

### Task 3: Integrate The Export Panel And Refresh Flow

**Files:**
- Modify: `scripts/main.py`
- Modify: `scripts/tests/test_ui_navigation.py`
- Modify: `README.md`

- [ ] **Step 1: Add failing UI integration tests**

Assert that navigation can activate an `export` panel and that `refresh_export_packages` preserves an existing selection, chooses the first new value, and clears stale state when no device packages are returned.

```python
app.feature_panels = {"install": FakePanel(), "export": FakePanel()}
app.feature_buttons = {"install": FakeButton(), "export": FakeButton()}
main.AdbInstallerApp.show_feature.im_func(app, "export")
self.assertTrue(app.feature_buttons["export"].active)
```

- [ ] **Step 2: Verify UI integration tests fail**

Run: `python -m unittest scripts.tests.test_ui_navigation scripts.tests.test_export_app`

Expected: failure because the export panel and refresh method are not wired in.

- [ ] **Step 3: Add panel, discovery, folder selection, and refresh wiring**

Add an `导出应用` navigation item and a panel with a read-only package combobox, read-only target entry, folder picker, and action button. Query packages with `adb -s <serial> shell pm list packages -3`, parse using `parse_adb_packages`, and call `refresh_export_packages` after device/global refresh.

```python
output = subprocess.check_output(
    ["adb", "-s", device, "shell", "pm", "list", "packages", "-3"],
    startupinfo=self.create_startupinfo())
packages = parse_adb_packages(output)
```

- [ ] **Step 4: Document the workflow**

Add README bullets and usage instructions stating that all base/split APKs are written to `<target>/<package-name>/` and that only third-party packages are listed.

- [ ] **Step 5: Run the complete test suite and syntax check**

Run: `python -m unittest discover -s scripts/tests -p "test_*.py"`

Run: `python -m py_compile scripts/main.py scripts/package_config.py`

Expected: all tests pass and both modules compile without errors.
