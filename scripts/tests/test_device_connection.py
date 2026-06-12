# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import sys
import unittest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import main
from main import normalize_network_address


class ValueHolder(object):
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeButton(object):
    def __init__(self):
        self.state = "normal"

    def config(self, **kwargs):
        self.state = kwargs.get("state", self.state)


class ImmediateRoot(object):
    def after(self, delay, callback):
        callback()


class ImmediateThread(object):
    def __init__(self, target):
        self.target = target
        self.daemon = False

    def start(self):
        self.target()


class FakeProcess(object):
    def __init__(self, returncode=0, stdout=b"connected\n", stderr=b""):
        self.returncode = returncode
        self.stdout_value = stdout
        self.stderr_value = stderr

    def communicate(self):
        return self.stdout_value, self.stderr_value


class FakeCombo(object):
    def __init__(self, variable):
        self.variable = variable
        self.values = []

    def __setitem__(self, key, value):
        if key == "values":
            self.values = value

    def current(self, index):
        self.variable.set(self.values[index])

    def set(self, value):
        self.variable.set(value)


class FakeWidget(object):
    def __init__(self, parent, **kwargs):
        self.parent = parent
        self.kwargs = kwargs
        self.pack_kwargs = None

    def pack(self, **kwargs):
        self.pack_kwargs = kwargs


class NormalizeNetworkAddressTest(unittest.TestCase):
    def test_defaults_to_port_5555(self):
        self.assertEqual(
            "192.168.1.20:5555",
            normalize_network_address("192.168.1.20")
        )

    def test_preserves_explicit_port(self):
        self.assertEqual(
            "192.168.1.20:4444",
            normalize_network_address(" 192.168.1.20:4444 ")
        )

    def test_rejects_invalid_addresses(self):
        invalid_values = [
            "",
            "192.168.1",
            "192.168.1.256",
            "192.168.one.20",
            "192.168.1.20:5555:1",
            "192.168.1.20:0",
            "192.168.1.20:65536",
            "192.168.1.20:port"
        ]
        for value in invalid_values:
            with self.assertRaises(ValueError):
                normalize_network_address(value)


class DeviceConnectionActionTest(unittest.TestCase):
    def test_connects_normalized_address_and_refreshes_devices(self):
        class FakeApp(object):
            def __init__(self):
                self.network_address = ValueHolder("192.168.1.20")
                self.connect_btn = FakeButton()
                self.root = ImmediateRoot()
                self.preferred_device_serial = None
                self.messages = []
                self.refresh_count = 0

            def create_startupinfo(self):
                return None

            def log(self, message):
                self.messages.append(message)

            def refresh_data(self):
                self.refresh_count += 1

        app = FakeApp()
        calls = []
        original_thread = main.threading.Thread
        original_popen = main.subprocess.Popen

        def fake_popen(command, **kwargs):
            calls.append(command)
            return FakeProcess()

        main.threading.Thread = ImmediateThread
        main.subprocess.Popen = fake_popen
        try:
            main.AdbInstallerApp.start_connect_thread.im_func(app)
        finally:
            main.threading.Thread = original_thread
            main.subprocess.Popen = original_popen

        self.assertEqual(
            [["adb", "connect", "192.168.1.20:5555"]],
            calls
        )
        self.assertEqual("192.168.1.20:5555", app.preferred_device_serial)
        self.assertEqual(1, app.refresh_count)
        self.assertEqual("normal", app.connect_btn.state)

    def test_refresh_selects_preferred_network_device(self):
        class FakeApp(object):
            def __init__(self):
                self.selected_device = ValueHolder("USB Device (ABC123)")
                self.selected_apk = ValueHolder("")
                self.preferred_device_serial = "192.168.1.20:5555"
                self.device_combo = FakeCombo(self.selected_device)
                self.apk_combo = FakeCombo(self.selected_apk)
                self.messages = []

            def log(self, message):
                self.messages.append(message)

            def get_devices(self):
                return [
                    "USB Device (ABC123)",
                    "Network Device (192.168.1.20:5555)"
                ]

            def get_apks(self):
                return []

            def refresh_uninstall_packages(self):
                pass

        app = FakeApp()

        main.AdbInstallerApp.refresh_data.im_func(app)

        self.assertEqual(
            "Network Device (192.168.1.20:5555)",
            app.selected_device.get()
        )
        self.assertIsNone(app.preferred_device_serial)

    def test_selecting_detected_device_does_not_run_adb_connect(self):
        class FakeApp(object):
            def __init__(self):
                self.selected_device = ValueHolder("USB Device (ABC123)")
                self.messages = []
                self.refresh_count = 0

            def log(self, message):
                self.messages.append(message)

            def refresh_uninstall_packages(self):
                self.refresh_count += 1

        app = FakeApp()
        calls = []
        original_popen = main.subprocess.Popen

        def fake_popen(command, **kwargs):
            calls.append(command)
            return FakeProcess()

        main.subprocess.Popen = fake_popen
        try:
            main.AdbInstallerApp.on_device_selected.im_func(app)
        finally:
            main.subprocess.Popen = original_popen

        self.assertEqual([], calls)
        self.assertEqual(1, app.refresh_count)


class DeviceConnectionControlsTest(unittest.TestCase):
    def test_creates_ip_entry_and_connect_button(self):
        class FakeApp(object):
            def __init__(self):
                self.network_address = ValueHolder("")

            def start_connect_thread(self):
                pass

        app = FakeApp()
        created_entries = []
        created_buttons = []
        original_label = main.ttk.Label
        original_entry = main.ttk.Entry
        original_button = main.ttk.Button

        def fake_entry(parent, **kwargs):
            widget = FakeWidget(parent, **kwargs)
            created_entries.append(widget)
            return widget

        def fake_button(parent, **kwargs):
            widget = FakeWidget(parent, **kwargs)
            created_buttons.append(widget)
            return widget

        main.ttk.Label = FakeWidget
        main.ttk.Entry = fake_entry
        main.ttk.Button = fake_button
        try:
            main.AdbInstallerApp.create_connection_controls.im_func(
                app, "network-toolbar"
            )
        finally:
            main.ttk.Label = original_label
            main.ttk.Entry = original_entry
            main.ttk.Button = original_button

        self.assertIs(app.network_address, created_entries[0].kwargs["textvariable"])
        self.assertEqual("连接 IP", created_buttons[0].kwargs["text"])
        self.assertEqual(app.start_connect_thread, created_buttons[0].kwargs["command"])
        self.assertIs(app.connect_btn, created_buttons[0])


if __name__ == "__main__":
    unittest.main()
