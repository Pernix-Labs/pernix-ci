#!/usr/bin/env python3
"""JSONC-tolerant global.json reader.

Usage: globaljson.py <path> <dotted.key>

Prints the value at the dotted key, or an empty line when the key or the
file is absent. Exits 1 with a message naming the file on parse error.
"""

import json
import sys


class GlobalJsonError(Exception):
    pass


def _scan(text, on_char):
    """Walk text, copying strings verbatim and passing other chars to on_char."""
    out = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        else:
            i = on_char(text, i, out)
    return "".join(out)


def _drop_comment(text, i, out):
    if text.startswith("//", i):
        end = text.find("\n", i)
        return len(text) if end == -1 else end
    if text.startswith("/*", i):
        end = text.find("*/", i + 2)
        if end == -1:
            raise ValueError("unterminated /* comment")
        out.append(" ")
        return end + 2
    out.append(text[i])
    return i + 1


def _drop_trailing_comma(text, i, out):
    if text[i] == ",":
        j = i + 1
        while j < len(text) and text[j] in " \t\r\n":
            j += 1
        if j < len(text) and text[j] in "}]":
            return i + 1
    out.append(text[i])
    return i + 1


def strip_jsonc(text):
    """Remove // and /* */ comments and trailing commas outside strings."""
    return _scan(_scan(text, _drop_comment), _drop_trailing_comma)


def load(path):
    """Return the parsed document, or None when the file is missing."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
    except FileNotFoundError:
        return None
    try:
        return json.loads(strip_jsonc(text))
    except ValueError as e:
        raise GlobalJsonError("failed to parse %s: %s" % (path, e))


def get(path, key):
    """Return the value at dotted `key` in `path`, or None if absent."""
    node = load(path)
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def format_value(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def main(argv):
    if len(argv) != 3:
        print("usage: globaljson.py <path> <dotted.key>", file=sys.stderr)
        return 1
    try:
        print(format_value(get(argv[1], argv[2])))
    except GlobalJsonError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
