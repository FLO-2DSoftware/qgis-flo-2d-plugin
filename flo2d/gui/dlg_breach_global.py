# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.PyQt.QtCore import Qt
from ..flo2d_tools.grid_tools import highlight_selected_segment, highlight_selected_xsection_a
from qgis.PyQt.QtWidgets import QTableWidgetItem, QApplication
from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..utils import float_or_zero

uiDialog, qtBaseClass = load_ui('global_breach_data')

class GlobalBreachDialog(qtBaseClass, uiDialog):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = None
        self.gutils = None
        self.feat_selection = []

        self.setup_connection()
        self.populate_global_breach_dialog()


    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_global_breach_dialog(self):
        qry = '''SELECT gzu , 
                        gzd , 
                        gzc , 
                        gcrestwidth , 
                        gcrestlength ,
                        gbrbotwidmax , 
                        gbrtopwidmax, 
                        gbrbottomel, 
                        gd50c , 
                        gporc , 
                        guwc , 
                        gcnc, 
                        gafrc, 
                        gcohc, 
                        gunfcc ,
                        gd50s , 
                        gpors  , 
                        guws , 
                        gcns , 
                        gafrs , 
                        gcohs , 
                        gunfcs , 
                        ggrasslength , 
                        ggrasscond , 
                        ggrassvmaxp ,
                        gsedconmax , 
                        d50df , 
                        gunfcdf
                FROM breach_global;'''

        row = self.gutils.execute(qry).fetchone() 
        if not row:
            return
        
        self.gzu_dbox.setValue(float_or_zero(row[0]))
        self.gzd_dbox.setValue(float_or_zero(row[1]))
        self.gzc_dbox.setValue(float_or_zero(row[2]))
        self.gcrestwidth_dbox.setValue(float_or_zero(row[3]))
        self.gcrestlength_dbox.setValue(float_or_zero(row[4]))
        self.gbrbotwidmax_dbox.setValue(float_or_zero(row[5]))
        self.gbrtopwidmax_dbox.setValue(float_or_zero(row[6]))
        self.gbrbottomel_dbox.setValue(float_or_zero(row[7]))
        self.gd50c_dbox.setValue(float_or_zero(row[8]))
        self.gporc_dbox.setValue(float_or_zero(row[9]))
        self.guwc_dbox.setValue(float_or_zero(row[10]))
        self.gcnc_dbox.setValue(float_or_zero(row[11]))
        self.gafrc_dbox.setValue(float_or_zero(row[12]))
        self.gcohc_dbox.setValue(float_or_zero(row[13]))
        self.gunfcc_dbox.setValue(float_or_zero(row[14]))
        self.gd50s_dbox.setValue(float_or_zero(row[15]))
        self.gpors_dbox.setValue(float_or_zero(row[16]))
        self.guws_dbox.setValue(float_or_zero(row[17]))
        self.gcns_dbox.setValue(float_or_zero(row[18]))
        self.gafrs_dbox.setValue(float_or_zero(row[19]))
        self.gcohs_dbox.setValue(float_or_zero(row[20]))
        self.gunfcs_dbox.setValue(float_or_zero(row[21]))
        self.ggrasslength_dbox.setValue(float_or_zero(row[22]))
        self.ggrasscond_dbox.setValue(float_or_zero(row[23]))
        self.ggrassvmaxp_dbox.setValue(float_or_zero(row[24]))
        self.gsedconmax_dbox.setValue(float_or_zero(row[25]))
        self.d50df_dbox.setValue(float_or_zero(row[26]))
        self.gunfcdf_dbox.setValue(float_or_zero(row[27]))

    def save_breach_global_data(self):
        """
        Save changes to breach_global.
        """
        update_qry = '''
        INSERT OR REPLACE INTO breach_global
        (   gzu , 
            gzd , 
            gzc , 
            gcrestwidth , 
            gcrestlength ,
            gbrbotwidmax , 
            gbrtopwidmax, 
            gbrbottomel, 
            gd50c , 
            gporc , 
            guwc , 
            gcnc, 
            gafrc, 
            gcohc, 
            gunfcc ,
            gd50s , 
            gpors  , 
            guws , 
            gcns , 
            gafrs , 
            gcohs , 
            gunfcs , 
            ggrasslength , 
            ggrasscond , 
            ggrassvmaxp ,
            gsedconmax , 
            d50df , 
            gunfcdf 
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ; '''
                
        try:
            self.gutils.clear_tables('breach_global')
            self.gutils.execute(update_qry, (
                self.gzu_dbox.value(),
                self.gzd_dbox.value(),
                self.gzc_dbox.value(),
                self.gcrestwidth_dbox.value(),
                self.gcrestlength_dbox.value(),
                self.gbrbotwidmax_dbox.value(),
                self.gbrtopwidmax_dbox.value(),
                self.gbrbottomel_dbox.value(),
                self.gd50c_dbox.value(),
                self.gporc_dbox.value(),
                self.guwc_dbox.value(),
                self.gcnc_dbox.value(),
                self.gafrc_dbox.value(),
                self.gcohc_dbox.value(),
                self.gunfcc_dbox.value(),
                self.gd50s_dbox.value(),
                self.gpors_dbox.value(),
                self.guws_dbox.value(),
                self.gcns_dbox.value(),
                self.gafrs_dbox.value(),
                self.gcohs_dbox.value(),
                self.gunfcs_dbox.value(),
                self.ggrasslength_dbox.value(),
                self.ggrasscond_dbox.value(),
                self.ggrassvmaxp_dbox.value(),
                self.gsedconmax_dbox.value(),
                self.d50df_dbox.value(),
                self.gunfcdf_dbox.value()
                ))
            return True
        except Exception as e:                
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 21019.0629: update of Breach Global Data failed!"
                       +'\n__________________________________________________', e)  
            return False 

