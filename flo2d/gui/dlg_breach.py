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

uiDialog_global, qtBaseClass = load_ui('global_breach_data')
uiDialog_individual, qtBaseClass = load_ui('individual_breach_data')

class GlobalBreachDialog(qtBaseClass, uiDialog_global):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog_global.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = None
        self.gutils = None
        self.equation = 0
        self.ratio = 0
        self.weird = 0
        self.time = 0       
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
                        gd50df , 
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
        self.gd50df_dbox.setValue(float_or_zero(row[26]))
        self.gunfcdf_dbox.setValue(float_or_zero(row[27]))

    def save_breach_global_data(self):
        """
        Save changes to breach_global.
        """
        update_breach_global_qry = '''
        UPDATE breach_global SET
            ibreachsedeqn  = ?, 
            gbratio  = ?, 
            gweircoef  = ?,  
            gbreachtime  = ?, 
            gzu  = ?, 
            gzd  = ? , 
            gzc  = ? , 
            gcrestwidth  = ? , 
            gcrestlength  = ? ,
            gbrbotwidmax  = ? , 
            gbrtopwidmax  = ?, 
            gbrbottomel  = ?, 
            gd50c  = ? , 
            gporc  = ? , 
            guwc  = ? , 
            gcnc  = ?, 
            gafrc  = ?, 
            gcohc  = ?, 
            gunfcc  = ? ,
            gd50s  = ? , 
            gpors  = ?  , 
            guws  = ? , 
            gcns  = ? , 
            gafrs  = ? , 
            gcohs  = ? , 
            gunfcs  = ? , 
            ggrasslength  = ? , 
            ggrasscond  = ? , 
            ggrassvmaxp  = ? ,
            gsedconmax  = ? , 
            gd50df  = ? , 
            gunfcdf  = ? ;
        '''
        
        
        
#         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ; '''
                
        try:
#             self.gutils.clear_tables('breach_global')
            if self.gutils.is_table_empty('breach_global'):
                sql = '''INSERT INTO breach_global DEFAULT VALUES;'''
                self.gutils.execute(sql,)
            
            self.gutils.execute(update_breach_global_qry, (
                self.equation,
                self.ratio,
                self.weird,
                self.time,
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
                self.gd50df_dbox.value(),
                self.gunfcdf_dbox.value()
                ))
            return True
        except Exception as e:                
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 21019.0629: update of Breach Global Data failed!"
                       +'\n__________________________________________________', e)  
            return False 

class IndividualBreachDialog(qtBaseClass, uiDialog_individual):

    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog_individual.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = None
        self.gutils = None

        self.setup_connection()
        self.individual_breach_element_cbo.currentIndexChanged.connect(self.individual_breach_element_cbo_currentIndexChanged)
        self.populate_individual_breach_dialog()


    def setup_connection(self):
        con = self.iface.f2d['con']
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_individual_breach_dialog(self):
        qry_breach_cells = '''SELECT breach_fid, grid_fid FROM breach_cells'''
        breach_rows = self.gutils.execute(qry_breach_cells).fetchall() 
        if not breach_rows:
            return
        
        for row in breach_rows:
            self.individual_breach_element_cbo.addItem(str(row[1]))

    def individual_breach_element_cbo_currentIndexChanged(self):
        qry_breach = '''SELECT 
                        ibreachdir,
                        zu , 
                        zd , 
                        zc , 
                        crestwidth , 
                        crestlength ,
                        brbotwidmax , 
                        brtopwidmax, 
                        brbottomel, 
                        d50c , 
                        porc , 
                        uwc , 
                        cnc, 
                        afrc, 
                        cohc, 
                        unfcc ,
                        d50s , 
                        pors  , 
                        uws , 
                        cns , 
                        afrs , 
                        cohs , 
                        unfcs , 
                        grasslength , 
                        grasscond , 
                        grassvmaxp ,
                        sedconmax , 
                        d50df , 
                        unfcdf
                FROM breach
                WHERE fid = ?;'''    
        
        qry_breach_cell = '''SELECT breach_fid FROM breach_cells WHERE grid_fid = ?'''
        
        breach = self.gutils.execute(qry_breach_cell, (self.individual_breach_element_cbo.currentText(),)).fetchone()  
        row = self.gutils.execute(qry_breach, (breach[0],)).fetchone()   
#         row = self.gutils.execute(qry_breach, (self.individual_breach_element_cbo.currentText(),)).fetchone()   
        
        if not row:
            pass
        
        self.breach_failure_direction_cbo.setCurrentIndex(row[0])
        self.zu_dbox.setValue(float_or_zero(row[1]))
        self.zd_dbox.setValue(float_or_zero(row[2]))
        self.zc_dbox.setValue(float_or_zero(row[3]))
        self.crestwidth_dbox.setValue(float_or_zero(row[4]))
        self.crestlength_dbox.setValue(float_or_zero(row[5]))
        self.brbotwidmax_dbox.setValue(float_or_zero(row[6]))
        self.brtopwidmax_dbox.setValue(float_or_zero(row[7]))
        self.brbottomel_dbox.setValue(float_or_zero(row[8]))
        self.d50c_dbox.setValue(float_or_zero(row[9]))
        self.porc_dbox.setValue(float_or_zero(row[10]))
        self.uwc_dbox.setValue(float_or_zero(row[11]))
        self.cnc_dbox.setValue(float_or_zero(row[12]))
        self.afrc_dbox.setValue(float_or_zero(row[13]))
        self.cohc_dbox.setValue(float_or_zero(row[14]))
        self.unfcc_dbox.setValue(float_or_zero(row[15]))
        self.d50s_dbox.setValue(float_or_zero(row[16]))
        self.pors_dbox.setValue(float_or_zero(row[17]))
        self.uws_dbox.setValue(float_or_zero(row[18]))
        self.cns_dbox.setValue(float_or_zero(row[19]))
        self.afrs_dbox.setValue(float_or_zero(row[20]))
        self.cohs_dbox.setValue(float_or_zero(row[21]))
        self.unfcs_dbox.setValue(float_or_zero(row[22]))
        self.grasslength_dbox.setValue(float_or_zero(row[23]))
        self.grasscond_dbox.setValue(float_or_zero(row[24]))
        self.grassvmaxp_dbox.setValue(float_or_zero(row[25]))
        self.sedconmax_dbox.setValue(float_or_zero(row[26]))
        self.d50df_dbox.setValue(float_or_zero(row[27]))
        self.unfcdf_dbox.setValue(float_or_zero(row[28]))
        
        
    def save_individual_breach_data(self):
        """
        Save changes to breach.
        """
        update_qry = '''
        UPDATE breach
        SET ibreachdir = ?,
            zu = ? , 
            zd  = ? , 
            zc = ?  , 
            crestwidth = ?  , 
            crestlength  = ? ,
            brbotwidmax  = ? , 
            brtopwidmax  = ? , 
            brbottomel = ? , 
            d50c  = ? , 
            porc = ?  , 
            uwc = ?  ,
            cnc = ? , 
            afrc = ? , 
            cohc = ? , 
            unfcc  = ? ,
            d50s = ?  , 
            pors = ?   , 
            uws = ?  , 
            cns = ?  , 
            afrs = ?  , 
            cohs = ?  , 
            unfcs = ?  , 
            grasslength = ?  , 
            grasscond = ?  , 
            grassvmaxp = ?  ,
            sedconmax = ?  , 
            d50df = ?  , 
            unfcdf = ?  
        WHERE fid = ? ; '''


        qry_breach_cell = '''SELECT breach_fid FROM breach_cells WHERE grid_fid = ?'''
        
                      
        try:
            breach = self.gutils.execute(qry_breach_cell, (self.individual_breach_element_cbo.currentText(),)).fetchone()    
            self.gutils.execute(update_qry, (
                self.breach_failure_direction_cbo.currentIndex(),
                self.zu_dbox.value(),
                self.zd_dbox.value(),
                self.zc_dbox.value(),
                self.crestwidth_dbox.value(),
                self.crestlength_dbox.value(),
                self.brbotwidmax_dbox.value(),
                self.brtopwidmax_dbox.value(),
                self.brbottomel_dbox.value(),
                self.d50c_dbox.value(),
                self.porc_dbox.value(),
                self.uwc_dbox.value(),
                self.cnc_dbox.value(),
                self.afrc_dbox.value(),
                self.cohc_dbox.value(),
                self.unfcc_dbox.value(),
                self.d50s_dbox.value(),
                self.pors_dbox.value(),
                self.uws_dbox.value(),
                self.cns_dbox.value(),
                self.afrs_dbox.value(),
                self.cohs_dbox.value(),
                self.unfcs_dbox.value(),
                self.grasslength_dbox.value(),
                self.grasscond_dbox.value(),
                self.grassvmaxp_dbox.value(),
                self.sedconmax_dbox.value(),
                self.d50df_dbox.value(),
                self.unfcdf_dbox.value(),
                breach[0]
                ))
            
            return True
        except Exception as e:                
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 040219.2015: update of Individual Breach Data failed!"
                       +'\n__________________________________________________', e)  
            return False 
