# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import datetime
import glob
import os
import re
import shutil
import subprocess
import sys
import threading
import tempfile
import zipfile

from package_config import (
    extract_apk_label,
    load_package_names,
    merge_package_names,
    parse_adb_apk_paths,
    parse_adb_package_list,
    parse_adb_package_labels,
    parse_adb_packages,
    save_package_names,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
APK_DIR = os.path.join(PROJECT_DIR, "apk")
PULL_DIR = os.path.join(PROJECT_DIR, "ReadByPhone")
UNINSTALL_PACKAGES_FILE = os.path.join(PROJECT_DIR, "uninstall_packages.txt")
UNINSTALL_PREFIXES_FILE = os.path.join(PROJECT_DIR, "uninstall_package_prefixes.txt")

# ── Design System ─────────────────────────────────────────────────────────────
C_WIN        = "#0D1117"
C_SURFACE    = "#161B22"
C_SURFACE2   = "#21262D"
C_HEADER_BG  = "#010409"

C_ACCENT     = "#58A6FF"
C_ACCENT_LT  = "#79C0FF"

C_TEXT       = "#E6EDF3"
C_TEXT_DIM   = "#8B949E"
C_TEXT_MUTED = "#3D444D"

C_BORDER     = "#30363D"

C_OK         = "#3FB950"
C_ERR        = "#F85149"

C_LOG_BG     = "#010409"
C_LOG_FG     = "#C9D1D9"
C_LOG_TIME   = "#6E7681"
C_LOG_CMD    = "#79C0FF"
C_LOG_OK     = "#56D364"
C_LOG_ERR    = "#F85149"

F_UI         = ("Segoe UI", 9)
F_UI_BOLD    = ("Segoe UI", 9, "bold")
F_TITLE      = ("Segoe UI", 15, "bold")
F_MONO       = ("Consolas", 9)

try:
    text_type = unicode
except NameError:
    text_type = str

if sys.version_info[0] < 3:
    import Tkinter as tk
    import ttk
    import tkMessageBox as messagebox
    import ScrolledText as scrolledtext
    import tkFileDialog as filedialog
else:
    import tkinter as tk
    from tkinter import ttk, messagebox, scrolledtext, filedialog


def to_text(value):
    if isinstance(value, text_type):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return text_type(value)


def normalize_network_address(value):
    address = to_text(value).strip()
    if not address:
        raise ValueError("IP 地址不能为空。")
    parts = address.split(":")
    if len(parts) > 2:
        raise ValueError("IP 地址格式无效。")
    ip_address = parts[0]
    port_text = parts[1] if len(parts) == 2 else "5555"
    octets = ip_address.split(".")
    if len(octets) != 4 or any(
            not octet.isdigit() or not 0 <= int(octet) <= 255
            for octet in octets):
        raise ValueError("IP 地址格式无效。")
    if not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
        raise ValueError("端口必须是 1 到 65535 之间的数字。")
    return "{}:{}".format(ip_address, port_text)


def serial_from_device_label(selection):
    match = re.search(r"\(([^)]+)\)$", selection)
    return match.group(1) if match else selection


def _is_install_package(path):
    lower = path.lower()
    return lower.endswith(".apk") or lower.endswith(".xapk")


def _xapk_sort_key(path):
    name = os.path.basename(path).lower()
    return (0 if name == "base.apk" else 1, name)


def build_xapk_install_args(xapk_path, extract_dir):
    try:
        archive = zipfile.ZipFile(xapk_path, "r")
    except Exception as error:
        raise ValueError("Invalid or unreadable XAPK file: " + to_text(error))

    extracted = []
    try:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            if name.endswith("/") or not name.lower().endswith(".apk"):
                continue
            dest_name = os.path.basename(name)
            if not dest_name:
                continue

            dest_path = os.path.join(extract_dir, dest_name)
            base, ext = os.path.splitext(dest_name)
            index = 1
            while os.path.exists(dest_path):
                dest_path = os.path.join(extract_dir, "{}_{}{}".format(base, index, ext))
                index += 1

            source = archive.open(info, "r")
            try:
                target = open(dest_path, "wb")
                try:
                    shutil.copyfileobj(source, target)
                finally:
                    target.close()
            finally:
                source.close()
            extracted.append(dest_path)
    except Exception as error:
        raise ValueError("Failed to extract XAPK: " + to_text(error))
    finally:
        archive.close()

    if not extracted:
        raise ValueError("No APK split files found inside XAPK.")

    return ["install-multiple", "-r"] + sorted(extracted, key=_xapk_sort_key)


class TabButton(tk.Frame):
    """VS Code-style navigation tab with accent underline indicator."""

    IND_H = 2

    def __init__(self, parent, text, command, **kwargs):
        tk.Frame.__init__(self, parent, bg=C_WIN, cursor="hand2", **kwargs)
        self._command = command
        self._active = False
        self._hovering = False

        self._label = tk.Label(
            self, text=text,
            font=F_UI, bg=C_WIN, fg=C_TEXT_DIM,
            padx=14, pady=9, cursor="hand2"
        )
        self._label.pack(fill=tk.X)

        self._bar = tk.Frame(self, bg=C_WIN, height=self.IND_H)
        self._bar.pack(fill=tk.X)

        for w in (self, self._label, self._bar):
            w.bind("<Button-1>", lambda e: self._command())
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)

    def _on_enter(self, e=None):
        self._hovering = True
        self._refresh()

    def _on_leave(self, e=None):
        self._hovering = False
        self._refresh()

    def _refresh(self):
        if self._active:
            self._label.config(fg=C_TEXT, font=F_UI_BOLD, bg=C_WIN)
            self._bar.config(bg=C_ACCENT)
            self.config(bg=C_WIN)
        elif self._hovering:
            self._label.config(fg=C_TEXT, font=F_UI, bg=C_SURFACE2)
            self._bar.config(bg=C_WIN)
            self.config(bg=C_SURFACE2)
        else:
            self._label.config(fg=C_TEXT_DIM, font=F_UI, bg=C_WIN)
            self._bar.config(bg=C_WIN)
            self.config(bg=C_WIN)

    def set_active(self, active):
        self._active = active
        self._refresh()


class AdbInstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ADB Device Tools")
        self.root.geometry("860x720")
        self.root.minsize(720, 580)
        self.root.configure(bg=C_WIN)

        self.selected_device = tk.StringVar()
        self.selected_apk = tk.StringVar()
        self.selected_uninstall_package = tk.StringVar()
        self.selected_export_package = tk.StringVar()
        self.export_target_dir = tk.StringVar()
        self.network_address = tk.StringVar()
        self.push_local_path = tk.StringVar()
        self.push_remote_path = tk.StringVar(value="/sdcard/Download/")
        self.pull_remote_path = tk.StringVar(value="/sdcard/Download/")
        self.preferred_device_serial = None

        self._package_labels = {}
        self._package_display_map = {}
        self.feature_panels = {}
        self.feature_buttons = {}

        self.configure_styles()
        self.create_widgets()
        self.show_feature("install")
        self.refresh_data()

    def configure_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".",
                       background=C_WIN, foreground=C_TEXT,
                       fieldbackground=C_SURFACE2, bordercolor=C_BORDER,
                       darkcolor=C_BORDER, lightcolor=C_BORDER,
                       troughcolor=C_SURFACE2, relief="flat", borderwidth=1)

        style.configure("TFrame", background=C_WIN)
        style.configure("TLabel", background=C_WIN, foreground=C_TEXT)

        style.configure("TButton",
                       background=C_SURFACE2, foreground=C_TEXT_DIM,
                       borderwidth=1, relief="flat", padding=(8, 4))
        style.map("TButton",
                  background=[("active", "#2D333B"), ("pressed", C_BORDER)],
                  foreground=[("active", C_TEXT)])

        style.configure("Action.TButton",
                       background=C_ACCENT, foreground="#ffffff",
                       borderwidth=0, relief="flat",
                       padding=(16, 8), font=F_UI_BOLD)
        style.map("Action.TButton",
                  background=[("active", C_ACCENT_LT), ("disabled", C_BORDER)],
                  foreground=[("disabled", C_TEXT_MUTED)])

        style.configure("TEntry",
                       fieldbackground=C_SURFACE2, foreground=C_TEXT,
                       bordercolor=C_BORDER, insertcolor=C_TEXT,
                       padding=(6, 4), relief="flat")
        style.map("TEntry", bordercolor=[("focus", C_ACCENT)])

        style.configure("TCombobox",
                       fieldbackground=C_SURFACE2, foreground=C_TEXT,
                       background=C_SURFACE2, bordercolor=C_BORDER,
                       arrowcolor=C_TEXT_DIM, relief="flat", padding=(4, 4))
        style.map("TCombobox",
                  fieldbackground=[("readonly", C_SURFACE2)],
                  foreground=[("readonly", C_TEXT)])

        style.configure("TScrollbar",
                       background=C_SURFACE2, troughcolor=C_WIN,
                       bordercolor=C_WIN, arrowcolor=C_TEXT_MUTED,
                       width=8, arrowsize=8)
        style.map("TScrollbar", background=[("active", C_BORDER)])

        style.configure("Card.TLabelframe",
                       background=C_SURFACE, bordercolor=C_BORDER,
                       borderwidth=1, relief="solid")
        style.configure("Card.TLabelframe.Label",
                       background=C_SURFACE, foreground=C_TEXT_DIM,
                       font=F_UI_BOLD)

    def create_widgets(self):
        # ── Header ─────────────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg=C_HEADER_BG, height=80)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        icon_canvas = tk.Canvas(header, width=80, height=80,
                               bg=C_HEADER_BG, highlightthickness=0)
        icon_canvas.pack(side=tk.LEFT, padx=(20, 0))
        self.root.after(20, lambda: self._draw_android(icon_canvas))

        title_frame = tk.Frame(header, bg=C_HEADER_BG)
        title_frame.pack(side=tk.LEFT, fill=tk.Y, pady=18, padx=(8, 0))
        tk.Label(title_frame, text="ADB Device Tools",
                font=F_TITLE, bg=C_HEADER_BG, fg=C_TEXT).pack(anchor=tk.W)
        tk.Label(title_frame, text="在线设备管理与文件操作",
                font=("Segoe UI", 9), bg=C_HEADER_BG, fg=C_TEXT_DIM).pack(anchor=tk.W, pady=(3, 0))

        tk.Frame(self.root, bg=C_ACCENT, height=1).pack(fill=tk.X)

        # ── Toolbar ────────────────────────────────────────────────────────────
        tb = tk.Frame(self.root, bg=C_SURFACE, padx=14, pady=8)
        tb.pack(fill=tk.X)

        tk.Label(tb, text="设备", font=F_UI, bg=C_SURFACE, fg=C_TEXT_DIM).pack(side=tk.LEFT)
        self.device_combo = ttk.Combobox(tb, textvariable=self.selected_device,
                                        state="readonly", width=26)
        self.device_combo.pack(side=tk.LEFT, padx=(6, 8))
        self.device_combo.bind("<<ComboboxSelected>>", self.on_device_selected)

        ttk.Button(tb, text="刷新", command=self.refresh_data).pack(side=tk.LEFT, padx=(0, 4))
        self.restart_btn = ttk.Button(tb, text="重启 ADB", command=self.restart_adb)
        self.restart_btn.pack(side=tk.LEFT, padx=(0, 14))

        tk.Frame(tb, bg=C_BORDER, width=1, height=22).pack(side=tk.LEFT, pady=1, padx=(0, 12))

        tk.Label(tb, text="IP", font=F_UI, bg=C_SURFACE, fg=C_TEXT_DIM).pack(side=tk.LEFT)
        ttk.Entry(tb, textvariable=self.network_address, width=18).pack(side=tk.LEFT, padx=(6, 6))
        self.connect_btn = ttk.Button(tb, text="连接", command=self.start_connect_thread)
        self.connect_btn.pack(side=tk.LEFT)

        tk.Frame(self.root, bg=C_BORDER, height=1).pack(fill=tk.X)

        # ── Nav tabs ───────────────────────────────────────────────────────────
        nav = tk.Frame(self.root, bg=C_WIN)
        nav.pack(fill=tk.X, padx=14)

        for key, label in [
            ("install",   "安装 APK/XAPK"),
            ("uninstall", "卸载应用"),
            ("export",    "导出应用"),
            ("push",      "推送文件"),
            ("pull",      "拉取文件"),
            ("terminal",  "ADB 终端"),
            ("config",    "配置"),
        ]:
            btn = TabButton(nav, text=label, command=lambda k=key: self.show_feature(k))
            btn.pack(side=tk.LEFT)
            self.feature_buttons[key] = btn

        tk.Frame(self.root, bg=C_BORDER, height=1).pack(fill=tk.X)

        # ── Feature host ───────────────────────────────────────────────────────
        self.feature_host = tk.Frame(self.root, bg=C_WIN, height=200)
        self.feature_host.pack(fill=tk.X, padx=14, pady=(8, 4))
        self.feature_host.pack_propagate(False)

        self.create_install_panel()
        self.create_uninstall_panel()
        self.create_export_panel()
        self.create_push_panel()
        self.create_pull_panel()
        self.create_terminal_panel()
        self.create_config_panel()

        # ── Log area ───────────────────────────────────────────────────────────
        log_outer = tk.Frame(self.root, bg=C_WIN, padx=14, pady=2)
        log_outer.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        log_hdr = tk.Frame(log_outer, bg=C_WIN, pady=4)
        log_hdr.pack(fill=tk.X)
        tk.Label(log_hdr, text="运行日志",
                font=F_UI_BOLD, bg=C_WIN, fg=C_TEXT_DIM).pack(side=tk.LEFT)
        ttk.Button(log_hdr, text="清空", command=self.clear_log).pack(side=tk.RIGHT)

        log_border = tk.Frame(log_outer, bg=C_BORDER, padx=1, pady=1)
        log_border.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(
            log_border,
            state="disabled",
            font=F_MONO,
            wrap=tk.WORD,
            bg=C_LOG_BG, fg=C_LOG_FG,
            insertbackground=C_LOG_FG,
            relief=tk.FLAT, borderwidth=0,
            selectbackground="#264F78",
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.tag_configure("time", foreground=C_LOG_TIME)
        self.log_text.tag_configure("cmd",  foreground=C_LOG_CMD)
        self.log_text.tag_configure("ok",   foreground=C_LOG_OK)
        self.log_text.tag_configure("err",  foreground=C_LOG_ERR)

    def _draw_android(self, canvas):
        """Draw Android robot head icon in the header."""
        cx, cy = 40, 50
        rx, ry = 21, 16

        # Atmospheric glow behind dome
        canvas.create_arc(cx - rx - 6, cy - ry - 6, cx + rx + 6, cy + ry + 6,
                         start=0, extent=180, style=tk.CHORD,
                         fill="#0b1e36", outline="")

        # Head dome (upper half of ellipse)
        canvas.create_arc(cx - rx, cy - ry, cx + rx, cy + ry,
                         start=0, extent=180, style=tk.CHORD,
                         fill=C_ACCENT, outline="")

        # Eyes (punched out with header bg color)
        canvas.create_oval(cx - 13, cy - 9, cx - 5, cy - 1,
                          fill=C_HEADER_BG, outline="")
        canvas.create_oval(cx + 5, cy - 9, cx + 13, cy - 1,
                          fill=C_HEADER_BG, outline="")

        # Left antenna: base on dome top → tip upper-left
        ax1, ay1 = cx - 13, cy - ry + 3
        ax2, ay2 = cx - 21, cy - ry - 14
        canvas.create_line(ax1, ay1, ax2, ay2,
                          fill=C_ACCENT, width=2, capstyle=tk.ROUND)
        canvas.create_oval(ax2 - 4, ay2 - 4, ax2 + 4, ay2 + 4,
                          fill=C_ACCENT, outline="")

        # Right antenna
        bx1, by1 = cx + 13, cy - ry + 3
        bx2, by2 = cx + 21, cy - ry - 14
        canvas.create_line(bx1, by1, bx2, by2,
                          fill=C_ACCENT, width=2, capstyle=tk.ROUND)
        canvas.create_oval(bx2 - 4, by2 - 4, bx2 + 4, by2 + 4,
                          fill=C_ACCENT, outline="")

    def _card(self, parent):
        """Return an inner frame styled as a dark card."""
        outer = tk.Frame(parent, bg=C_BORDER, padx=1, pady=1)
        inner = tk.Frame(outer, bg=C_SURFACE, padx=14, pady=12)
        inner.pack(fill=tk.BOTH, expand=True)
        return outer, inner

    def create_connection_controls(self, parent):
        pass

    def create_install_panel(self):
        outer, panel = self._card(self.feature_host)
        row = tk.Frame(panel, bg=C_SURFACE)
        row.pack(fill=tk.X, pady=(0, 10))
        tk.Label(row, text="APK/XAPK", font=F_UI, bg=C_SURFACE, fg=C_TEXT_DIM, width=8).pack(side=tk.LEFT)
        self.apk_combo = ttk.Combobox(row, textvariable=self.selected_apk, state="readonly")
        self.apk_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        self.install_btn = ttk.Button(
            panel, text="安装到当前设备",
            command=self.start_install_thread,
            style="Action.TButton"
        )
        self.install_btn.pack(fill=tk.X)
        self.feature_panels["install"] = outer

    def create_uninstall_panel(self):
        outer, panel = self._card(self.feature_host)
        row = tk.Frame(panel, bg=C_SURFACE)
        row.pack(fill=tk.X, pady=(0, 10))
        tk.Label(row, text="应用包名", font=F_UI, bg=C_SURFACE, fg=C_TEXT_DIM, width=8).pack(side=tk.LEFT)
        self.uninstall_package_combo = ttk.Combobox(
            row, textvariable=self.selected_uninstall_package, state="readonly")
        self.uninstall_package_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        self.uninstall_btn = ttk.Button(
            panel, text="从当前设备卸载",
            command=self.start_uninstall_thread,
            style="Action.TButton"
        )
        self.uninstall_btn.pack(fill=tk.X)
        self.feature_panels["uninstall"] = outer

    def create_export_panel(self):
        outer, panel = self._card(self.feature_host)

        package_row = tk.Frame(panel, bg=C_SURFACE)
        package_row.pack(fill=tk.X, pady=(0, 6))
        tk.Label(package_row, text="应用包名", font=F_UI, bg=C_SURFACE,
                 fg=C_TEXT_DIM, width=8).pack(side=tk.LEFT)
        self.export_package_combo = ttk.Combobox(
            package_row,
            textvariable=self.selected_export_package,
            state="readonly"
        )
        self.export_package_combo.pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0)
        )

        target_row = tk.Frame(panel, bg=C_SURFACE)
        target_row.pack(fill=tk.X, pady=(0, 10))
        tk.Label(target_row, text="目标文件夹", font=F_UI, bg=C_SURFACE,
                 fg=C_TEXT_DIM, width=8).pack(side=tk.LEFT)
        ttk.Entry(
            target_row,
            textvariable=self.export_target_dir,
            state="readonly"
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 6))
        ttk.Button(
            target_row,
            text="选择文件夹",
            command=self.select_export_directory
        ).pack(side=tk.LEFT)

        self.export_btn = ttk.Button(
            panel,
            text="导出到目标文件夹",
            command=self.start_export_thread,
            style="Action.TButton"
        )
        self.export_btn.pack(fill=tk.X)
        self.feature_panels["export"] = outer

    def create_push_panel(self):
        outer, panel = self._card(self.feature_host)

        local_row = tk.Frame(panel, bg=C_SURFACE)
        local_row.pack(fill=tk.X, pady=(0, 6))
        tk.Label(local_row, text="本地文件", font=F_UI, bg=C_SURFACE, fg=C_TEXT_DIM, width=8).pack(side=tk.LEFT)
        ttk.Entry(local_row, textvariable=self.push_local_path).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 6))
        ttk.Button(local_row, text="浏览", command=self.select_local_file).pack(side=tk.LEFT)

        remote_row = tk.Frame(panel, bg=C_SURFACE)
        remote_row.pack(fill=tk.X, pady=(0, 10))
        tk.Label(remote_row, text="手机路径", font=F_UI, bg=C_SURFACE, fg=C_TEXT_DIM, width=8).pack(side=tk.LEFT)
        ttk.Entry(remote_row, textvariable=self.push_remote_path).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

        ttk.Button(panel, text="推送到当前设备",
                  command=self.start_push_thread,
                  style="Action.TButton").pack(fill=tk.X)
        self.feature_panels["push"] = outer

    def create_pull_panel(self):
        outer, panel = self._card(self.feature_host)
        row = tk.Frame(panel, bg=C_SURFACE)
        row.pack(fill=tk.X, pady=(0, 6))
        tk.Label(row, text="手机文件", font=F_UI, bg=C_SURFACE, fg=C_TEXT_DIM, width=8).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.pull_remote_path).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        tk.Label(panel, text="文件将保存至本机 ReadByPhone 目录",
                font=("Segoe UI", 8), bg=C_SURFACE, fg=C_TEXT_MUTED).pack(anchor=tk.W, pady=(0, 10))
        ttk.Button(panel, text="拉取到电脑",
                  command=self.start_pull_thread,
                  style="Action.TButton").pack(fill=tk.X)
        self.feature_panels["pull"] = outer

    def create_terminal_panel(self):
        ADB_QUICK_CMDS = [
            ("查看设备列表",       "devices"),
            ("---", None),
            ("Shell 交互",         "shell"),
            ("查看 logcat",        "logcat -d"),
            ("清空 logcat",        "shell logcat -c"),
            ("---", None),
            ("列出所有应用",       "shell pm list packages"),
            ("列出第三方应用",     "shell pm list packages -3"),
            ("列出系统应用",       "shell pm list packages -s"),
            ("---", None),
            ("查看屏幕分辨率",     "shell wm size"),
            ("查看屏幕密度",       "shell wm density"),
            ("截图到 /sdcard/",    "shell screencap /sdcard/screen.png"),
            ("拉取截图",           "pull /sdcard/screen.png"),
            ("---", None),
            ("查看 CPU 信息",      "shell cat /proc/cpuinfo"),
            ("查看内存信息",       "shell cat /proc/meminfo"),
            ("查看电池状态",       "shell dumpsys battery"),
            ("查看网络信息",       "shell ifconfig"),
            ("---", None),
            ("重启设备",           "reboot"),
            ("重启到 Recovery",    "reboot recovery"),
            ("重启到 Bootloader",  "reboot bootloader"),
            ("---", None),
            ("开启无线调试 5555",  "tcpip 5555"),
            ("关闭无线调试",       "usb"),
        ]

        outer, panel = self._card(self.feature_host)
        panel.config(padx=0, pady=0)

        left = tk.Frame(panel, bg=C_SURFACE, width=190)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(14, 0), pady=12)
        left.pack_propagate(False)

        tk.Label(left, text="常用命令", font=("Segoe UI", 8),
                bg=C_SURFACE, fg=C_TEXT_MUTED).pack(anchor=tk.W, pady=(0, 4))

        cmd_frame = tk.Frame(left, bg=C_SURFACE)
        cmd_frame.pack(fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(cmd_frame, orient=tk.VERTICAL)
        self.quick_cmd_listbox = tk.Listbox(
            cmd_frame, yscrollcommand=sb.set,
            font=F_MONO,
            bg=C_SURFACE2, fg=C_TEXT_DIM,
            selectbackground=C_ACCENT, selectforeground="#ffffff",
            relief=tk.FLAT, borderwidth=0,
            highlightthickness=1,
            highlightcolor=C_BORDER, highlightbackground=C_BORDER,
            activestyle="none",
        )
        sb.config(command=self.quick_cmd_listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.quick_cmd_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._quick_cmd_map = {}
        for label, args in ADB_QUICK_CMDS:
            if args is None:
                self.quick_cmd_listbox.insert(tk.END, "")
                self.quick_cmd_listbox.itemconfig(tk.END,
                    fg=C_BORDER, selectbackground=C_SURFACE2, selectforeground=C_BORDER)
            else:
                idx = self.quick_cmd_listbox.size()
                self.quick_cmd_listbox.insert(tk.END, "  " + label)
                self._quick_cmd_map[idx] = args

        self.quick_cmd_listbox.bind("<<ListboxSelect>>", self._on_quick_cmd_select)

        # Divider
        tk.Frame(panel, bg=C_BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=8)

        right = tk.Frame(panel, bg=C_SURFACE)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 14), pady=12)

        tk.Label(right, text="命令（adb 后的部分，自动附加 -s <设备>）",
                font=("Segoe UI", 8), bg=C_SURFACE, fg=C_TEXT_MUTED).pack(anchor=tk.W, pady=(0, 6))

        input_row = tk.Frame(right, bg=C_SURFACE)
        input_row.pack(fill=tk.X)

        self.terminal_cmd_var = tk.StringVar()
        self.terminal_entry = ttk.Entry(input_row, textvariable=self.terminal_cmd_var,
                                       font=F_MONO)
        self.terminal_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.terminal_entry.bind("<Return>", lambda e: self.run_terminal_command())

        ttk.Button(input_row, text="执行",
                  style="Action.TButton",
                  command=self.run_terminal_command).pack(side=tk.LEFT)

        tk.Label(right, text="结果输出在下方运行日志中",
                font=("Segoe UI", 8), bg=C_SURFACE, fg=C_TEXT_MUTED).pack(anchor=tk.W, pady=(8, 0))

        self.feature_panels["terminal"] = outer

    def _on_quick_cmd_select(self, event=None):
        sel = self.quick_cmd_listbox.curselection()
        if not sel:
            return
        args = self._quick_cmd_map.get(sel[0])
        if args:
            self.terminal_cmd_var.set(args)
            self.terminal_entry.focus_set()
            self.terminal_entry.icursor(tk.END)

    def run_terminal_command(self):
        raw = self.terminal_cmd_var.get().strip()
        if not raw:
            return
        import shlex
        try:
            args = shlex.split(raw)
        except ValueError:
            args = raw.split()

        device = self.get_selected_serial()
        if device and args and args[0] != "devices":
            cmd = ["adb", "-s", device] + args
        else:
            cmd = ["adb"] + args

        def run():
            self.log("-" * 40)
            self.log("执行命令: " + " ".join(cmd), "cmd")
            try:
                process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    startupinfo=self.create_startupinfo()
                )
                while True:
                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break
                    if line:
                        self.log(to_text(line).rstrip())
                stderr = process.stderr.read()
                if stderr:
                    self.log(to_text(stderr).strip(), "err")
                if process.returncode == 0:
                    self.log("命令执行完毕。", "ok")
                else:
                    self.log("命令返回码: {}".format(process.returncode), "err")
            except OSError:
                self.log("错误: 未找到 adb 命令，请检查 PATH 配置。", "err")
            except Exception as error:
                self.log("执行出错: " + to_text(error), "err")

        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()

    def create_config_panel(self):
        outer, panel = self._card(self.feature_host)
        panel.config(padx=0, pady=0)

        left = tk.Frame(panel, bg=C_SURFACE, padx=14, pady=12)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Label(left, text="卸载包名（精确匹配）",
                font=F_UI_BOLD, bg=C_SURFACE, fg=C_TEXT_DIM).pack(anchor=tk.W, pady=(0, 6))
        self.pkg_listbox = self._make_config_list(left)
        self._make_config_controls(left, self.pkg_listbox, UNINSTALL_PACKAGES_FILE, "pkg_entry")

        tk.Frame(panel, bg=C_BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, pady=8)

        right = tk.Frame(panel, bg=C_SURFACE, padx=14, pady=12)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Label(right, text="包名前缀（前缀筛选）",
                font=F_UI_BOLD, bg=C_SURFACE, fg=C_TEXT_DIM).pack(anchor=tk.W, pady=(0, 6))
        self.prefix_listbox = self._make_config_list(right)
        self._make_config_controls(right, self.prefix_listbox, UNINSTALL_PREFIXES_FILE, "prefix_entry")

        self.feature_panels["config"] = outer

    def _make_config_list(self, parent):
        frame = tk.Frame(parent, bg=C_SURFACE)
        frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL)
        lb = tk.Listbox(
            frame, yscrollcommand=sb.set,
            selectmode=tk.EXTENDED,
            font=F_MONO, height=5,
            bg=C_SURFACE2, fg=C_TEXT_DIM,
            selectbackground=C_ACCENT, selectforeground="#ffffff",
            relief=tk.FLAT, borderwidth=0,
            highlightthickness=1,
            highlightcolor=C_BORDER, highlightbackground=C_BORDER,
        )
        sb.config(command=lb.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        return lb

    def _make_config_controls(self, parent, listbox, filepath, entry_attr):
        add_row = tk.Frame(parent, bg=C_SURFACE)
        add_row.pack(fill=tk.X, pady=(0, 4))
        entry = ttk.Entry(add_row)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        setattr(self, entry_attr, entry)
        ttk.Button(add_row, text="添加",
                  command=lambda lb=listbox, e=entry: self._config_add(lb, e)).pack(side=tk.LEFT)

        btn_row = tk.Frame(parent, bg=C_SURFACE)
        btn_row.pack(fill=tk.X)
        ttk.Button(btn_row, text="删除选中",
                  command=lambda lb=listbox: self._config_delete(lb)).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="保存",
                  style="Action.TButton",
                  command=lambda lb=listbox, p=filepath: self._config_save(lb, p)).pack(side=tk.LEFT)

    def _config_add(self, listbox, entry):
        value = entry.get().strip()
        if not value:
            return
        if value not in list(listbox.get(0, tk.END)):
            listbox.insert(tk.END, value)
        entry.delete(0, tk.END)

    def _config_delete(self, listbox):
        for index in reversed(listbox.curselection()):
            listbox.delete(index)

    def _config_save(self, listbox, filepath):
        names = list(listbox.get(0, tk.END))
        try:
            save_package_names(filepath, names)
            self.log("已保存 {} 条到 {}".format(len(names), os.path.basename(filepath)), "ok")
            self.refresh_uninstall_packages()
        except Exception as error:
            self.log("保存失败: " + to_text(error), "err")

    def _reload_config_panel(self):
        pkg_names = load_package_names(UNINSTALL_PACKAGES_FILE)
        prefix_names = load_package_names(UNINSTALL_PREFIXES_FILE)
        self.pkg_listbox.delete(0, tk.END)
        for name in pkg_names:
            self.pkg_listbox.insert(tk.END, name)
        self.prefix_listbox.delete(0, tk.END)
        for name in prefix_names:
            self.prefix_listbox.insert(tk.END, name)

    def show_feature(self, feature_name):
        if feature_name not in self.feature_panels:
            return
        for name, panel in self.feature_panels.items():
            panel.pack_forget()
            self.feature_buttons[name].set_active(name == feature_name)
        self.feature_panels[feature_name].pack(fill=tk.BOTH, expand=True)
        if feature_name == "config":
            self._reload_config_panel()

    def clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state="disabled")

    def log(self, message, tag=None):
        message = to_text(message)
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, "[{}] ".format(timestamp), "time")
        if tag:
            self.log_text.insert(tk.END, message + "\n", tag)
        else:
            lower = message.lower()
            if message.startswith("执行命令:"):
                self.log_text.insert(tk.END, message + "\n", "cmd")
            elif any(w in lower for w in ("失败", "错误", "error", "failed", "cannot", "unable")):
                self.log_text.insert(tk.END, message + "\n", "err")
            elif any(w in lower for w in ("成功", "完成", "success")):
                self.log_text.insert(tk.END, message + "\n", "ok")
            else:
                self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def select_local_file(self):
        filename = filedialog.askopenfilename()
        if filename:
            self.push_local_path.set(filename)

    def select_export_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.export_target_dir.set(directory)

    def create_startupinfo(self):
        if os.name != "nt":
            return None
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return startupinfo

    def get_devices(self):
        try:
            output = subprocess.check_output(
                ["adb", "devices"], startupinfo=self.create_startupinfo()
            )
            lines = to_text(output).strip().splitlines()[1:]
            devices = []
            for line in lines:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    serial = parts[0]
                    model = self.get_device_model(serial)
                    devices.append("{} ({})".format(model, serial))
            return devices
        except OSError:
            self.log("错误: 未找到 adb 命令，请检查 PATH 配置。")
            return []
        except Exception as error:
            self.log("获取设备失败: " + to_text(error))
            return []

    def get_device_model(self, serial):
        try:
            output = subprocess.check_output(
                ["adb", "-s", serial, "shell", "getprop", "ro.product.model"],
                startupinfo=self.create_startupinfo()
            )
            return to_text(output).strip() or "Unknown"
        except Exception:
            return "Unknown"

    def get_selected_serial(self):
        selection = self.selected_device.get()
        if not selection:
            return None
        return serial_from_device_label(selection)

    def get_apks(self):
        paths = []
        for pattern in ("*.apk", "*.xapk"):
            paths.extend(glob.glob(os.path.join(APK_DIR, pattern)))
        return sorted(os.path.basename(path) for path in paths if _is_install_package(path))

    def get_installed_packages(self, prefixes):
        device = self.get_selected_serial()
        if not device or not prefixes:
            return []
        try:
            output = subprocess.check_output(
                ["adb", "-s", device, "shell", "pm", "list", "packages"],
                startupinfo=self.create_startupinfo()
            )
            return parse_adb_package_list(output, prefixes)
        except Exception as error:
            self.log("检测手机已安装包失败: " + to_text(error))
            return []

    def get_all_installed_packages(self):
        device = self.get_selected_serial()
        if not device:
            return set()
        try:
            output = subprocess.check_output(
                ["adb", "-s", device, "shell", "pm", "list", "packages"],
                startupinfo=self.create_startupinfo()
            )
            raw = to_text(output)
            result = set()
            for line in raw.splitlines():
                line = line.strip()
                if line.startswith("package:"):
                    result.add(line[len("package:"):])
            return result
        except Exception as error:
            self.log("获取设备包列表失败: " + to_text(error))
            return set()

    def _fetch_package_labels(self, device, packages):
        """Fetch app labels by pulling base.apk and parsing AndroidManifest.xml.

        Pulls each APK to a temp file, extracts the label via binary XML
        parsing, then cleans up.  Results are cached in self._package_labels.
        """
        if not device or not packages:
            return {}

        # Only fetch labels we don't already have
        missing = [p for p in packages if p not in self._package_labels]
        if not missing:
            return {p: self._package_labels[p] for p in packages
                    if p in self._package_labels}

        temp_dir = tempfile.gettempdir()
        new_labels = {}

        for pkg in missing:
            temp_apk = None
            try:
                # Get APK path from device
                path_output = subprocess.check_output(
                    ["adb", "-s", device, "shell", "pm", "path", pkg],
                    startupinfo=self.create_startupinfo(),
                    timeout=10,
                )
                path_line = to_text(path_output).strip()
                if not path_line.startswith("package:"):
                    continue
                apk_path = path_line[len("package:"):].strip()
                if not apk_path:
                    continue

                # Pull to temp file
                temp_apk = os.path.join(temp_dir, "adb_label_{}.apk".format(pkg))
                subprocess.check_call(
                    ["adb", "-s", device, "pull", apk_path, temp_apk],
                    startupinfo=self.create_startupinfo(),
                    timeout=30,
                )

                # Extract label
                label = extract_apk_label(temp_apk)
                if label:
                    new_labels[pkg] = label
                    self._package_labels[pkg] = label
            except Exception:
                pass
            finally:
                if temp_apk and os.path.isfile(temp_apk):
                    try:
                        os.unlink(temp_apk)
                    except Exception:
                        pass

        # Merge cached labels with newly fetched ones
        result = {}
        for pkg in packages:
            if pkg in self._package_labels:
                result[pkg] = self._package_labels[pkg]
        return result

    def _get_selected_package(self, display_text):
        """Extract the package name from a combo box display string.

        Display strings are formatted as 'App Label (package.name)' or just
        'package.name' when no label is available.
        """
        if not display_text:
            return None
        pkg = self._package_display_map.get(display_text)
        if pkg:
            return pkg
        return display_text.strip()

    def _build_package_display_list(self, packages):
        """Convert a list of package names to display strings with labels.

        Returns (display_list, display_map) where display_map maps
        display_string -> package_name.
        """
        display_map = {}
        display_list = []
        for pkg in packages:
            label = self._package_labels.get(pkg, "")
            if label:
                display = "{} ({})".format(label, pkg)
            else:
                display = pkg
            display_map[display] = pkg
            display_list.append(display)
        return display_list, display_map

    def _find_previous_display(self, display_list, display_map, previous_display):
        """Find a previous selection in the new display list."""
        if not previous_display:
            return None
        previous_pkg = self._get_selected_package(previous_display)
        if not previous_pkg:
            return None
        for display in display_list:
            if display_map.get(display) == previous_pkg:
                return display
        return None

    def get_export_packages(self):
        device = self.get_selected_serial()
        if not device:
            return []
        try:
            output = subprocess.check_output(
                ["adb", "-s", device, "shell", "pm", "list", "packages", "-3"],
                startupinfo=self.create_startupinfo()
            )
            return parse_adb_packages(output)
        except Exception as error:
            self.log("获取第三方应用列表失败: " + to_text(error), "err")
            return []

    def refresh_data(self):
        self._package_labels.clear()
        self._package_display_map.clear()
        self.log("正在刷新设备和文件列表...")
        previous_device = self.selected_device.get()
        devices = self.get_devices()
        self.device_combo["values"] = devices
        if devices:
            preferred_device = None
            preferred_serial = getattr(self, "preferred_device_serial", None)
            if preferred_serial:
                for device in devices:
                    if serial_from_device_label(device) == preferred_serial:
                        preferred_device = device
                        break
            if preferred_device:
                self.selected_device.set(preferred_device)
                self.preferred_device_serial = None
            elif previous_device in devices:
                self.selected_device.set(previous_device)
            else:
                self.device_combo.current(0)
            self.log("找到 {} 个在线设备。".format(len(devices)))
        else:
            self.device_combo.set("")
            self.log("未找到在线设备。")

        apks = self.get_apks()
        self.apk_combo["values"] = apks
        if apks:
            if self.selected_apk.get() not in apks:
                self.apk_combo.current(0)
            self.log("找到 {} 个 APK/XAPK 文件。".format(len(apks)))
        else:
            self.apk_combo.set("")
            self.log("apk 文件夹中未找到 APK/XAPK 文件。")

        self.refresh_uninstall_packages()
        self.refresh_export_packages()

    def refresh_uninstall_packages(self):
        configured = load_package_names(UNINSTALL_PACKAGES_FILE)
        prefixes = load_package_names(UNINSTALL_PREFIXES_FILE)
        detected = self.get_installed_packages(prefixes)

        if configured and self.get_selected_serial():
            installed_set = self.get_all_installed_packages()
            confirmed_configured = [p for p in configured if p in installed_set]
        else:
            confirmed_configured = []

        packages = merge_package_names(confirmed_configured, detected)
        previous_display = self.selected_uninstall_package.get()

        device = self.get_selected_serial()
        self._fetch_package_labels(device, packages)
        display_list, display_map = self._build_package_display_list(packages)
        self._package_display_map.update(display_map)

        self.uninstall_package_combo["values"] = display_list

        if display_list:
            found = self._find_previous_display(
                display_list, display_map, previous_display
            )
            if found:
                self.selected_uninstall_package.set(found)
            else:
                self.uninstall_package_combo.current(0)
            self.log("卸载列表找到 {} 个已安装包（前缀匹配 {}，精确匹配 {}）。".format(
                len(packages), len(detected), len(confirmed_configured)
            ))
        else:
            self.uninstall_package_combo.set("")
            if not prefixes and not configured:
                self.log("卸载配置为空，请在「配置」页添加包名或前缀。")
            else:
                self.log("当前设备未安装任何配置中的包。")

    def refresh_export_packages(self):
        packages = self.get_export_packages()
        previous_display = self.selected_export_package.get()

        device = self.get_selected_serial()
        self._fetch_package_labels(device, packages)
        display_list, display_map = self._build_package_display_list(packages)
        self._package_display_map.update(display_map)

        self.export_package_combo["values"] = display_list
        if display_list:
            found = self._find_previous_display(
                display_list, display_map, previous_display
            )
            if found:
                self.selected_export_package.set(found)
            else:
                self.export_package_combo.current(0)
            self.log("找到 {} 个第三方应用可供导出。".format(len(packages)))
        else:
            self.export_package_combo.set("")
            self.log("当前设备未找到可导出的第三方应用。")

    def on_device_selected(self, event=None):
        self._package_labels.clear()
        self._package_display_map.clear()
        self.log("已切换设备: " + self.selected_device.get())
        self.refresh_uninstall_packages()
        self.refresh_export_packages()

    def start_connect_thread(self):
        try:
            address = normalize_network_address(self.network_address.get())
        except ValueError as error:
            messagebox.showwarning("提示", to_text(error))
            return

        def run():
            self.log("-" * 40)
            self.log("执行命令: adb connect " + address)
            try:
                process = subprocess.Popen(
                    ["adb", "connect", address],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    startupinfo=self.create_startupinfo()
                )
                stdout, stderr = process.communicate()
                output = to_text(stdout).strip()
                error_output = to_text(stderr).strip()
                if output:
                    self.log(output)
                if error_output:
                    self.log("输出: " + error_output)
                failed_output = (output + " " + error_output).lower()
                failed = any(m in failed_output for m in ("failed", "cannot", "unable"))
                if process.returncode == 0 and not failed:
                    self.preferred_device_serial = address
                    self.log("设备连接成功。")
                    self.root.after(0, self.refresh_data)
                else:
                    self.log("设备连接失败，请检查 IP 地址和设备网络调试设置。")
            except OSError:
                self.log("错误: 未找到 adb 命令，请检查 PATH 配置。")
            except Exception as error:
                self.log("连接设备失败: " + to_text(error))
            finally:
                self.root.after(0, lambda: self.connect_btn.config(state="normal"))

        self.connect_btn.config(state="disabled")
        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()

    def restart_adb(self):
        def run():
            self.log("-" * 40)
            self.log("正在重启 ADB 服务...")
            try:
                startupinfo = self.create_startupinfo()
                subprocess.call(["adb", "kill-server"], startupinfo=startupinfo)
                subprocess.call(["adb", "start-server"], startupinfo=startupinfo)
                self.log("ADB 服务重启完成。")
                self.root.after(1000, self.refresh_data)
            except Exception as error:
                self.log("重启 ADB 失败: " + to_text(error))
            finally:
                self.root.after(0, lambda: self.restart_btn.config(state="normal"))

        self.restart_btn.config(state="disabled")
        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()

    def run_adb_command(self, args, success_msg="操作成功", success_callback=None,
                        completion_callback=None):
        device = self.get_selected_serial()
        if not device:
            messagebox.showwarning("提示", "请先选择一个设备。")
            return

        def run():
            self.log("-" * 40)
            self.log("执行命令: adb -s {} {}".format(device, " ".join(args)))
            try:
                process = subprocess.Popen(
                    ["adb", "-s", device] + args,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    startupinfo=self.create_startupinfo()
                )
                while True:
                    output = process.stdout.readline()
                    if not output and process.poll() is not None:
                        break
                    if output:
                        self.log(to_text(output).strip())
                stderr = process.stderr.read()
                if stderr:
                    self.log("输出: " + to_text(stderr).strip())
                if process.returncode == 0:
                    self.log(success_msg)
                    if success_callback:
                        self.root.after(0, success_callback)
                else:
                    self.log("操作失败，请检查上方日志。")
            except Exception as error:
                self.log("执行出错: " + to_text(error))
            finally:
                if completion_callback:
                    self.root.after(0, completion_callback)

        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()

    def start_install_thread(self):
        apk = self.selected_apk.get()
        if not apk:
            messagebox.showwarning("提示", "请先选择一个 APK/XAPK 文件。")
            return
        package_path = os.path.join(APK_DIR, apk)
        if apk.lower().endswith(".xapk"):
            temp_dir = tempfile.mkdtemp(prefix="adb-xapk-")
            try:
                args = build_xapk_install_args(package_path, temp_dir)
            except ValueError as error:
                shutil.rmtree(temp_dir, ignore_errors=True)
                self.log(to_text(error), "err")
                return
            self.log("XAPK 解包完成，准备安装 {} 个 APK 分包。".format(len(args) - 2))
            self.run_adb_command(
                args,
                "安装完成。",
                completion_callback=lambda path=temp_dir: shutil.rmtree(path, ignore_errors=True)
            )
            return
        self.run_adb_command(["install", "-r", package_path], "安装完成。")

    def start_uninstall_thread(self):
        display_text = self.selected_uninstall_package.get()
        package_name = self._get_selected_package(display_text)
        if not package_name:
            messagebox.showwarning("提示", "请先选择一个要卸载的包名。")
            return
        self.run_adb_command(["uninstall", package_name], "卸载完成。", self.refresh_data)

    def start_push_thread(self):
        local = self.push_local_path.get()
        remote = self.push_remote_path.get()
        if not local or not remote:
            messagebox.showwarning("提示", "请选择本地文件并填写手机目标路径。")
            return
        self.run_adb_command(["push", local, remote], "文件推送成功。")

    def start_pull_thread(self):
        remote = self.pull_remote_path.get()
        if not remote:
            messagebox.showwarning("提示", "请填写手机文件路径。")
            return
        if not os.path.exists(PULL_DIR):
            try:
                os.makedirs(PULL_DIR)
                self.log("已创建目录: " + PULL_DIR)
            except Exception as error:
                self.log("创建目录失败: " + to_text(error))
                return
        self.run_adb_command(["pull", remote, PULL_DIR],
                            "文件拉取成功，保存至 " + PULL_DIR)

    def start_export_thread(self):
        device = self.get_selected_serial()
        if not device:
            messagebox.showwarning("提示", "请先选择一个设备。")
            return

        display_text = self.selected_export_package.get().strip()
        package_name = self._get_selected_package(display_text)
        if not package_name:
            messagebox.showwarning("提示", "请先选择一个要导出的应用。")
            return

        target_dir = self.export_target_dir.get().strip()
        if not target_dir or not os.path.isdir(target_dir):
            messagebox.showwarning("提示", "请选择有效的目标文件夹。")
            return

        self.export_btn.config(state="disabled")
        thread = threading.Thread(
            target=self._export_app,
            args=(device, package_name, target_dir)
        )
        thread.daemon = True
        thread.start()

    def _export_app(self, device, package_name, target_dir):
        def worker_log(message, tag=None):
            self.root.after(
                0,
                lambda message=message, tag=tag: self.log(message, tag)
            )

        def run_command(command):
            worker_log("执行命令: " + " ".join(command), "cmd")
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=self.create_startupinfo()
            )
            stdout, stderr = process.communicate()
            return process.returncode, to_text(stdout).strip(), to_text(stderr).strip()

        try:
            query_command = [
                "adb", "-s", device, "shell", "pm", "path", package_name
            ]
            returncode, output, error_output = run_command(query_command)
            if returncode != 0:
                worker_log("查询应用 APK 路径失败: " + (error_output or output), "err")
                return

            apk_paths = parse_adb_apk_paths(output)
            if not apk_paths:
                worker_log("导出失败: 未找到 APK 路径。", "err")
                return

            package_dir = os.path.join(target_dir, package_name)
            if not os.path.isdir(package_dir):
                try:
                    os.makedirs(package_dir)
                except OSError as error:
                    worker_log("创建导出目录失败: " + to_text(error), "err")
                    return

            failed_count = 0
            for remote_path in apk_paths:
                local_path = os.path.join(package_dir, os.path.basename(remote_path))
                pull_command = [
                    "adb", "-s", device, "pull", remote_path, local_path
                ]
                pull_code, pull_output, pull_error = run_command(pull_command)
                if pull_output:
                    worker_log(pull_output)
                if pull_error:
                    worker_log("输出: " + pull_error, "err" if pull_code else None)
                if pull_code != 0:
                    failed_count += 1

            if failed_count:
                worker_log(
                    "导出部分失败: 成功 {} 个，失败 {} 个。".format(
                        len(apk_paths) - failed_count, failed_count
                    ),
                    "err"
                )
            else:
                worker_log("导出完成，保存至 " + package_dir, "ok")
        except OSError:
            worker_log("导出失败: 未找到 adb 命令，请检查 PATH 配置。", "err")
        except Exception as error:
            worker_log("导出失败: " + to_text(error), "err")
        finally:
            self.root.after(0, lambda: self.export_btn.config(state="normal"))


if __name__ == "__main__":
    root = tk.Tk()
    app = AdbInstallerApp(root)
    root.mainloop()
