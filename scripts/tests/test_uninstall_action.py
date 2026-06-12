# -*- coding: utf-8 -*-
import os
import sys
import unittest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import main


class ValueHolder(object):
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class FakeApp(object):
    def __init__(self, package_name):
        self.selected_uninstall_package = ValueHolder(package_name)
        self.command = None
        self.success_message = None
        self.success_callback = None

    def run_adb_command(self, args, success_message, success_callback=None):
        self.command = args
        self.success_message = success_message
        self.success_callback = success_callback

    def refresh_data(self):
        pass


class UninstallActionTest(unittest.TestCase):
    def test_dispatches_selected_package_to_adb_uninstall(self):
        app = FakeApp("com.example.game")

        main.AdbInstallerApp.start_uninstall_thread.im_func(app)

        self.assertEqual(["uninstall", "com.example.game"], app.command)
        self.assertEqual(app.refresh_data, app.success_callback)

    def test_queries_all_device_packages_and_filters_configured_prefixes(self):
        class DetectionApp(object):
            def get_selected_serial(self):
                return "device-123"

            def create_startupinfo(self):
                return None

            def log(self, message):
                pass

        calls = []
        original_check_output = main.subprocess.check_output

        def fake_check_output(command, startupinfo=None):
            calls.append(command)
            return (b"package:com.coolfishgames.ironforce\n"
                    b"package:com.example.tool\n"
                    b"package:org.other.app\n")

        main.subprocess.check_output = fake_check_output
        try:
            packages = main.AdbInstallerApp.get_installed_packages.im_func(
                DetectionApp(), ["com.coolfishgames", "com.example"]
            )
        finally:
            main.subprocess.check_output = original_check_output

        self.assertEqual(
            ['adb', '-s', 'device-123', 'shell', 'pm', 'list', 'packages'],
            calls[0]
        )
        self.assertEqual(
            ["com.coolfishgames.ironforce", "com.example.tool"],
            packages
        )


if __name__ == "__main__":
    unittest.main()
