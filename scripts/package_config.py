# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import io
import os
import struct
import zipfile

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


def _parse_package_values(output):
    if not isinstance(output, text_type):
        output = output.decode("utf-8", "replace")

    values = []
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("package:"):
            continue
        value = line[len("package:"):].strip()
        if value:
            values.append(value)
    return values


def parse_adb_packages(output):
    return sorted(set(_parse_package_values(output)))


def parse_adb_apk_paths(output):
    paths = []
    for value in _parse_package_values(output):
        if value.lower().endswith(".apk") and value not in paths:
            paths.append(value)
    return paths


def merge_package_names(*package_lists):
    merged = []
    seen = set()
    for package_list in package_lists:
        for package_name in package_list:
            if package_name not in seen:
                seen.add(package_name)
                merged.append(package_name)
    return merged


def parse_adb_package_labels(output):
    """Parse batch label-fetching command output.

    Expected format per line: package_name|app_label
    Returns dict mapping package_name -> app_label.
    """
    if not isinstance(output, text_type):
        output = output.decode("utf-8", "replace")

    labels = {}
    for line in output.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = line.split("|", 1)
        pkg = parts[0].strip()
        label = parts[1].strip()
        if pkg and label:
            labels[pkg] = label
    return labels


# ── Binary XML (AXML) chunk type constants ─────────────────────────────────────
_AXML_STRING_POOL = 0x0001
_AXML_RESOURCE_MAP = 0x0180
_AXML_START_NAMESPACE = 0x0100
_AXML_END_NAMESPACE = 0x0101
_AXML_START_ELEMENT = 0x0102
_AXML_END_ELEMENT = 0x0103

# Res_value type constants
_AXML_TYPE_REFERENCE = 0x01
_AXML_TYPE_STRING = 0x03


def _axml_string_pool(data, offset):
    """Parse a binary XML string-pool chunk.

    Returns (list_of_strings, next_chunk_offset).
    """
    chunk_hdr = struct.unpack_from("<H", data, offset + 2)[0]
    chunk_size = struct.unpack_from("<I", data, offset + 4)[0]
    string_count = struct.unpack_from("<I", data, offset + 8)[0]
    flags = struct.unpack_from("<I", data, offset + 16)[0]
    strings_start = struct.unpack_from("<I", data, offset + 20)[0]

    is_utf8 = bool(flags & (1 << 8))

    off = offset + chunk_hdr
    string_offsets = [
        struct.unpack_from("<I", data, off + i * 4)[0]
        for i in range(string_count)
    ]

    str_base = offset + strings_start
    strings = []
    for str_off in string_offsets:
        pos = str_base + str_off
        try:
            if is_utf8:
                # UTF-8: byte-len (uint8) + byte-len (uint8), then data
                byte_len = struct.unpack_from("<B", data, pos + 1)[0]
                pos += 2
                s = data[pos:pos + byte_len].decode("utf-8", "replace")
            else:
                # UTF-16: char-len (uint16), then data
                char_len = struct.unpack_from("<H", data, pos)[0]
                pos += 2
                raw = data[pos:pos + char_len * 2]
                s = raw.decode("utf-16-le", "replace").rstrip("\0")
        except (UnicodeDecodeError, struct.error):
            s = ""
        strings.append(s)

    return strings, offset + chunk_size


def _parse_manifest_label(manifest_data):
    """Parse AndroidManifest.xml binary data and return (label_str, label_res_id).

    - label_str: direct string label if found in string pool, else None.
    - label_res_id: resource ID (int) if label is a reference, else None.
    """
    if len(manifest_data) < 8:
        return None, None

    # Skip XML file header chunk
    xml_hdr = struct.unpack_from("<H", manifest_data, 2)[0]
    sp_pos = xml_hdr

    # Parse the string pool
    sp_type = struct.unpack_from("<H", manifest_data, sp_pos)[0]
    if sp_type != _AXML_STRING_POOL:
        return None, None

    strings, pos = _axml_string_pool(manifest_data, sp_pos)
    ns_android = -1

    app_label_str = None
    app_label_ref = None

    while pos < len(manifest_data):
        chunk_type = struct.unpack_from("<H", manifest_data, pos)[0]
        chunk_hdr = struct.unpack_from("<H", manifest_data, pos + 2)[0]
        chunk_size = struct.unpack_from("<I", manifest_data, pos + 4)[0]

        if chunk_size == 0:
            break

        if chunk_type == _AXML_RESOURCE_MAP:
            pos += chunk_size
            continue

        if chunk_type == _AXML_START_NAMESPACE:
            node = pos + chunk_hdr
            uri = struct.unpack_from("<I", manifest_data, node + 4)[0]
            uri_str = strings[uri] if uri < len(strings) else ""
            if "schemas.android.com/apk/res/android" in uri_str:
                ns_android = uri
            pos += chunk_size
            continue

        if chunk_type in (_AXML_END_NAMESPACE, _AXML_END_ELEMENT):
            pos += chunk_size
            continue

        if chunk_type == _AXML_START_ELEMENT:
            node = pos + chunk_hdr  # start of attrExt
            name_idx = struct.unpack_from("<I", manifest_data, node + 4)[0]
            attr_count = struct.unpack_from("<H", manifest_data, node + 12)[0]

            tag_name = strings[name_idx] if name_idx < len(strings) else ""

            if tag_name not in ("manifest", "application", "activity"):
                pos += chunk_size
                continue

            attr_start = struct.unpack_from("<H", manifest_data, node + 8)[0]
            # attr_size is at node + 10, always 20 bytes per attribute
            for a in range(attr_count):
                aoff = node + attr_start + a * 20
                a_ns = struct.unpack_from("<I", manifest_data, aoff)[0]
                a_name = struct.unpack_from("<I", manifest_data, aoff + 4)[0]
                tv_type = manifest_data[aoff + 15]
                tv_data = struct.unpack_from("<I", manifest_data, aoff + 16)[0]

                attr_str = strings[a_name] if a_name < len(strings) else ""

                if attr_str != "label":
                    continue

                if tv_type == _AXML_TYPE_STRING:
                    val = strings[tv_data] if tv_data < len(strings) else ""
                    if tag_name == "application" and app_label_str is None:
                        app_label_str = val
                    elif app_label_str is None:
                        # fallback label from manifest or activity
                        app_label_str = val
                elif tv_type == _AXML_TYPE_REFERENCE:
                    if tag_name == "application" and app_label_ref is None:
                        app_label_ref = tv_data
                    elif app_label_ref is None:
                        app_label_ref = tv_data

            pos += chunk_size
            continue

        # Unknown chunk — stop
        break

    return app_label_str, app_label_ref


def _resolve_arsc_resource(arsc_data, resource_id):
    """Resolve a resource reference by parsing resources.arsc.

    Uses the TypeSpec (0x0201) chunk to locate entry data for the
    target type/entry, then reads the string value from the global
    string pool.
    """
    if not arsc_data or len(arsc_data) < 8:
        return None

    target_pkg = (resource_id >> 24) & 0xFF
    target_type = (resource_id >> 16) & 0xFF
    target_entry = resource_id & 0xFFFF
    no_entry = 0xFFFFFFFF

    # Parse global string pool
    arsc_hdr = struct.unpack_from("<H", arsc_data, 2)[0]
    gsp_pos = arsc_hdr
    gsp_type = struct.unpack_from("<H", arsc_data, gsp_pos)[0]
    if gsp_type != _AXML_STRING_POOL:
        return None

    g_strings, pos = _axml_string_pool(arsc_data, gsp_pos)

    while pos < len(arsc_data):
        chunk_type = struct.unpack_from("<H", arsc_data, pos)[0]
        chunk_size = struct.unpack_from("<I", arsc_data, pos + 4)[0]
        if chunk_size == 0:
            break

        if chunk_type == 0x0200:  # RES_TABLE_PACKAGE_TYPE
            pkg_id = struct.unpack_from("<I", arsc_data, pos + 8)[0]
            if pkg_id != target_pkg:
                pos += chunk_size
                continue

            # Skip type and key string pools (only used for debugging)
            pkg_hdr = struct.unpack_from("<H", arsc_data, pos + 2)[0]
            inner = pos + pkg_hdr
            _, inner = _axml_string_pool(arsc_data, inner)  # type strings
            _, inner = _axml_string_pool(arsc_data, inner)  # key strings

            pkg_end = pos + chunk_size
            while inner < pkg_end:
                t2_type = struct.unpack_from("<H", arsc_data, inner)[0]
                t2_size = struct.unpack_from("<I", arsc_data, inner + 4)[0]
                if t2_size == 0:
                    break

                if t2_type == 0x0201:  # RES_TABLE_TYPE_SPEC_TYPE
                    ts_id = struct.unpack_from("<B", arsc_data, inner + 8)[0]
                    if ts_id != target_type:
                        inner += t2_size
                        continue

                    ts_hdr = struct.unpack_from("<H", arsc_data, inner + 2)[0]
                    ts_entry_count = struct.unpack_from(
                        "<I", arsc_data, inner + 12
                    )[0]

                    if target_entry >= ts_entry_count:
                        return None

                    # Entry offsets array at inner + ts_hdr
                    off_arr = inner + ts_hdr
                    e_off = struct.unpack_from(
                        "<I", arsc_data, off_arr + target_entry * 4
                    )[0]

                    if e_off == no_entry:
                        return None

                    # Entry data starts after the offset array
                    data_start = off_arr + ts_entry_count * 4
                    e_pos = data_start + e_off

                    # Read Res_value (8 bytes after the 8-byte entry header)
                    tv_type = arsc_data[e_pos + 11]  # byte 3 of Res_value
                    tv_data = struct.unpack_from(
                        "<I", arsc_data, e_pos + 12
                    )[0]

                    if tv_type == _AXML_TYPE_STRING and tv_data < len(g_strings):
                        return g_strings[tv_data]
                    return None

                inner += t2_size

        pos += chunk_size

    return None


def extract_apk_label(apk_path):
    """Extract the human-readable application label from an APK file.

    Opens the APK as a ZIP archive, parses the binary AndroidManifest.xml
    and (when needed) resources.arsc to resolve the label.

    Returns the label string, or None if extraction fails.
    """
    try:
        with zipfile.ZipFile(apk_path, "r") as zf:
            manifest_data = zf.read("AndroidManifest.xml")
            try:
                arsc_data = zf.read("resources.arsc")
            except KeyError:
                arsc_data = None

        label_str, label_ref = _parse_manifest_label(manifest_data)

        if label_str:
            return label_str

        if label_ref is not None and arsc_data is not None:
            resolved = _resolve_arsc_resource(arsc_data, label_ref)
            if resolved:
                return resolved

        return None
    except Exception:
        return None


def save_package_names(path, names):
    with io.open(path, "w", encoding="utf-8") as f:
        for name in names:
            f.write(name + "\n")
