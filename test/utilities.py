# coding=utf-8
"""Common functionality used by regression tests."""

QGIS_APP = None  # Static variable used to hold hand to running QGIS app


def get_qgis_app():
    """Start one QGIS application to test against.

    :returns: Handle to QGIS app

    If QGIS is already running the handle to that app will be returned.
    """
    global QGIS_APP
    if QGIS_APP is None:
        from qgis.core import QgsApplication

        gui_flag = True  # All test will run qgis in gui mode
        QGIS_APP = QgsApplication([], gui_flag)
        # Make sure QGIS_PREFIX_PATH is set in your env if needed!
        QGIS_APP.initQgis()

    return QGIS_APP
