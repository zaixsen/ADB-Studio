# Detect Installed Packages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate the uninstall dropdown with all installed packages matching configurable prefixes while retaining configured fallback entries.

**Architecture:** Pure helpers parse ADB output and merge package lists so behavior is testable without a device or Tk. The existing refresh flow queries only the currently selected device and falls back to the text configuration on errors.

**Tech Stack:** Python 2.7/3 standard library, unittest, Tkinter/ttk, ADB package manager.

---

### Task 1: Package Output Helpers

**Files:**
- Modify: `scripts/package_config.py`
- Modify: `scripts/tests/test_package_config.py`

- [x] Add failing tests for parsing multi-prefix-filtered `pm list packages` output.
- [x] Add failing tests for stable deduplicated merging.
- [x] Implement the minimal parser and merge helpers.
- [x] Run the unit tests and verify they pass.

### Task 2: Device Detection Integration

**Files:**
- Modify: `scripts/main.py`
- Modify: `scripts/tests/test_uninstall_action.py`

- [x] Add a device-query method using the selected serial and all configured prefixes.
- [x] Merge detected names with configured names during refresh.
- [x] Preserve configured names and log the error when detection fails.
- [x] Refresh data after a successful uninstall.

### Task 3: Verification

**Files:**
- Verify: `scripts/main.py`
- Verify: `scripts/package_config.py`
- Verify: `scripts/tests/*.py`

- [x] Run all unit tests under Python 2.7.
- [x] Compile all Python files.
- [x] Verify the all-package ADB query and prefix configuration are present.
- [x] If a device is connected, run the read-only package query manually.
