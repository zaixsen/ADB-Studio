# Uninstall Packages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add package-name-based uninstall support using a dedicated text configuration and dropdown.

**Architecture:** Keep text parsing in a small standalone module so it can be tested without creating a Tk window. The existing UI owns selection, refresh, warnings, and dispatch through its existing device-aware ADB command runner.

**Tech Stack:** Python 2.7/3 compatible standard library, Tkinter/ttk, unittest, ADB.

---

### Task 1: Package List Parser

**Files:**
- Create: `scripts/package_config.py`
- Create: `scripts/tests/test_package_config.py`

- [x] Write tests proving blank lines, comments, whitespace, and duplicates are handled.
- [x] Run the tests and verify they fail because the parser module does not exist.
- [x] Implement `load_package_names(path)` with UTF-8-compatible text handling.
- [x] Run the tests and verify they pass under the available Python runtime.

### Task 2: Uninstall UI and Command

**Files:**
- Modify: `scripts/main.py`
- Create: `uninstall_packages.txt`

- [x] Add the root configuration path and selected-package variable.
- [x] Add a read-only dropdown and uninstall button below APK installation.
- [x] Refresh the dropdown from `uninstall_packages.txt` and log missing/empty states.
- [x] Validate selection and dispatch `['uninstall', package_name]` through `run_adb_command`.
- [x] Add example comments to the configuration file.

### Task 3: Verification

**Files:**
- Verify: `scripts/main.py`
- Verify: `scripts/package_config.py`
- Verify: `scripts/tests/test_package_config.py`

- [x] Run parser unit tests.
- [x] Compile all Python files with Python 2.7.
- [x] Load the UI module without starting Tk and verify configuration path resolution.
- [x] Inspect the final root structure and configuration contents.
