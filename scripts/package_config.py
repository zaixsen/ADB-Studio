# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import io
import os

try:
    text_type = unicode
except NameError:
    text_type = str


def load_package_names(path):
    if not os.path.isfile(path):
        return []

    packages = []
    seen = set()
    with io.open(path, "r", encoding="utf-8-sig") as config_file:
        for line in config_file:
            package_name = line.strip()
            if not package_name or package_name.startswith("#"):
                continue
            if package_name not in seen:
                seen.add(package_name)
                packages.append(package_name)
    return packages


def parse_adb_package_list(output, prefixes):
    if not prefixes:
        return []
    if not isinstance(output, text_type):
        output = output.decode("utf-8", "replace")

    packages = []
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("package:"):
            continue
        package_name = line[len("package:"):]
        if any(package_name.startswith(prefix) for prefix in prefixes):
            packages.append(package_name)
    return packages


def merge_package_names(*package_lists):
    merged = []
    seen = set()
    for package_list in package_lists:
        for package_name in package_list:
            if package_name not in seen:
                seen.add(package_name)
                merged.append(package_name)
    return merged


def save_package_names(path, names):
    with io.open(path, "w", encoding="utf-8") as f:
        for name in names:
            f.write(name + "\n")
