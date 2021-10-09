# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from .ui_utils import load_ui, set_icon
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui("mud_and_sediment")
class MudAndSedimentDialog(qtBaseClass, uiDialog):
    def __init__(self, con,  iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = con
        self.gutils = None
        
        set_icon(self.create_polygon_sed_btn, "mActionCapturePolygon.svg")
        set_icon(self.save_changes_sed_btn, "mActionSaveAllEdits.svg")
        set_icon(self.revert_changes_sed_btn, "mActionUndo.svg")
        set_icon(self.delete_sed_btn, "mActionDeleteSelected.svg")

        self.create_polygon_sed_btn.clicked.connect(self.create_polygon_sed)  
        self.save_changes_sed_btn.clicked.connect(self.save_sed_lyrs_edits)
        # self.revert_changes_sed_btn.clicked.connect(self.cancel_sed_lyrs_edits)
        # self.delete_sed_btn.clicked.connect(self.delete_sed)
        
        self.mud_debris_transport_radio.clicked.connect(self.show_mud)
        self.sediment_transport_radio.clicked.connect(self.show_sediment)
        self.none_transport_radio.clicked.connect(self.show_none)
        self.setup_connection()
        self.populate_mud_and_sediment()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
            
    def populate_mud_and_sediment(self):
        if self.gutils.get_cont_par("ISED") == "1":
            self.sediment_transport_radio.click()
            # self.show_sediment()
        elif self.gutils.get_cont_par("MUD") == "1":
            self.mud_debris_transport_radio.click()
            # self.show_mud()
        else:
            self.none_transport_radio.click()
            # self.show_none()
            
    def show_mud(self):
        self.mud_sediment_tabWidget.setTabEnabled(1, False); 
        self.mud_sediment_tabWidget.setTabEnabled(2, False); 
        self.mud_sediment_tabWidget.setTabEnabled(0, True);  
        self.mud_sediment_tabWidget.setStyleSheet("QTabBar::tab::disabled {width: 0; height: 0; margin: 0; padding: 0; border: none;} ")        
        self.mud_sediment_tabWidget.setCurrentIndex(0);
        
        
    def show_sediment(self):
        self.mud_sediment_tabWidget.setTabEnabled(0, False); 
        self.mud_sediment_tabWidget.setTabEnabled(2, False); 
        self.mud_sediment_tabWidget.setTabEnabled(1, True); 
        self.mud_sediment_tabWidget.setStyleSheet("QTabBar::tab::disabled {width: 0; height: 0; margin: 0; padding: 0; border: none;} ")       
        self.mud_sediment_tabWidget.setCurrentIndex(1); 
        
    def show_none(self):
        self.mud_sediment_tabWidget.setTabEnabled(0, False); 
        # self.mud_sediment_tabWidget.setCurrentIndex(0)
        self.mud_sediment_tabWidget.setStyleSheet("QTabBar::tab::disabled {width: 0; height: 0; margin: 0; padding: 0; border: none;} ")   
        self.mud_sediment_tabWidget.setTabEnabled(1, False); 
        # self.mud_sediment_tabWidget.setCurrentIndex(1) 
        self.mud_sediment_tabWidget.setStyleSheet("QTabBar::tab::disabled {width: 0; height: 0; margin: 0; padding: 0; border: none;} ")     
        self.mud_sediment_tabWidget.setCurrentIndex(2); 
         
    def save_mud_sediment(self): 
        if self.mud_debris_transport_radio.isChecked():
            self.gutils.set_cont_par("ISED", 0);
            self.gutils.set_cont_par("MUD", 1);  
        elif self.sediment_transport_radio.isChecked():
            self.gutils.set_cont_par("MUD", 0); 
            self.gutils.set_cont_par("ISED", 1); 
        else:
            self.gutils.set_cont_par("MUD", 0); 
            self.gutils.set_cont_par("ISED", 0);              
                       
    def create_polygon_sed(self):
        self.lyrs.enter_edit_mode("sed_rigid_areas")
        
    def save_sed_lyrs_edits(self):
        """
        Save changes of sed_rigid_areas layer.
        """
        if not self.gutils or not self.lyrs.any_lyr_in_edit("sed_rigid_areas"):
            return
        self.lyrs.save_lyrs_edits("sed_rigid_areas")
        self.lyrs.lyrs_to_repaint = [self.lyrs.data["sed_rigid_areas"]["qlyr"]]
        self.lyrs.repaint_layers()                 