"""Working-directory path normalization for pernix-ci blocks and workflows.

hashFiles() and other glob consumers reject '.' and '..' segments, so a
working-directory such as '.', './src' or 'repo/.' must be normalized before
it is joined into a path or pattern.

CLI:
  wdpath.py join <prefix> <path>   print <prefix>/<path> normalized ('.' when empty)
  wdpath.py glob <path>            print the normalized path as a glob prefix:
                                   '' for '.', else '<path>/'
"""

import sys


class WdPathError(ValueError):
    pass


def normalize(path):
    """Drop empty and '.' segments. Reject '..'. Return '.' for an empty result."""
    absolute = path.startswith("/")
    parts = []
    for seg in path.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            raise WdPathError("path '%s' must not contain '..' segments" % path)
        parts.append(seg)
    joined = "/".join(parts)
    if absolute:
        return "/" + joined
    return joined or "."


def join(prefix, path):
    """Join prefix and path, then normalize. An absolute path ignores prefix."""
    if path.startswith("/") or not prefix:
        return normalize(path)
    return normalize(prefix + "/" + path)


def glob_prefix(path):
    """Prefix for a '**/x' glob: '' for '.', else '<normalized>/'."""
    norm = normalize(path)
    if norm == ".":
        return ""
    if norm == "/":
        return "/"
    return norm + "/"


def main(argv):
    try:
        if len(argv) == 4 and argv[1] == "join":
            print(join(argv[2], argv[3]))
        elif len(argv) == 3 and argv[1] == "glob":
            print(glob_prefix(argv[2]))
        else:
            print("usage: wdpath.py join <prefix> <path> | glob <path>", file=sys.stderr)
            return 2
    except WdPathError as exc:
        print("::error::%s" % exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
