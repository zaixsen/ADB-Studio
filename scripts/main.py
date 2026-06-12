# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import glob
import os
import re
import subprocess
import sys
import threading

from package_config import load_package_names, merge_package_names, parse_adb_package_list

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
APK_DIR = os.path.join(PROJECT_DIR, "apk")
PULL_DIR = os.path.join(PROJECT_DIR, "ReadByPhone")
UNINSTALL_PACKAGES_FILE = os.path.join(PROJECT_DIR, "uninstall_packages.txt")
UNINSTALL_PREFIXES_FILE = os.path.join(PROJECT_DIR, "uninstall_package_prefixes.txt")

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


class AdbInstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ADB 设备工具")
        self.root.geometry("760x720")
        self.root.minsize(680, 600)

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

        style.configure("TButton", padding=(10, 7))
        style.configure("TLabel", padding=4)
        style.configure("Toolbar.TFrame", padding=10)
        style.configure("Nav.TButton", padding=(12, 9))
        style.configure("ActiveNav.TButton", padding=(12, 9), font=("TkDefaultFont", 9, "bold"))
        style.configure("Action.TButton", padding=(12, 9), font=("TkDefaultFont", 10, "bold"))
        style.map(
            "ActiveNav.TButton",
            background=[("!disabled", "#2f6fed")],
            foreground=[("!disabled", "white")]
        )

    def create_widgets(self):
        toolbar = ttk.Frame(self.root, style="Toolbar.TFrame")
        toolbar.pack(fill=tk.X)

        ttk.Label(toolbar, text="当前设备:").pack(side=tk.LEFT)
        self.device_combo = ttk.Combobox(
            toolbar,
            textvariable=self.selected_device,
            state="readonly",
            width=34
        )
        self.device_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 10))
        self.device_combo.bind("<<ComboboxSelected>>", self.on_device_selected)

        ttk.Button(toolbar, text="刷新", command=self.refresh_data).pack(side=tk.LEFT, padx=(0, 6))
        self.restart_btn = ttk.Button(toolbar, text="重启 ADB", command=self.restart_adb)
        self.restart_btn.pack(side=tk.LEFT)

        network_toolbar = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        network_toolbar.pack(fill=tk.X)
        self.create_connection_controls(network_toolbar)

        nav_frame = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        nav_frame.pack(fill=tk.X)
        nav_items = [
            ("install", "安装 APK"),
            ("uninstall", "卸载应用"),
            ("push", "推送文件"),
            ("pull", "拉取文件")
        ]
        for feature_name, label in nav_items:
            button = ttk.Button(
                nav_frame,
                text=label,
                style="Nav.TButton",
                command=lambda name=feature_name: self.show_feature(name)
            )
            button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)
            self.feature_buttons[feature_name] = button

        self.feature_host = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        self.feature_host.pack(fill=tk.X)
        self.create_install_panel()
        self.create_uninstall_panel()
        self.create_push_panel()
        self.create_pull_panel()

        log_frame = ttk.LabelFrame(self.root, text="运行日志", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(log_toolbar, text="ADB 命令和操作结果").pack(side=tk.LEFT)
        ttk.Button(log_toolbar, text="清空日志", command=self.clear_log).pack(side=tk.RIGHT)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=20,
            state="disabled",
            font=("Consolas", 10),
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def create_connection_controls(self, parent):
        ttk.Label(parent, text="IP 地址:").pack(side=tk.LEFT)
        ttk.Entry(parent, textvariable=self.network_address).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8)
        )
        self.connect_btn = ttk.Button(
            parent,
            text="连接 IP",
            command=self.start_connect_thread
        )
        self.connect_btn.pack(side=tk.LEFT)

    def create_install_panel(self):
        panel = ttk.LabelFrame(self.feature_host, text="安装 APK", padding=12)
        row = ttk.Frame(panel)
        row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(row, text="APK 文件:", width=11).pack(side=tk.LEFT)
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
        panel = ttk.LabelFrame(self.feature_host, text="卸载应用", padding=12)
        row = ttk.Frame(panel)
        row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(row, text="应用包名:", width=11).pack(side=tk.LEFT)
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
        panel = ttk.LabelFrame(self.feature_host, text="推送文件到手机", padding=12)

        local_row = ttk.Frame(panel)
        local_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(local_row, text="本地文件:", width=11).pack(side=tk.LEFT)
        ttk.Entry(local_row, textvariable=self.push_local_path).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(local_row, text="选择文件", command=self.select_local_file).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        remote_row = ttk.Frame(panel)
        remote_row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(remote_row, text="手机路径:", width=11).pack(side=tk.LEFT)
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
        panel = ttk.LabelFrame(self.feature_host, text="从手机拉取文件", padding=12)
        row = ttk.Frame(panel)
        row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(row, text="手机文件:", width=11).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.pull_remote_path).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Label(panel, text="文件将保存到主目录的 ReadByPhone 文件夹。").pack(
            anchor=tk.W, pady=(0, 10)
        )
        ttk.Button(
            panel,
            text="拉取到电脑",
            command=self.start_pull_thread,
            style="Action.TButton"
        ).pack(fill=tk.X)
        self.feature_panels["pull"] = panel

    def show_feature(self, feature_name):
        if feature_name not in self.feature_panels:
            return
        for name, panel in self.feature_panels.items():
            panel.pack_forget()
            self.feature_buttons[name].config(
                style="ActiveNav.TButton" if name == feature_name else "Nav.TButton"
            )
        self.feature_panels[feature_name].pack(fill=tk.X)

    def clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state="disabled")

    def log(self, message):
        message = to_text(message)
        self.log_text.config(state="normal")
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
        packages = merge_package_names(configured, detected)
        previous_package = self.selected_uninstall_package.get()
        self.uninstall_package_combo["values"] = packages

        if packages:
            if previous_package in packages:
                self.selected_uninstall_package.set(previous_package)
            else:
                self.uninstall_package_combo.current(0)
            self.log(
                "卸载列表显示 {} 个包名，其中当前设备匹配 {} 个。".format(
                    len(packages), len(detected)
                )
            )
        else:
            self.uninstall_package_combo.set("")
            if not prefixes:
                self.log("前缀清单 uninstall_package_prefixes.txt 中没有有效前缀。")
            else:
                self.log("当前设备和卸载清单中均未找到匹配包名。")

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
