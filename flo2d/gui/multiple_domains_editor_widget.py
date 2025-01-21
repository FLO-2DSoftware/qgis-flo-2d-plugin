#  -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

from ..user_communication import UserCommunication
from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("multiple_domains_editor")


class MultipleDomainsEditorWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.con = None
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.grid_lyr = None

    def setup_connection(self):
        pass