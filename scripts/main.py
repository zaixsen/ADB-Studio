# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import datetime
import glob
import os
import re
import subprocess
import sys
import threading

from package_config import load_package_names, merge_package_names, parse_adb_package_list, save_package_names

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
APK_DIR = os.path.join(PROJECT_DIR, "apk")
PULL_DIR = os.path.join(PROJECT_DIR, "ReadByPhone")
UNINSTALL_PACKAGES_FILE = os.path.join(PROJECT_DIR, "uninstall_packages.txt")
UNINSTALL_PREFIXES_FILE = os.path.join(PROJECT_DIR, "uninstall_package_prefixes.txt")

# Colors
COLOR_NAV_ACTIVE_BG = "#2563EB"
COLOR_NAV_ACTIVE_FG = "#FFFFFF"
COLOR_NAV_IDLE_BG = "#E5E7EB"
COLOR_NAV_IDLE_FG = "#374151"
COLOR_NAV_HOVER_BG = "#D1D5DB"
COLOR_LOG_BG = "#1E1E1E"
COLOR_LOG_FG = "#D4D4D4"
COLOR_LOG_TIME = "#6A9955"
COLOR_LOG_CMD = "#4FC1FF"
COLOR_LOG_ERR = "#F44747"
COLOR_LOG_OK = "#4EC9B0"

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


class NavButton(tk.Frame):
    """Custom nav tab button with reliable cross-platform active state."""

    def __init__(self, parent, text, command, **kwargs):
        tk.Frame.__init__(self, parent, cursor="hand2", **kwargs)
        self._command = command
        self._active = False
        self._label = tk.Label(
            self, text=text, padx=14, pady=8,
            font=("TkDefaultFont", 9),
            bg=COLOR_NAV_IDLE_BG, fg=COLOR_NAV_IDLE_FG,
            cursor="hand2"
        )
        self._label.pack(fill=tk.BOTH, expand=True)
        self._label.bind("<Button-1>", self._on_click)
        self._label.bind("<Enter>", self._on_enter)
        self._label.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _on_click(self, event=None):
        self._command()

    def _on_enter(self, event=None):
        if not self._active:
            self._label.config(bg=COLOR_NAV_HOVER_BG)

    def _on_leave(self, event=None):
        if not self._active:
            self._label.config(bg=COLOR_NAV_IDLE_BG)

    def set_active(self, active):
        self._active = active
        if active:
            self._label.config(
                bg=COLOR_NAV_ACTIVE_BG, fg=COLOR_NAV_ACTIVE_FG,
                font=("TkDefaultFont", 9, "bold")
            )
        else:
            self._label.config(
                bg=COLOR_NAV_IDLE_BG, fg=COLOR_NAV_IDLE_FG,
                font=("TkDefaultFont", 9)
            )


class AdbInstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ADB 设备工具")
        self.root.geometry("780x680")
        self.root.minsize(680, 560)

        self.selected_device = tk.StringVar()
        self.selected_apk = tk.StringVar()
        self.selected_uninstall_package = tk.StringVar()
        self.network_address = tk.StringVar()
        self.push_local_path = tk.StringVar()
        self.push_remote_path = tk.StringVar(value="/sdcard/Download/")
        self.pull_remote_path = tk.StringVar(value="/sdcard/Download/")
        self.preferred_device_serial = None

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

        style.configure("TButton", padding=(10, 6))
        style.configure("TLabel", padding=2)
        style.configure("Toolbar.TFrame", padding=(10, 6, 10, 6))
        style.configure("Action.TButton", padding=(14, 8), font=("TkDefaultFont", 10, "bold"))
        style.map(
            "Action.TButton",
            background=[("active", "#1d4ed8"), ("!disabled", "#2563EB")],
            foreground=[("!disabled", "white")]
        )

    def create_widgets(self):
        # ── Row 1: device selector + connection controls ──
        toolbar = ttk.Frame(self.root, style="Toolbar.TFrame")
        toolbar.pack(fill=tk.X)

        ttk.Label(toolbar, text="设备:").pack(side=tk.LEFT)
        self.device_combo = ttk.Combobox(
            toolbar,
            textvariable=self.selected_device,
            state="readonly",
            width=28
        )
        self.device_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))
        self.device_combo.bind("<<ComboboxSelected>>", self.on_device_selected)

        ttk.Button(toolbar, text="刷新", command=self.refresh_data).pack(side=tk.LEFT, padx=(0, 4))
        self.restart_btn = ttk.Button(toolbar, text="重启 ADB", command=self.restart_adb)
        self.restart_btn.pack(side=tk.LEFT, padx=(0, 16))

        # IP connection inline in the same toolbar row
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, pady=4, padx=(0, 8))
        ttk.Label(toolbar, text="IP:").pack(side=tk.LEFT)
        ttk.Entry(toolbar, textvariable=self.network_address, width=18).pack(
            side=tk.LEFT, padx=(4, 6)
        )
        self.connect_btn = ttk.Button(
            toolbar, text="连接", command=self.start_connect_thread
        )
        self.connect_btn.pack(side=tk.LEFT)

        # ── Row 2: nav tabs ──
        nav_frame = tk.Frame(self.root, bg=COLOR_NAV_IDLE_BG, pady=0)
        nav_frame.pack(fill=tk.X, padx=10, pady=(6, 0))

        nav_items = [
            ("install", "安装 APK"),
            ("uninstall", "卸载应用"),
            ("push", "推送文件"),
            ("pull", "拉取文件"),
            ("terminal", "终端"),
            ("config", "配置"),
        ]
        for feature_name, label in nav_items:
            btn = NavButton(
                nav_frame,
                text=label,
                command=lambda name=feature_name: self.show_feature(name),
                bg=COLOR_NAV_IDLE_BG
            )
            btn.pack(side=tk.LEFT, padx=(0, 2))
            self.feature_buttons[feature_name] = btn

        # ── Row 3: feature panels (fixed height container) ──
        self.feature_host = tk.Frame(self.root, height=200)
        self.feature_host.pack(fill=tk.X, padx=10, pady=(0, 4))
        self.feature_host.pack_propagate(False)

        self.create_install_panel()
        self.create_uninstall_panel()
        self.create_push_panel()
        self.create_pull_panel()
        self.create_terminal_panel()
        self.create_config_panel()

        # ── Row 4: log area ──
        log_frame = ttk.LabelFrame(self.root, text="运行日志", padding=(8, 4))
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(log_toolbar, text="ADB 命令和操作结果").pack(side=tk.LEFT)
        ttk.Button(log_toolbar, text="清空", command=self.clear_log).pack(side=tk.RIGHT)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            state="disabled",
            font=("Consolas", 9),
            wrap=tk.WORD,
            bg=COLOR_LOG_BG,
            fg=COLOR_LOG_FG,
            insertbackground=COLOR_LOG_FG,
            relief=tk.FLAT,
            borderwidth=0,
            selectbackground="#264F78",
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.tag_configure("time", foreground=COLOR_LOG_TIME)
        self.log_text.tag_configure("cmd", foreground=COLOR_LOG_CMD)
        self.log_text.tag_configure("ok", foreground=COLOR_LOG_OK)
        self.log_text.tag_configure("err", foreground=COLOR_LOG_ERR)

    def create_connection_controls(self, parent):
        # No longer used — connection controls are inline in the toolbar.
        pass

    def create_install_panel(self):
        panel = ttk.LabelFrame(self.feature_host, text="安装 APK", padding=10)
        row = ttk.Frame(panel)
        row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(row, text="APK 文件:", width=10).pack(side=tk.LEFT)
        self.apk_combo = ttk.Combobox(row, textvariable=self.selected_apk, state="readonly")
        self.apk_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.install_btn = ttk.Button(
            panel,
            text="安装到当前设备",
            command=self.start_install_thread,
            style="Action.TButton"
        )
        self.install_btn.pack(fill=tk.X)
        self.feature_panels["install"] = panel

    def create_uninstall_panel(self):
        panel = ttk.LabelFrame(self.feature_host, text="卸载应用", padding=10)
        row = ttk.Frame(panel)
        row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(row, text="应用包名:", width=10).pack(side=tk.LEFT)
        self.uninstall_package_combo = ttk.Combobox(
            row,
            textvariable=self.selected_uninstall_package,
            state="readonly"
        )
        self.uninstall_package_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.uninstall_btn = ttk.Button(
            panel,
            text="从当前设备卸载",
            command=self.start_uninstall_thread,
            style="Action.TButton"
        )
        self.uninstall_btn.pack(fill=tk.X)
        self.feature_panels["uninstall"] = panel

    def create_push_panel(self):
        panel = ttk.LabelFrame(self.feature_host, text="推送文件到手机", padding=10)

        local_row = ttk.Frame(panel)
        local_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(local_row, text="本地文件:", width=10).pack(side=tk.LEFT)
        ttk.Entry(local_row, textvariable=self.push_local_path).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(local_row, text="浏览", command=self.select_local_file).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        remote_row = ttk.Frame(panel)
        remote_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(remote_row, text="手机路径:", width=10).pack(side=tk.LEFT)
        ttk.Entry(remote_row, textvariable=self.push_remote_path).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        ttk.Button(
            panel,
            text="推送到当前设备",
            command=self.start_push_thread,
            style="Action.TButton"
        ).pack(fill=tk.X)
        self.feature_panels["push"] = panel

    def create_pull_panel(self):
        panel = ttk.LabelFrame(self.feature_host, text="从手机拉取文件", padding=10)
        row = ttk.Frame(panel)
        row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(row, text="手机文件:", width=10).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.pull_remote_path).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Label(panel, text="文件将保存至本机 ReadByPhone 文件夹。", foreground="#6B7280").pack(
            anchor=tk.W, pady=(0, 8)
        )
        ttk.Button(
            panel,
            text="拉取到电脑",
            command=self.start_pull_thread,
            style="Action.TButton"
        ).pack(fill=tk.X)
        self.feature_panels["pull"] = panel

    def create_terminal_panel(self):
        # Common ADB commands: (display label, command args template)
        # {serial} is replaced at runtime; {args} is left for user to fill
        ADB_QUICK_CMDS = [
            ("查看设备列表",          "devices"),
            ("---", None),
            ("Shell 交互",            "shell"),
            ("查看 logcat",           "logcat -d"),
            ("清空 logcat",           "shell logcat -c"),
            ("---", None),
            ("列出所有应用",          "shell pm list packages"),
            ("列出第三方应用",        "shell pm list packages -3"),
            ("列出系统应用",          "shell pm list packages -s"),
            ("---", None),
            ("查看屏幕分辨率",        "shell wm size"),
            ("查看屏幕密度",          "shell wm density"),
            ("截图到 /sdcard/",       "shell screencap /sdcard/screen.png"),
            ("拉取截图",              "pull /sdcard/screen.png"),
            ("---", None),
            ("查看 CPU 信息",         "shell cat /proc/cpuinfo"),
            ("查看内存信息",          "shell cat /proc/meminfo"),
            ("查看电池状态",          "shell dumpsys battery"),
            ("查看网络信息",          "shell ifconfig"),
            ("---", None),
            ("重启设备",              "reboot"),
            ("重启到 Recovery",       "reboot recovery"),
            ("重启到 Bootloader",     "reboot bootloader"),
            ("---", None),
            ("开启无线调试 5555",     "tcpip 5555"),
            ("关闭无线调试",          "usb"),
        ]

        panel = ttk.LabelFrame(self.feature_host, text="ADB 终端", padding=10)

        # Left: quick command list
        left = ttk.Frame(panel, width=200)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        left.pack_propagate(False)

        ttk.Label(left, text="常用命令", foreground="#6B7280").pack(anchor=tk.W, pady=(0, 4))

        cmd_frame = ttk.Frame(left)
        cmd_frame.pack(fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(cmd_frame, orient=tk.VERTICAL)
        self.quick_cmd_listbox = tk.Listbox(
            cmd_frame,
            yscrollcommand=sb.set,
            font=("Consolas", 9),
            bg="#F9FAFB",
            relief=tk.FLAT,
            borderwidth=1,
            highlightthickness=1,
            highlightcolor="#D1D5DB",
            highlightbackground="#D1D5DB",
            activestyle="none",
        )
        sb.config(command=self.quick_cmd_listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.quick_cmd_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._quick_cmd_map = {}
        for label, args in ADB_QUICK_CMDS:
            if args is None:
                self.quick_cmd_listbox.insert(tk.END, "")
                self.quick_cmd_listbox.itemconfig(tk.END, fg="#D1D5DB", selectbackground="#F9FAFB", selectforeground="#D1D5DB")
            else:
                idx = self.quick_cmd_listbox.size()
                self.quick_cmd_listbox.insert(tk.END, "  " + label)
                self._quick_cmd_map[idx] = args

        self.quick_cmd_listbox.bind("<<ListboxSelect>>", self._on_quick_cmd_select)

        # Right: input + output hint
        right = ttk.Frame(panel)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(right, text="命令（adb 后的部分，自动附加 -s <设备>）", foreground="#6B7280").pack(anchor=tk.W, pady=(0, 4))

        input_row = ttk.Frame(right)
        input_row.pack(fill=tk.X)

        self.terminal_cmd_var = tk.StringVar()
        self.terminal_entry = ttk.Entry(input_row, textvariable=self.terminal_cmd_var, font=("Consolas", 10))
        self.terminal_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.terminal_entry.bind("<Return>", lambda e: self.run_terminal_command())

        ttk.Button(
            input_row, text="执行",
            style="Action.TButton",
            command=self.run_terminal_command
        ).pack(side=tk.LEFT)

        ttk.Label(right, text="结果输出在下方运行日志中", foreground="#9CA3AF").pack(anchor=tk.W, pady=(6, 0))

        self.feature_panels["terminal"] = panel

    def _on_quick_cmd_select(self, event=None):
        sel = self.quick_cmd_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        args = self._quick_cmd_map.get(idx)
        if args:
            self.terminal_cmd_var.set(args)
            self.terminal_entry.focus_set()
            self.terminal_entry.icursor(tk.END)

    def run_terminal_command(self):
        raw = self.terminal_cmd_var.get().strip()
        if not raw:
            return

        # Split args; prepend -s <serial> when a device is selected and command is not 'devices'
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
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
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
        panel = ttk.LabelFrame(self.feature_host, text="配置", padding=10)

        # Two-column layout
        left = ttk.LabelFrame(panel, text="卸载包名（精确匹配）", padding=8)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        right = ttk.LabelFrame(panel, text="包名前缀（前缀筛选）", padding=8)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.pkg_listbox = self._make_config_list(left)
        self.prefix_listbox = self._make_config_list(right)

        self._make_config_controls(
            left, self.pkg_listbox,
            UNINSTALL_PACKAGES_FILE,
            "pkg_entry"
        )
        self._make_config_controls(
            right, self.prefix_listbox,
            UNINSTALL_PREFIXES_FILE,
            "prefix_entry"
        )

        self.feature_panels["config"] = panel

    def _make_config_list(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True, pady=(0, 4))
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL)
        lb = tk.Listbox(
            frame,
            yscrollcommand=sb.set,
            selectmode=tk.EXTENDED,
            font=("Consolas", 9),
            height=5,
            bg="#F9FAFB",
            relief=tk.FLAT,
            borderwidth=1,
            highlightthickness=1,
            highlightcolor="#D1D5DB",
            highlightbackground="#D1D5DB",
        )
        sb.config(command=lb.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        return lb

    def _make_config_controls(self, parent, listbox, filepath, entry_attr):
        add_row = ttk.Frame(parent)
        add_row.pack(fill=tk.X, pady=(0, 4))
        entry = ttk.Entry(add_row)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        setattr(self, entry_attr, entry)
        ttk.Button(
            add_row, text="添加",
            command=lambda lb=listbox, e=entry: self._config_add(lb, e)
        ).pack(side=tk.LEFT)

        btn_row = ttk.Frame(parent)
        btn_row.pack(fill=tk.X)
        ttk.Button(
            btn_row, text="删除选中",
            command=lambda lb=listbox: self._config_delete(lb)
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            btn_row, text="保存",
            style="Action.TButton",
            command=lambda lb=listbox, p=filepath: self._config_save(lb, p)
        ).pack(side=tk.LEFT)

    def _config_add(self, listbox, entry):
        value = entry.get().strip()
        if not value:
            return
        existing = list(listbox.get(0, tk.END))
        if value not in existing:
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
            # Auto-detect tag from message content
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
        paths = glob.glob(os.path.join(APK_DIR, "*.apk"))
        return sorted(os.path.basename(path) for path in paths)

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

    def refresh_data(self):
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
            self.log("找到 {} 个 APK 文件。".format(len(apks)))
        else:
            self.apk_combo.set("")
            self.log("apk 文件夹中未找到 APK 文件。")

        self.refresh_uninstall_packages()

    def refresh_uninstall_packages(self):
        configured = load_package_names(UNINSTALL_PACKAGES_FILE)
        prefixes = load_package_names(UNINSTALL_PREFIXES_FILE)
        detected = self.get_installed_packages(prefixes)

        # Filter exact-name entries: only include those actually installed on device
        if configured and self.get_selected_serial():
            installed_set = self.get_all_installed_packages()
            confirmed_configured = [p for p in configured if p in installed_set]
        else:
            confirmed_configured = []

        packages = merge_package_names(confirmed_configured, detected)
        previous_package = self.selected_uninstall_package.get()
        self.uninstall_package_combo["values"] = packages

        if packages:
            if previous_package in packages:
                self.selected_uninstall_package.set(previous_package)
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

    def on_device_selected(self, event=None):
        self.log("已切换设备: " + self.selected_device.get())
        self.refresh_uninstall_packages()

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
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
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
                failed = any(
                    marker in failed_output
                    for marker in ("failed", "cannot", "unable")
                )
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
                self.root.after(
                    0, lambda: self.connect_btn.config(state="normal")
                )

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

    def run_adb_command(self, args, success_msg="操作成功", success_callback=None):
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
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
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

        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()

    def start_install_thread(self):
        apk = self.selected_apk.get()
        if not apk:
            messagebox.showwarning("提示", "请先选择一个 APK 文件。")
            return
        self.run_adb_command(
            ["install", "-r", os.path.join(APK_DIR, apk)],
            "安装完成。"
        )

    def start_uninstall_thread(self):
        package_name = self.selected_uninstall_package.get()
        if not package_name:
            messagebox.showwarning("提示", "请先选择一个要卸载的包名。")
            return
        self.run_adb_command(
            ["uninstall", package_name],
            "卸载完成。",
            self.refresh_data
        )

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

        self.run_adb_command(
            ["pull", remote, PULL_DIR],
            "文件拉取成功，保存至 " + PULL_DIR
        )


if __name__ == "__main__":
    root = tk.Tk()
    app = AdbInstallerApp(root)
    root.mainloop()
