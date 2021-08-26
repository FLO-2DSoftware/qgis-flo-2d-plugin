# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright � 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
from .ui_utils import load_ui
from ..user_communication import UserCommunication
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QFileDialog
from qgis.PyQt.QtGui import QPixmap

uiDialog, qtBaseClass = load_ui("confluences")
class Confluences2(qtBaseClass, uiDialog):
    def __init__(self, con, iface):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.setupUi(self)
        self.con = con
        self.iface = iface
        self.uc = UserCommunication(iface, "FLO-2D")
        
        # self.tributary_pic_lbl.pixmap = QPixmap(os.path.join(os.path.dirname(__file__), "img/confluence1.svg"))
        # self.main_pic_lbl.pixmap = QPixmap(os.path.join(os.path.dirname(__file__), "img/confluence2.png"))

        # pix = QPixmap(os.path.join(os.path.dirname(__file__), "img/confluence1.svg"))
        # self.tributary_pic_lbl.setPixmap(pix)
        # self.tributary_pic_lbl.setMask(pix.mask())
        # self.tributary_pic_lbl.show();
        #
        #
        # ui_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "img")
        # # ui_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "img", "confluence2.png" )
        # basepath = os.path.dirname(os.path.realpath(__file__))
        # picDir =  os.path.join(basepath, "/img")
        # # self.main_pic_lbl.setPixmap(QPixmap(ui_file, "confluence2.png")) 
        # self.main_pic_lbl.pixmap = QPixmap(ui_file, "confluence2.png")
        #
        # # idir = os.path.join(os.path.dirname(__file__), "..\\img")
        # # os.chdir("C:/Users/Juan Jose Rodriguez/Desktop/XSEC Interpolated")
        #
        idir = os.chdir("C:/Users/Juan Jose Rodriguez/git/qgis-flo-2d-plugin/flo2d/img")
        self.main_pic_lbl.pixmap = QPixmap(idir, "confluence2.png")   
        
        self.tributary_pic_lbl.show()  
        self.main_pic_lbl.show()   
        self.show()                