# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import shutil
import sys
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import main


def call_method(method, instance, *args):
    return getattr(method, "im_func", method)(instance, *args)


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


class FakeCombo(object):
    def __init__(self, selection):
        self.values = []
        self.selection = selection

    def __setitem__(self, key, value):
        if key == "values":
            self.values = value

    def current(self, index):
        self.selection.set(self.values[index])

    def set(self, value):
        self.selection.set(value)


class ImmediateRoot(object):
    def after(self, delay, callback):
        callback()


class FakeProcess(object):
    def __init__(self, returncode, stdout=b"", stderr=b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    def communicate(self):
        return self._stdout, self._stderr


def _setup_package_display_support(app, serial=None):
    """Add label/display-map attributes expected by the refactored UI methods."""
    app.get_selected_serial = lambda: serial
    app._package_labels = {}
    app._package_display_map = {}
    app._fetch_package_labels = lambda device, pkgs: {}
    app._build_package_display_list = (
        lambda pkgs: main.AdbInstallerApp._build_package_display_list(app, pkgs)
    )
    app._find_previous_display = (
        lambda dl, dm, pd: main.AdbInstallerApp._find_previous_display(
            app, dl, dm, pd
        )
    )
    app._get_selected_package = (
        lambda dt: main.AdbInstallerApp._get_selected_package(app, dt)
    )


class FakeApp(object):
    pass


class ExportAppWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.target_dir = tempfile.mkdtemp(prefix="adb-export-test-")
        self.original_popen = main.subprocess.Popen
        self.original_makedirs = main.os.makedirs

    def tearDown(self):
        main.subprocess.Popen = self.original_popen
        main.os.makedirs = self.original_makedirs
        shutil.rmtree(self.target_dir, ignore_errors=True)

    def make_app(self):
        app = FakeApp()
        app.root = ImmediateRoot()
        app.export_btn = FakeButton()
        app.export_btn.state = "disabled"
        app.messages = []
        app.log = lambda message, tag=None: app.messages.append((message, tag))
        app.create_startupinfo = lambda: None
        return app

    def test_exports_base_and_split_apks_to_package_folder(self):
        app = self.make_app()
        commands = []
        responses = [
            FakeProcess(
                0,
                b"package:/data/app/com.example/base.apk\n"
                b"package:/data/app/com.example/split_config.en.apk\n",
            ),
            FakeProcess(0, b"1 file pulled"),
            FakeProcess(0, b"1 file pulled"),
        ]

        def fake_popen(command, **kwargs):
            commands.append(command)
            return responses.pop(0)

        main.subprocess.Popen = fake_popen

        call_method(
            main.AdbInstallerApp._export_app,
            app,
            "device-123",
            "com.example",
            self.target_dir,
        )

        package_dir = os.path.join(self.target_dir, "com.example")
        self.assertEqual(
            [
                ["adb", "-s", "device-123", "shell", "pm", "path", "com.example"],
                [
                    "adb", "-s", "device-123", "pull",
                    "/data/app/com.example/base.apk",
                    os.path.join(package_dir, "base.apk"),
                ],
                [
                    "adb", "-s", "device-123", "pull",
                    "/data/app/com.example/split_config.en.apk",
                    os.path.join(package_dir, "split_config.en.apk"),
                ],
            ],
            commands,
        )
        self.assertTrue(os.path.isdir(package_dir))
        self.assertEqual("normal", app.export_btn.state)
        self.assertTrue(any("导出完成" in message for message, tag in app.messages))

    def test_reports_partial_failure_and_continues_remaining_pulls(self):
        app = self.make_app()
        commands = []
        responses = [
            FakeProcess(
                0,
                b"package:/data/app/com.example/base.apk\n"
                b"package:/data/app/com.example/split_config.en.apk\n",
            ),
            FakeProcess(1, stderr=b"permission denied"),
            FakeProcess(0, b"1 file pulled"),
        ]

        def fake_popen(command, **kwargs):
            commands.append(command)
            return responses.pop(0)

        main.subprocess.Popen = fake_popen

        call_method(
            main.AdbInstallerApp._export_app,
            app,
            "device-123",
            "com.example",
            self.target_dir,
        )

        self.assertEqual(3, len(commands))
        self.assertEqual("normal", app.export_btn.state)
        self.assertTrue(any("部分失败" in message for message, tag in app.messages))

    def test_empty_pm_path_output_fails_without_creating_package_folder(self):
        app = self.make_app()
        main.subprocess.Popen = lambda command, **kwargs: FakeProcess(0, b"")

        call_method(
            main.AdbInstallerApp._export_app,
            app,
            "device-123",
            "com.example",
            self.target_dir,
        )

        self.assertFalse(os.path.exists(os.path.join(self.target_dir, "com.example")))
        self.assertEqual("normal", app.export_btn.state)
        self.assertTrue(any("未找到 APK" in message for message, tag in app.messages))

    def test_directory_creation_error_is_reported_accurately(self):
        app = self.make_app()
        main.subprocess.Popen = lambda command, **kwargs: FakeProcess(
            0, b"package:/data/app/com.example/base.apk\n"
        )

        def fail_makedirs(path):
            raise OSError("access denied")

        main.os.makedirs = fail_makedirs

        call_method(
            main.AdbInstallerApp._export_app,
            app,
            "device-123",
            "com.example",
            self.target_dir,
        )

        self.assertEqual("normal", app.export_btn.state)
        self.assertTrue(any("创建导出目录失败" in message for message, tag in app.messages))


class ExportPackageDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.original_check_output = main.subprocess.check_output

    def tearDown(self):
        main.subprocess.check_output = self.original_check_output

    def test_queries_only_third_party_packages(self):
        app = FakeApp()
        app.get_selected_serial = lambda: "device-123"
        app.create_startupinfo = lambda: None
        app.messages = []
        app.log = lambda message, tag=None: app.messages.append((message, tag))
        commands = []

        def fake_check_output(command, **kwargs):
            commands.append(command)
            return (b"package:com.zeta\n"
                    b"package:com.alpha\n"
                    b"package:com.zeta\n")

        main.subprocess.check_output = fake_check_output

        packages = call_method(main.AdbInstallerApp.get_export_packages, app)

        self.assertEqual(["com.alpha", "com.zeta"], packages)
        self.assertEqual(
            [["adb", "-s", "device-123", "shell", "pm", "list", "packages", "-3"]],
            commands,
        )

    def test_refresh_preserves_available_selection(self):
        app = FakeApp()
        app.selected_export_package = ValueHolder("com.zeta")
        app.export_package_combo = FakeCombo(app.selected_export_package)
        app.get_export_packages = lambda: ["com.alpha", "com.zeta"]
        _setup_package_display_support(app)
        app.messages = []
        app.log = lambda message, tag=None: app.messages.append((message, tag))

        call_method(main.AdbInstallerApp.refresh_export_packages, app)

        self.assertEqual(["com.alpha", "com.zeta"], app.export_package_combo.values)
        self.assertEqual("com.zeta", app.selected_export_package.get())

    def test_refresh_clears_stale_selection_when_no_packages_exist(self):
        app = FakeApp()
        app.selected_export_package = ValueHolder("com.stale")
        app.export_package_combo = FakeCombo(app.selected_export_package)
        app.get_export_packages = lambda: []
        _setup_package_display_support(app)
        app.messages = []
        app.log = lambda message, tag=None: app.messages.append((message, tag))

        call_method(main.AdbInstallerApp.refresh_export_packages, app)

        self.assertEqual([], app.export_package_combo.values)
        self.assertEqual("", app.selected_export_package.get())


class ExportAppActionTest(unittest.TestCase):
    def setUp(self):
        self.original_askdirectory = main.filedialog.askdirectory
        self.original_showwarning = main.messagebox.showwarning
        self.original_thread = main.threading.Thread

    def tearDown(self):
        main.filedialog.askdirectory = self.original_askdirectory
        main.messagebox.showwarning = self.original_showwarning
        main.threading.Thread = self.original_thread

    def test_select_directory_updates_target(self):
        app = FakeApp()
        app.export_target_dir = ValueHolder()
        main.filedialog.askdirectory = lambda: "C:/exports"

        call_method(main.AdbInstallerApp.select_export_directory, app)

        self.assertEqual("C:/exports", app.export_target_dir.get())

    def test_valid_selection_starts_background_export(self):
        app = FakeApp()
        app.get_selected_serial = lambda: "device-123"
        app.selected_export_package = ValueHolder("com.example")
        app.export_target_dir = ValueHolder(self.make_existing_dir())
        app.export_btn = FakeButton()
        app._export_app = lambda *args: None
        app._package_display_map = {}
        app._get_selected_package = (
            lambda dt: main.AdbInstallerApp._get_selected_package(app, dt)
        )
        created_threads = []

        class FakeThread(object):
            def __init__(self, target, args):
                self.target = target
                self.args = args
                self.daemon = False
                self.started = False
                created_threads.append(self)

            def start(self):
                self.started = True

        main.threading.Thread = FakeThread
        try:
            call_method(main.AdbInstallerApp.start_export_thread, app)
        finally:
            shutil.rmtree(app.export_target_dir.get(), ignore_errors=True)

        self.assertEqual("disabled", app.export_btn.state)
        self.assertEqual(1, len(created_threads))
        self.assertTrue(created_threads[0].daemon)
        self.assertTrue(created_threads[0].started)
        self.assertEqual(
            ("device-123", "com.example", app.export_target_dir.get()),
            created_threads[0].args,
        )

    def test_invalid_target_folder_shows_warning_without_starting_thread(self):
        app = FakeApp()
        app.get_selected_serial = lambda: "device-123"
        app.selected_export_package = ValueHolder("com.example")
        app.export_target_dir = ValueHolder(os.path.join(self.make_existing_dir(), "missing"))
        app.export_btn = FakeButton()
        app._package_display_map = {}
        app._get_selected_package = (
            lambda dt: main.AdbInstallerApp._get_selected_package(app, dt)
        )
        warnings = []
        main.messagebox.showwarning = lambda title, message: warnings.append(message)
        main.threading.Thread = lambda **kwargs: self.fail("thread should not start")
        parent_dir = os.path.dirname(app.export_target_dir.get())
        try:
            call_method(main.AdbInstallerApp.start_export_thread, app)
        finally:
            shutil.rmtree(parent_dir, ignore_errors=True)

        self.assertEqual("normal", app.export_btn.state)
        self.assertEqual(1, len(warnings))
        self.assertTrue("目标文件夹" in warnings[0])

    @staticmethod
    def make_existing_dir():
        return tempfile.mkdtemp(prefix="adb-export-action-")


class FetchPackageLabelsTest(unittest.TestCase):
    """Test APK-based label extraction (pm path + pull + parse)."""

    def setUp(self):
        self.original_check_output = main.subprocess.check_output
        self.original_check_call = main.subprocess.check_call
        self.original_extract = main.extract_apk_label

    def tearDown(self):
        main.subprocess.check_output = self.original_check_output
        main.subprocess.check_call = self.original_check_call
        main.extract_apk_label = self.original_extract

    def _make_app(self, labels_by_pkg):
        """Create a fake app that returns the given labels when pulling APKs.

        `labels_by_pkg` maps package name -> label string (or None to skip).
        """
        app = FakeApp()
        app._package_labels = {}
        app.create_startupinfo = lambda: None

        called_pkgs = []

        def fake_check_output(command, **kwargs):
            called_pkgs.append(command)
            pkg = command[-1]
            return ("package:/data/app/~~fake==/{}/base.apk".format(pkg)).encode()

        def fake_check_call(command, **kwargs):
            return 0  # success

        def fake_extract(apk_path):
            for pkg, label in labels_by_pkg.items():
                if pkg in apk_path:
                    return label
            return None

        main.subprocess.check_output = fake_check_output
        main.subprocess.check_call = fake_check_call
        main.extract_apk_label = fake_extract
        app._called_pkgs = called_pkgs
        return app

    def test_fetches_labels_for_missing_packages(self):
        app = self._make_app({
            "com.example.app": "Example App",
            "com.other.tool": "Awesome Tool",
        })
        labels = call_method(
            main.AdbInstallerApp._fetch_package_labels,
            app,
            "device-1",
            ["com.example.app", "com.other.tool"],
        )
        self.assertEqual(
            {"com.example.app": "Example App", "com.other.tool": "Awesome Tool"},
            labels,
        )

    def test_skips_packages_already_in_cache(self):
        app = self._make_app({
            "com.new.app": "New App",
        })
        app._package_labels = {"com.cached.app": "Cached"}
        labels = call_method(
            main.AdbInstallerApp._fetch_package_labels,
            app,
            "device-1",
            ["com.cached.app", "com.new.app"],
        )
        # Only the new one should be fetched
        self.assertEqual(
            {"com.cached.app": "Cached", "com.new.app": "New App"},
            labels,
        )

    def test_updates_instance_cache(self):
        app = self._make_app({"com.cached.app": "Cached"})
        app._package_labels = {"existing": "Existing"}
        call_method(
            main.AdbInstallerApp._fetch_package_labels,
            app,
            "device-1",
            ["com.cached.app"],
        )
        self.assertIn("com.cached.app", app._package_labels)
        self.assertIn("existing", app._package_labels)

    def test_empty_when_no_packages_requested(self):
        app = FakeApp()
        app._package_labels = {}
        app.create_startupinfo = lambda: None
        labels = call_method(
            main.AdbInstallerApp._fetch_package_labels,
            app,
            "device-1",
            [],
        )
        self.assertEqual({}, labels)


if __name__ == "__main__":
    unittest.main()
