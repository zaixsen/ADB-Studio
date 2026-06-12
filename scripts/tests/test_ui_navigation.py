# -*- coding: utf-8 -*-
import os
import sys
import unittest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import main


class FakePanel(object):
    def __init__(self):
        self.visible = False

    def pack_forget(self):
        self.visible = False

    def pack(self, **kwargs):
        self.visible = True


class FakeButton(object):
    def __init__(self):
        self.style = None

    def config(self, **kwargs):
        self.style = kwargs.get("style")


class FakeApp(object):
    pass


class FeatureNavigationTest(unittest.TestCase):
    def test_show_feature_displays_only_selected_panel(self):
        app = FakeApp()
        app.feature_panels = {
            "install": FakePanel(),
            "uninstall": FakePanel(),
            "push": FakePanel()
        }
        app.feature_buttons = dict((name, FakeButton()) for name in app.feature_panels)

        main.AdbInstallerApp.show_feature.im_func(app, "uninstall")

        self.assertFalse(app.feature_panels["install"].visible)
        self.assertTrue(app.feature_panels["uninstall"].visible)
        self.assertFalse(app.feature_panels["push"].visible)

    def test_show_feature_highlights_selected_button(self):
        app = FakeApp()
        app.feature_panels = {"install": FakePanel(), "pull": FakePanel()}
        app.feature_buttons = {"install": FakeButton(), "pull": FakeButton()}

        main.AdbInstallerApp.show_feature.im_func(app, "pull")

        self.assertEqual("Nav.TButton", app.feature_buttons["install"].style)
        self.assertEqual("ActiveNav.TButton", app.feature_buttons["pull"].style)


if __name__ == "__main__":
    unittest.main()
