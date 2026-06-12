# Button Navigation UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stacked operation forms with button-switched panels and enlarge the persistent log area.

**Architecture:** Keep all existing operations in `AdbInstallerApp`. Store operation frames and navigation buttons in dictionaries, with one method responsible for switching visibility and active styling.

**Tech Stack:** Python 2.7/3, Tkinter/ttk, unittest.

---

### Task 1: Navigation Behavior

**Files:**
- Create: `scripts/tests/test_ui_navigation.py`
- Modify: `scripts/main.py`

- [x] Add a failing test proving only the selected operation panel is packed.
- [x] Add a failing test proving the selected navigation button is highlighted.
- [x] Implement `show_feature(feature_name)`.
- [x] Run tests and verify the navigation behavior passes.

### Task 2: Interface Layout

**Files:**
- Modify: `scripts/main.py`

- [x] Build the fixed device toolbar.
- [x] Build four navigation buttons and four operation panels.
- [x] Show Install APK by default.
- [x] Expand the log panel and add Clear Log.
- [x] Correct all visible Chinese labels and messages.

### Task 3: Verification

**Files:**
- Verify: `scripts/main.py`
- Verify: `scripts/tests/*.py`

- [x] Run all unit tests using Python 2.7.
- [x] Compile all Python source files.
- [x] Instantiate the Tk interface when a desktop display is available.
- [x] Confirm the existing ADB package detection remains covered.
