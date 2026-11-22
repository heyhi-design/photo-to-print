# Security Policy

## Supported Versions

This project is pre-1.0. Fixes are applied to the latest release only.

## Reporting a Vulnerability

Please report security issues privately rather than opening a public GitHub issue. Email **hello@heyhi.design** with a description of the issue, steps to reproduce, and any suggested fix. You should receive an acknowledgment within 5 business days.

## Scope

photo-to-print is a set of local scripts and documents. It makes no network calls and has no server component. The realistic risk surface:

- **Blender runs Python.** `kit.py build` runs your project's `scripts/build_part.py` inside Blender, and `kit.py verify` runs this repo's own scripts there. Only build projects whose scripts you've read. A `.blend` file passed with `--blend` can also carry scripts; open only files you trust.
- **Files you point it at.** `photo_tools.py` opens images with Pillow, and the checks import STL and GLB files through Blender's importers. Treat images and models from unknown sources the way you'd treat any untrusted file.
- **Photos can carry location data.** `photo_tools.py info` reads EXIF but never writes or uploads it. If you share a project folder, check what's in `reference/`.

If you find a path where any of this behaves worse than described, that's exactly what we'd like to hear about.
