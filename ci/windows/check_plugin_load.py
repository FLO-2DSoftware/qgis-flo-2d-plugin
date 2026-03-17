import faulthandler
import os
import sys
import traceback

from qgis.PyQt.QtCore import QCoreApplication, QTimer
from qgis.core import Qgis
import qgis.utils

PLUGIN_NAME = os.environ.get("PLUGIN_NAME", "flo2d")


def log(msg):
    print(msg, flush=True)


def finish(code: int):
    log(f"[INFO] Finishing with exit code {code}")
    QCoreApplication.exit(code)


def main():
    log("[INFO] check_plugin_load.py started")

    try:
        log(f"[INFO] QGIS version: {Qgis.QGIS_VERSION}")
        log(f"[INFO] Python version: {sys.version}")
        log(f"[INFO] Plugin name: {PLUGIN_NAME}")
        log(f"[INFO] Plugin paths: {qgis.utils.plugin_paths}")

        plugin_path = os.path.join(qgis.utils.plugin_paths[0], PLUGIN_NAME)
        log(f"[INFO] Does plugin package exist? {os.path.exists(plugin_path)}")
        log(f"[INFO] Plugin package path: {plugin_path}")

        log(f"[INFO] Calling loadPlugin('{PLUGIN_NAME}')")
        ok_load = qgis.utils.loadPlugin(PLUGIN_NAME)
        log(f"[INFO] loadPlugin -> {ok_load}")

        if not ok_load:
            log(f"[ERROR] loadPlugin('{PLUGIN_NAME}') returned False")
            finish(1)
            return

        module = sys.modules.get(PLUGIN_NAME)
        if module is None:
            log(f"[ERROR] Plugin module '{PLUGIN_NAME}' not found in sys.modules after loadPlugin")
            finish(1)
            return

        log(f"[INFO] Loaded module: {module}")

        if not hasattr(module, "classFactory"):
            log(f"[ERROR] Plugin module '{PLUGIN_NAME}' has no classFactory")
            finish(1)
            return

        iface = qgis.utils.iface
        log(f"[INFO] iface object: {iface}")

        faulthandler.dump_traceback_later(60, repeat=False)

        log("[INFO] Calling module.classFactory(iface)")
        plugin = module.classFactory(iface)
        log(f"[INFO] classFactory returned plugin instance: {type(plugin).__name__}")

        if hasattr(plugin, "initGui"):
            log("[INFO] Calling plugin.initGui()")
            plugin.initGui()
            log("[INFO] plugin.initGui() completed")
        else:
            log("[INFO] Plugin has no initGui()")

        faulthandler.cancel_dump_traceback_later()

        log(f"[SUCCESS] Plugin '{PLUGIN_NAME}' loaded successfully.")
        finish(0)

    except Exception:
        faulthandler.cancel_dump_traceback_later()
        log("[ERROR] Exception while loading plugin.")
        traceback.print_exc()
        finish(1)


log("[INFO] Scheduling main() with QTimer.singleShot")
QTimer.singleShot(0, main)