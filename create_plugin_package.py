# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import os
import re
import shutil


def get_plugin_version(directory):
    metadata = os.path.join(directory, "metadata.txt")
    reg = "\nversion=(.+)\n"
    version = ""
    with open(metadata, "r") as f:
        match = re.search(reg, f.read())
        if match:
            version = match.group(1)
    return version


if __name__ == "__main__":
    print("Creating plugin package...")
    this_dir = os.path.dirname(os.path.realpath(__file__))
    plugin_dirname = "flo2d"
    plugin_path = os.path.join(this_dir, plugin_dirname)
    plugin_version = get_plugin_version(plugin_path)
    zip_filename = f"{plugin_dirname}-{plugin_version}"
    plugin_zip_path = os.path.join(this_dir, zip_filename)
    shutil.make_archive(plugin_zip_path, "zip", this_dir, plugin_dirname)
    print(f"Creating plugin package '{zip_filename}' finished.")
