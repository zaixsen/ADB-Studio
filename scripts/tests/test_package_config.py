# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from package_config import (
    load_package_names,
    merge_package_names,
    parse_adb_apk_paths,
    parse_adb_package_labels,
    parse_adb_package_list,
    parse_adb_packages,
)


class LoadPackageNamesTest(unittest.TestCase):
    def test_ignores_blank_lines_comments_and_duplicates(self):
        handle, path = tempfile.mkstemp()
        try:
            os.write(handle, b"\n# uninstall list\n com.example.first \n"
                             b"com.example.second\ncom.example.first\n")
            os.close(handle)
            handle = None

            self.assertEqual(
                ["com.example.first", "com.example.second"],
                load_package_names(path)
            )
        finally:
            if handle is not None:
                os.close(handle)
            os.remove(path)

    def test_missing_file_returns_empty_list(self):
        path = os.path.join(tempfile.gettempdir(), "missing-uninstall-packages.txt")
        if os.path.exists(path):
            os.remove(path)

        self.assertEqual([], load_package_names(path))

    def test_parses_only_packages_with_required_prefix(self):
        output = (b"package:com.coolfishgames.ironforce\r\n"
                  b"package:com.other.app\r\n"
                  b"package:com.coolfishgames.another\r\n")

        self.assertEqual(
            ["com.coolfishgames.ironforce", "com.coolfishgames.another"],
            parse_adb_package_list(output, ["com.coolfishgames"])
        )

    def test_parses_packages_matching_any_configured_prefix(self):
        output = (b"package:com.coolfishgames.ironforce\n"
                  b"package:com.example.tool\n"
                  b"package:org.unmatched.app\n")

        self.assertEqual(
            ["com.coolfishgames.ironforce", "com.example.tool"],
            parse_adb_package_list(output, ["com.coolfishgames", "com.example"])
        )

    def test_merges_package_names_without_duplicates(self):
        self.assertEqual(
            ["com.configured", "com.coolfishgames.game"],
            merge_package_names(
                ["com.configured", "com.coolfishgames.game"],
                ["com.coolfishgames.game"]
            )
        )

    def test_parses_sorts_and_deduplicates_package_output(self):
        output = (b"package:com.zeta\n"
                  b"unexpected output\n"
                  b" package:com.alpha \n"
                  b"package:com.zeta\n")

        self.assertEqual(
            ["com.alpha", "com.zeta"],
            parse_adb_packages(output)
        )

    def test_parses_base_and_split_apk_paths_in_device_order(self):
        output = (b"package:/data/app/com.example/base.apk\n"
                  b"package:/data/app/com.example/split_config.en.apk\n"
                  b"package:/data/app/com.example/base.apk\n"
                  b"noise\n")

        self.assertEqual(
            [
                "/data/app/com.example/base.apk",
                "/data/app/com.example/split_config.en.apk",
            ],
            parse_adb_apk_paths(output)
        )

    def test_apk_path_parser_ignores_non_apk_values(self):
        self.assertEqual(
            [],
            parse_adb_apk_paths(b"package:/data/app/com.example/not-an-apk\n")
        )


class ParseAdbPackageLabelsTest(unittest.TestCase):
    def test_parses_pipe_separated_package_label_pairs(self):
        output = (
            b"com.example.app|Example App\n"
            b"com.google.chrome|Google Chrome\n"
        )
        expected = {
            "com.example.app": "Example App",
            "com.google.chrome": "Google Chrome",
        }
        self.assertEqual(expected, parse_adb_package_labels(output))

    def test_ignores_lines_without_pipe(self):
        output = (
            b"com.example.app|Example App\n"
            b"garbage line without pipe\n"
            b"com.test.tool|Test Tool\n"
        )
        expected = {
            "com.example.app": "Example App",
            "com.test.tool": "Test Tool",
        }
        self.assertEqual(expected, parse_adb_package_labels(output))

    def test_skips_empty_labels(self):
        output = b"com.example.app|\ncom.test.tool|Valid\n"
        expected = {"com.test.tool": "Valid"}
        self.assertEqual(expected, parse_adb_package_labels(output))

    def test_handles_unicode_app_names(self):
        output = (
            b"com.tencent.mm|\xe5\xbe\xae\xe4\xbf\xa1\n"
            b"com.example.test|Test\n"
        )
        result = parse_adb_package_labels(output)
        self.assertIn("com.tencent.mm", result)
        self.assertIn("com.example.test", result)


if __name__ == "__main__":
    unittest.main()
