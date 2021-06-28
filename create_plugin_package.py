# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import os
import re
import shutil
import subprocess


def get_plugin_version(directory):
    metadata = os.path.join(directory, "metadata.txt")
    reg = "\nversion=(.+)\n"
    version = ""
    with open(metadata, "r") as f:
        match = re.search(reg, f.read())
        if match:
            version = match.group(1)
    return version


def build_sphinx_docs(directory, source="source", build="build", output_format="html"):
    dest_dir = os.path.join(build, output_format)
    build_cmd = subprocess.run(["sphinx-build", "-b", output_format, source, dest_dir], cwd=directory)
    build_cmd.check_returncode()


if __name__ == "__main__":
    print("Creating plugin package...")
    this_dir = os.path.dirname(os.path.realpath(__file__))
    plugin_dirname = "flo2d"
    plugin_path = os.path.join(this_dir, plugin_dirname)
    docs_path = os.path.join(this_dir, "docs", "user")
    print("Building documentation...")
    try:
        build_sphinx_docs(docs_path)
        html_build_path = os.path.join(docs_path, "build", "html")
        html_help_path = os.path.join(plugin_path, "help", "html")
        print("Copying documentation files to the help folder...")
        if os.path.exists(html_build_path):
            if os.path.exists(html_help_path):
                shutil.rmtree(html_help_path)
            shutil.copytree(html_build_path, html_help_path)
    except subprocess.CalledProcessError as e:
        print("Building documentation skipped due to Sphinx error!")
    print("Zipping plugin package...")
    plugin_version = get_plugin_version(plugin_path)
    zip_filename = f"{plugin_dirname}-{plugin_version}"
    plugin_zip_path = os.path.join(this_dir, zip_filename)
    shutil.make_archive(plugin_zip_path, "zip", this_dir, plugin_dirname)
    print(f"Creating plugin package '{zip_filename}' finished.")
