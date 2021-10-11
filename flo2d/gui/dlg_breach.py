# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import functools
import time

from qgis.PyQt.QtCore import Qt, QEvent
from qgis.PyQt.QtWidgets import (
    QTableWidgetItem,
    QApplication,
    QInputDialog,
    QDialogButtonBox,
    QListView,
    QComboBox,
    QDoubleSpinBox,
    QWidget,
)
from qgis.PyQt.QtGui import QStandardItemModel, QStandardItem, QColor, QIntValidator, QPalette
from .ui_utils import load_ui, set_icon, center_canvas, zoom
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..utils import float_or_zero, int_or_zero
from ..flo2d_tools.grid_tools import adjacent_grid_elevations, number_of_elements, buildCellIDNPArray, buildCellElevNPArray, adjacent_grid_elevations_np, cellIDNumpyArray, xvalsNumpyArray, yvalsNumpyArray, cellElevNumpyArray

from pickle import FALSE
from qgis.core import *
from datetime import datetime
from math import modf

import numpy as np

# from qgis.PyQt.QtWidgets import (QApplication, QDialogButtonBox, QInputDialog, QFileDialog,
#                                 QTableWidgetItem, , , QTableView, QCompleter, QTableWidget, qApp )

uiDialog_global, qtBaseClass = load_ui("global_breach_data")
uiDialog_individual_breach, qtBaseClass = load_ui("individual_breach_data")
uiDialog_levee_fragility, qtBaseClass = load_ui("levee_fragility_curves")
uiDialog_individual_levees, qtBaseClass = load_ui("individual_levee_data")

def timer(func):
    """Print the runtime of the decorated function"""
    @functools.wraps(func)
    def wrapper_timer(*args, **kwargs):
        start_time = time.perf_counter()    # 1
        value = func(*args, **kwargs)
        end_time = time.perf_counter()      # 2
        run_time = end_time - start_time    # 3
        print(f"Finished {func.__name__!r} in {run_time:.4f} secs")
        return value
    return wrapper_timer

def timer1(func):
    """Print the runtime of the decorated function"""
    @functools.wraps(func)
    def wrapper_timer(arg):
        start_time = time.perf_counter()    # 1
        value = func(arg)
        end_time = time.perf_counter()      # 2
        run_time = end_time - start_time    # 3
        print(f"Finished {func.__name__!r} in {run_time:.4f} secs")
        return value
    return wrapper_timer

class GlobalBreachDialog(qtBaseClass, uiDialog_global):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog_global.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None
        self.equation = 0
        self.ratio = 0
        self.weird = 0
        self.time = 0
        self.setup_connection()
        self.populate_global_breach_dialog()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_global_breach_dialog(self):
        qry = """SELECT gzu , 
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
                        gunfcdf,
                        useglobaldata
                FROM breach_global;"""

        try:
            row = self.gutils.execute(qry).fetchone()
            if not row:
                return

            self.use_global_data_chbox.setChecked(int_or_zero(row[28]))

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

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 220319.0434: loading Global Breach Data failed!"
                + "\n__________________________________________________",
                e,
            )
            return False

    def save_breach_global_data(self):
        """
        Save changes to breach_global.
        """
        update_breach_global_qry = """
        UPDATE breach_global SET
            ibreachsedeqn  = ?, 
            gbratio  = ?, 
            gweircoef  = ?,  
            gbreachtime  = ?, 
            useglobaldata = ?,
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
        """

        try:
            if self.gutils.is_table_empty("breach_global"):
                sql = """INSERT INTO breach_global DEFAULT VALUES;"""
                self.gutils.execute(
                    sql,
                )

            self.gutils.execute(
                update_breach_global_qry,
                (
                    self.equation,
                    self.ratio,
                    self.weird,
                    self.time,
                    self.use_global_data_chbox.isChecked(),
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
                    self.gunfcdf_dbox.value(),
                ),
            )
            return True
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 21019.0629: update of Breach Global Data failed!"
                + "\n__________________________________________________",
                e,
            )
            return False


class IndividualBreachDialog(qtBaseClass, uiDialog_individual_breach):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog_individual_breach.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None

        self.setup_connection()
        self.individual_breach_element_cbo.currentIndexChanged.connect(
            self.individual_breach_element_cbo_currentIndexChanged
        )

        self.populate_individual_breach_dialog()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_individual_breach_dialog(self):
        qry_breach_cells = """SELECT breach_fid, grid_fid FROM breach_cells ORDER BY grid_fid"""
        breach_rows = self.gutils.execute(qry_breach_cells).fetchall()
        if not breach_rows:
            return

        for row in breach_rows:
            self.individual_breach_element_cbo.addItem(str(row[1]))

    def individual_breach_element_cbo_currentIndexChanged(self):
        qry_breach = """SELECT 
                        ibreachdir,
                        zu , 
                        zd , 
                        zc , 
                        crestwidth , 
                        crestlength ,
                        brbotwidmax , 
                        brtopwidmax, 
                        brbottomel, 
                        weircoef,
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
                        bratio, 
                        grasslength , 
                        grasscond , 
                        grassvmaxp ,
                        sedconmax , 
                        d50df , 
                        unfcdf,
                        breachtime
                FROM breach
                WHERE fid = ?;"""

        qry_breach_cell = """SELECT breach_fid FROM breach_cells WHERE grid_fid = ?"""

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

        self.weircoef_dbox.setValue(float_or_zero(row[9]))

        self.d50c_dbox.setValue(float_or_zero(row[10]))
        self.porc_dbox.setValue(float_or_zero(row[11]))
        self.uwc_dbox.setValue(float_or_zero(row[12]))
        self.cnc_dbox.setValue(float_or_zero(row[13]))
        self.afrc_dbox.setValue(float_or_zero(row[14]))
        self.cohc_dbox.setValue(float_or_zero(row[15]))
        self.unfcc_dbox.setValue(float_or_zero(row[16]))
        self.d50s_dbox.setValue(float_or_zero(row[17]))
        self.pors_dbox.setValue(float_or_zero(row[18]))
        self.uws_dbox.setValue(float_or_zero(row[19]))
        self.cns_dbox.setValue(float_or_zero(row[20]))
        self.afrs_dbox.setValue(float_or_zero(row[21]))
        self.cohs_dbox.setValue(float_or_zero(row[22]))
        self.unfcs_dbox.setValue(float_or_zero(row[23]))

        self.bratio_dbox.setValue(float_or_zero(row[24]))

        self.grasslength_dbox.setValue(float_or_zero(row[25]))
        self.grasscond_dbox.setValue(float_or_zero(row[26]))
        self.grassvmaxp_dbox.setValue(float_or_zero(row[27]))
        self.sedconmax_dbox.setValue(float_or_zero(row[28]))
        self.d50df_dbox.setValue(float_or_zero(row[29]))
        self.unfcdf_dbox.setValue(float_or_zero(row[30]))

        self.breachtime_dbox.setValue(float_or_zero(row[31]))

    def save_individual_breach_data(self):
        """
        Save changes to breach.
        """
        update_qry = """
        UPDATE breach
        SET ibreachdir = ?,
            zu = ?, 
            zd  = ?, 
            zc = ?, 
            crestwidth = ?, 
            crestlength  = ?,
            brbotwidmax  = ?, 
            brtopwidmax  = ?, 
            brbottomel = ?, 
            weircoef = ?,
            d50c  = ?, 
            porc = ?, 
            uwc = ?,
            cnc = ?, 
            afrc = ?, 
            cohc = ?, 
            unfcc  = ?,
            d50s = ?, 
            pors = ?, 
            uws = ?, 
            cns = ?, 
            afrs = ?, 
            cohs = ?, 
            unfcs = ?, 
            bratio = ?,
            grasslength = ?, 
            grasscond = ?, 
            grassvmaxp = ?,
            sedconmax = ?, 
            d50df = ?, 
            unfcdf = ?,
            breachtime = ?
        WHERE fid = ? ; """

        qry_breach_cell = """SELECT breach_fid FROM breach_cells WHERE grid_fid = ?"""

        try:
            breach = self.gutils.execute(
                qry_breach_cell, (self.individual_breach_element_cbo.currentText(),)
            ).fetchone()
            self.gutils.execute(
                update_qry,
                (
                    self.breach_failure_direction_cbo.currentIndex(),
                    self.zu_dbox.value(),
                    self.zd_dbox.value(),
                    self.zc_dbox.value(),
                    self.crestwidth_dbox.value(),
                    self.crestlength_dbox.value(),
                    self.brbotwidmax_dbox.value(),
                    self.brtopwidmax_dbox.value(),
                    self.brbottomel_dbox.value(),
                    self.weircoef_dbox.value(),
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
                    self.bratio_dbox.value(),
                    self.grasslength_dbox.value(),
                    self.grasscond_dbox.value(),
                    self.grassvmaxp_dbox.value(),
                    self.sedconmax_dbox.value(),
                    self.d50df_dbox.value(),
                    self.unfcdf_dbox.value(),
                    self.breachtime_dbox.value(),
                    breach[0],
                ),
            )

            return True
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 040219.2015: update of Individual Breach Data failed!"
                + "\n__________________________________________________",
                e,
            )
            return False


class LeveeFragilityCurvesDialog(qtBaseClass, uiDialog_levee_fragility):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog_levee_fragility.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None

        set_icon(self.add_curve_btn, "add.svg")
        set_icon(self.remove_curve_btn, "remove.svg")

        self.setup_connection()
        self.ID_cbo.currentIndexChanged.connect(self.ID_cbo_currentIndexChanged)
        self.add_row_btn.clicked.connect(self.add_row)
        self.delete_row_btn.clicked.connect(self.delete_row)
        self.add_curve_btn.clicked.connect(self.add_curve)
        self.remove_curve_btn.clicked.connect(self.remove_curve)

        self.populate_list_of_curves()
        self.populate_table_with_current_curve()

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def populate_list_of_curves(self):
        qry_probabilities = """SELECT fragchar, prfail, prdepth FROM breach_fragility_curves"""
        probabilities_rows = self.gutils.execute(qry_probabilities).fetchall()
        if not probabilities_rows:
            return
        self.ID_cbo.clear()
        for row in probabilities_rows:
            if self.ID_cbo.findText(str(row[0])) == -1:
                self.ID_cbo.addItem(str(row[0]))

    def add_curve(self):
        #         qid = QInputDialog()
        #         title = "Enter Your Name"
        #         label = "Name: "
        #         mode = QLineEdit.Normal
        #         default = "<your name here>"
        #         txt, ok = QinputDialog.getText(qid,title, label, mode, default)
        ID, ok = QInputDialog.getText(None, "New fragility curve ID", "Fragility curve ID (one letter and one number)")
        if not ok or not ID:
            return
        sql = """INSERT INTO breach_fragility_curves (fragchar, prfail, prdepth) VALUES (?,?,?);"""
        self.gutils.execute(
            sql,
            (
                ID,
                "0.0",
                "0.0",
            ),
        )
        self.populate_list_of_curves()
        self.ID_cbo.setCurrentIndex(len(self.ID_cbo) - 1)
        self.populate_table_with_current_curve()

    def remove_curve(self):
        qry = """DELETE FROM breach_fragility_curves WHERE fragchar = ?;"""
        self.gutils.execute(qry, (self.ID_cbo.currentText(),))

        self.populate_list_of_curves()
        self.populate_table_with_current_curve()

    def add_row(self):
        #         self.fragility_tblw.insertRow(self.fragility_tblw.rowCount())
        self.fragility_tblw.insertRow(self.fragility_tblw.currentRow())

    def delete_row(self):
        self.fragility_tblw.removeRow(self.fragility_tblw.currentRow())

    def populate_table_with_current_curve(self):
        qry_curve = """SELECT prfail, prdepth FROM breach_fragility_curves WHERE fragchar = ?;"""

        data = self.gutils.execute(qry_curve, (self.ID_cbo.currentText(),)).fetchall()
        if not data:
            pass

        self.fragility_tblw.clear()
        for row, value in enumerate(data):
            if value[0] is not None:
                item1 = QTableWidgetItem()
                item1.setData(Qt.DisplayRole, value[0])
                self.fragility_tblw.setItem(row, 0, item1)

                item2 = QTableWidgetItem()
                item2.setData(Qt.DisplayRole, value[1])
                self.fragility_tblw.setItem(row, 1, item2)

    def ID_cbo_currentIndexChanged(self):
        self.populate_table_with_current_curve()

    def save_current_probability_table(self):
        pass
        """
        Save changes to table.
        """
        qry = """DELETE FROM breach_fragility_curves WHERE fragchar = ?;"""
        self.gutils.execute(qry, (self.ID_cbo.currentText(),))

        sql = """INSERT INTO breach_fragility_curves (fragchar, prfail, prdepth) VALUES (?,?,?);"""

        for row in range(0, self.fragility_tblw.rowCount()):
            item = QTableWidgetItem()
            item = self.fragility_tblw.item(row, 0)
            if item is not None:

                fragchar = self.ID_cbo.currentText()
                prfail = str(item.text())
                item = self.fragility_tblw.item(row, 1)
                prdepth = item.text() if item is not None else 0
                self.gutils.execute(sql, (fragchar, prfail, prdepth))

        return True


#         except Exception as e:
#             QApplication.restoreOverrideCursor()
#             self.uc.show_error("ERROR 130219.0755: update of fragility curves failed!"
#                        +'\n__________________________________________________', e)
#             return False


class IndividualLeveesDialog(qtBaseClass, uiDialog_individual_levees):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog_individual_levees.__init__(self)
        self.iface = iface
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = None
        self.gutils = None
        self.ext = self.iface.mapCanvas().extent()
        self.levee_rows = []
        self.n_levees = 1000
        self.previousWidget = ""
        self.previousDirection = 0
        name = ""

        self.failureData = {
            1: [False, 0, 0, 0, 0, 0, 0],
            2: [False, 0, 0, 0, 0, 0, 0],
            3: [False, 0, 0, 0, 0, 0, 0],
            4: [False, 0, 0, 0, 0, 0, 0],
            5: [False, 0, 0, 0, 0, 0, 0],
            6: [False, 0, 0, 0, 0, 0, 0],
            7: [False, 0, 0, 0, 0, 0, 0],
            8: [False, 0, 0, 0, 0, 0, 0],
        }

        self.grid_lyr = self.lyrs.data["grid"]["qlyr"]
        
        set_icon(self.zoom_in_btn, "zoom_in.svg")
        set_icon(self.zoom_out_btn, "zoom_out.svg")
        set_icon(self.find_levee_cell_btn, "eye-svgrepo-com.svg")
        set_icon(self.previous_levees_btn, "arrow_4.svg")
        set_icon(self.next_levees_btn, "arrow_2.svg")
        self.previous_levees_lbl.setText("Previous " + str(self.n_levees))
        self.next_levees_lbl.setText("Next " + str(self.n_levees))

        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.setup_connection()
        
        self.grid_count = self.gutils.count('grid', field="fid")
        
        global cellIDNumpyArray
        global cellElevNumpyArray
        if cellIDNumpyArray is None:
            cellIDNumpyArray, xvalsNumpyArray, yvalsNumpyArray = buildCellIDNPArray(self.gutils)
        if cellElevNumpyArray is None:
            cellElevNumpyArray = buildCellElevNPArray(self.gutils, cellIDNumpyArray)

        # Allow only integers:
        validator = QIntValidator()
        self.individual_levee_element_cbo.setValidator(validator)
        self.cell_to_find_le.setValidator(validator)

        self.levee_data_save_btn.clicked.connect(self.save_individual_levee_data)
        self.find_levee_cell_btn.clicked.connect(self.find_levee_cell)

        self.individual_levee_element_cbo.currentIndexChanged.connect(
            self.individual_levee_element_cbo_currentIndexChanged
        )
        self.N_chbox.stateChanged.connect(self.N_chbox_checked)
        self.E_chbox.stateChanged.connect(self.E_chbox_checked)
        self.S_chbox.stateChanged.connect(self.S_chbox_checked)
        self.W_chbox.stateChanged.connect(self.W_chbox_checked)
        self.NE_chbox.stateChanged.connect(self.NE_chbox_checked)
        self.SE_chbox.stateChanged.connect(self.SE_chbox_checked)
        self.SW_chbox.stateChanged.connect(self.SW_chbox_checked)
        self.NW_chbox.stateChanged.connect(self.NW_chbox_checked)
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        self.next_levees_btn.clicked.connect(self.load_next_combo)
        self.previous_levees_btn.clicked.connect(self.load_previous_combo)

        #         self.N_dbox.editingFinished.connect(lambda: self.directionEditingFinished(self.N_dbox))
        #         self.E_dbox.editingFinished.connect(lambda: self.directionEditingFinished(self.E_dbox))
        #         self.S_dbox.editingFinished.connect(lambda: self.directionEditingFinished(self.S_dbox))
        #         self.W_dbox.editingFinished.connect(lambda: self.directionEditingFinished(self.W_dbox))
        #         self.NE_dbox.editingFinished.connect(lambda: self.directionEditingFinished(self.NE_dbox))
        #         self.SE_dbox.editingFinished.connect(lambda: self.directionEditingFinished(self.SE_dbox))
        #         self.SW_dbox.editingFinished.connect(lambda: self.directionEditingFinished(self.SW_dbox))
        #         self.NW_dbox.editingFinished.connect(lambda: self.directionEditingFinished(self.NW_dbox))

        self.individual_levee_element_cbo.installEventFilter(self)
        self.cell_to_find_le.installEventFilter(self)
        self.find_levee_cell_btn.installEventFilter(self)
        self.previous_levees_btn.installEventFilter(self)
        self.next_levees_btn.installEventFilter(self)

        self.N_dbox.installEventFilter(self)
        self.E_dbox.installEventFilter(self)
        self.S_dbox.installEventFilter(self)
        self.W_dbox.installEventFilter(self)
        self.NE_dbox.installEventFilter(self)
        self.SE_dbox.installEventFilter(self)
        self.SW_dbox.installEventFilter(self)
        self.NW_dbox.installEventFilter(self)

        #         self.N_chbox.installEventFilter(self)
        #         self.E_chbox.installEventFilter(self)
        #         self.S_chbox.installEventFilter(self)
        #         self.W_chbox.installEventFilter(self)
        #         self.NE_chbox.installEventFilter(self)
        #         self.SE_chbox.installEventFilter(self)
        #         self.SW_chbox.installEventFilter(self)
        #         self.NW_chbox.installEventFilter(self)

        self.levee_failure_grp.installEventFilter(self)
        self.failure_elevation_dbox.installEventFilter(self)
        self.failure_duration_dbox.installEventFilter(self)
        self.failure_base_elevation_dbox.installEventFilter(self)
        self.failure_max_width_dbox.installEventFilter(self)
        self.failure_vertical_rate_dbox.installEventFilter(self)
        self.failure_horizontal_rate_dbox.installEventFilter(self)
        
        self.populate_individual_levees_dialog()

        QApplication.restoreOverrideCursor()

    #         event = QEvent(QEvent.FocusIn)
    #         self.eventFilter(self.E_dbox, event)
    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)
    @timer
    def populate_individual_levees_dialog(self):
        
        qry_levee_cells = (
            """SELECT grid_fid, ldir, levcrest, user_line_fid FROM levee_data GROUP BY grid_fid ORDER BY grid_fid"""
        )
        #starttime = datetime.now()
        self.levee_rows = self.gutils.execute(qry_levee_cells).fetchall()
        #print ("qry_levee_cells: %s"  % (datetime.now() - starttime).total_seconds())       
        
        if not self.levee_rows:
            return

        self.setWindowTitle("Individual Levee Data (" + str(len(self.levee_rows)) + " grid elements with levees)")

        i = 0
        self.next_levees_btn.setEnabled(False)
        for row in self.levee_rows:
            if i == self.n_levees:
                self.next_levees_btn.setEnabled(True)
                break
            if self.individual_levee_element_cbo.findText(str(row[0])) == -1:
                self.individual_levee_element_cbo.addItem(str(row[0]))
                i += 1

        self.previous_levees_btn.setEnabled(False)
        self.levee_failure_grp.setChecked(False)
    def eventFilter(self, widget, event):
        name = widget.objectName()
        if event.type() == QEvent.FocusOut:
            if name in [
                "levee_failure_grp",
                "failure_elevation_dbox",
                "failure_duration_dbox",
                "failure_base_elevation_dbox",
                "failure_max_width_dbox",
                "failure_vertical_rate_dbox",
                "failure_horizontal_rate_dbox",
            ]:

                self.failureData[self.previousDirection] = [
                    self.levee_failure_grp.isChecked(),
                    self.failure_elevation_dbox.value(),
                    self.failure_duration_dbox.value(),
                    self.failure_base_elevation_dbox.value(),
                    self.failure_max_width_dbox.value(),
                    self.failure_vertical_rate_dbox.value(),
                    self.failure_horizontal_rate_dbox.value(),
                ]

        elif event.type() == QEvent.FocusIn:

            if name not in [
                "levee_failure_grp",
                "failure_elevation_dbox",
                "failure_duration_dbox",
                "failure_base_elevation_dbox",
                "failure_max_width_dbox",
                "failure_vertical_rate_dbox",
                "failure_horizontal_rate_dbox",
            ]:

                self.N_dbox.setStyleSheet("")
                self.E_dbox.setStyleSheet("")
                self.S_dbox.setStyleSheet("")
                self.W_dbox.setStyleSheet("")
                self.NE_dbox.setStyleSheet("")
                self.SE_dbox.setStyleSheet("")
                self.SW_dbox.setStyleSheet("")
                self.NW_dbox.setStyleSheet("")

                self.failure_elevation_dbox.setStyleSheet("")
                self.failure_duration_dbox.setStyleSheet("")
                self.failure_base_elevation_dbox.setStyleSheet("")
                self.failure_max_width_dbox.setStyleSheet("")
                self.failure_vertical_rate_dbox.setStyleSheet("")
                self.failure_horizontal_rate_dbox.setStyleSheet("")
                self.levee_failure_grp.setTitle("Levee failure")

            t = ""
            styleSheet = ""
            cell = self.individual_levee_element_cbo.currentText()
            if name == "NW_dbox":
                t = "North West (8) "
                styleSheet = "background-color: rgb(255,255,132)"
                widget.setStyleSheet(styleSheet)
                self.load_grid_failure(cell, 8)
                self.previousDirection = 8

            elif name == "N_dbox":
                t = "North (1) "
                styleSheet = "background-color: rgb(255,187,187)"
                widget.setStyleSheet(styleSheet)
                self.load_grid_failure(cell, 1)
                self.previousDirection = 1

            elif name == "NE_dbox":
                t = "North East (5) "
                styleSheet = "background-color: rgb(250,237,173)"
                widget.setStyleSheet(styleSheet)
                self.load_grid_failure(cell, 5)
                self.previousDirection = 5

            elif name == "E_dbox":
                t = "East (2) "
                styleSheet = "background-color: rgb(231,244,136)"
                widget.setStyleSheet(styleSheet)
                self.load_grid_failure(cell, 2)
                self.previousDirection = 2

            elif name == "SE_dbox":
                t = "South East (6) "
                styleSheet = "background-color: rgb(255,179,102)"
                widget.setStyleSheet(styleSheet)
                self.load_grid_failure(cell, 6)
                self.previousDirection = 6

            elif name == "S_dbox":
                t = "South (3) "
                styleSheet = "background-color: rgb(217,179,255)"
                widget.setStyleSheet(styleSheet)
                self.load_grid_failure(cell, 3)
                self.previousDirection = 3

            elif name == "SW_dbox":
                t = "South West (7) "
                styleSheet = "background-color: rgb(180,209,241)"
                widget.setStyleSheet(styleSheet)
                self.load_grid_failure(cell, 7)
                self.previousDirection = 7

            elif name == "W_dbox":
                t = "West (4) "
                styleSheet = "background-color: rgb(193,193,255)"
                widget.setStyleSheet(styleSheet)
                self.load_grid_failure(cell, 4)
                self.previousDirection = 4

            if t != "":
                self.failure_elevation_dbox.setStyleSheet(styleSheet)
                self.failure_duration_dbox.setStyleSheet(styleSheet)
                self.failure_base_elevation_dbox.setStyleSheet(styleSheet)
                self.failure_max_width_dbox.setStyleSheet(styleSheet)
                self.failure_vertical_rate_dbox.setStyleSheet(styleSheet)
                self.failure_horizontal_rate_dbox.setStyleSheet(styleSheet)

                self.levee_failure_grp.setTitle(t + " levee failure")
            #                 self.levee_failure_grp.setChecked(True)

            self.previousWidget = name

        return QWidget.eventFilter(self, widget, event)
    @timer
    def load_grid_failure(self, grid, direction):

        #         if self.failureData.get(direction)[0]:  # Index [0] is a boolean indicating that the direction is selected or not.
        self.levee_failure_grp.setChecked(self.failureData.get(direction)[0])
        self.failure_elevation_dbox.setValue(float_or_zero(self.failureData.get(direction)[1]))
        self.failure_duration_dbox.setValue(float_or_zero(self.failureData.get(direction)[2]))
        self.failure_base_elevation_dbox.setValue(float_or_zero(self.failureData.get(direction)[3]))
        self.failure_max_width_dbox.setValue(float_or_zero(self.failureData.get(direction)[4]))
        self.failure_vertical_rate_dbox.setValue(float_or_zero(self.failureData.get(direction)[5]))
        self.failure_horizontal_rate_dbox.setValue(float_or_zero(self.failureData.get(direction)[6]))

    #         select_failure_sql = '''SELECT failevel, failtime, levbase, failwidthmax, failrate, failwidrate
    #                                 FROM levee_failure
    #                                 WHERE grid_fid = ? AND lfaildir = ?'''
    #
    #         fail = self.gutils.execute(select_failure_sql, (grid, direction)).fetchone()
    #         if fail:
    #             self.failure_elevation_dbox.setValue(float_or_zero(fail[0]))
    #             self.failure_duration_dbox.setValue(float_or_zero(fail[1]))
    #             self.failure_base_elevation_dbox.setValue(float_or_zero(fail[2]))
    #             self.failure_max_width_dbox.setValue(float_or_zero(fail[3]))
    #             self.failure_vertical_rate_dbox.setValue(float_or_zero(fail[4]))
    #             self.failure_horizontal_rate_dbox.setValue(float_or_zero(fail[5]))
    @timer
    def load_next_combo(self):
        self.previous_levees_btn.setEnabled(True)
        self.individual_levee_element_cbo.setCurrentIndex(self.individual_levee_element_cbo.count() - 1)
        last = self.individual_levee_element_cbo.currentText()
        row = [y[0] for y in self.levee_rows].index(int(last))
        if len(self.levee_rows) > row:
            self.individual_levee_element_cbo.clear()
            for i in range(row + 1, row + 1 + self.n_levees):
                if i == len(self.levee_rows):
                    self.next_levees_btn.setEnabled(False)
                    break
                self.individual_levee_element_cbo.addItem(str(self.levee_rows[i][0]))
    @timer
    def directionEditingFinished(self, widget):
        widget.setStyleSheet("")
    @timer
    def load_previous_combo(self):
        self.next_levees_btn.setEnabled(True)
        self.individual_levee_element_cbo.setCurrentIndex(0)
        first = self.individual_levee_element_cbo.currentText()
        row = [y[0] for y in self.levee_rows].index(int(first))
        self.individual_levee_element_cbo.clear()
        for i in range(row - self.n_levees, row):
            self.individual_levee_element_cbo.addItem(str(self.levee_rows[i][0]))
        if row - self.n_levees == 0:
            self.previous_levees_btn.setEnabled(False)
    @timer1
    def individual_levee_element_cbo_currentIndexChanged(self):
        cell = self.individual_levee_element_cbo.currentText()
        self.show_levee(cell)
    @timer
    def show_levee(self, cell):                   
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.uc.clear_bar_messages()

            if cell == "":
                return
            else:
                cell = int(cell)
                if cell > self.grid_count or cell < 0:
                    self.uc.bar_warn("Cell is outside the computational domain!")
                    return

            self.clear_all_directions()

            # Load local failure data.
            levee_all_failure_qry = """SELECT lfaildir, failevel, failtime, levbase, failwidthmax, failrate, failwidrate
                                   FROM levee_failure 
                                   WHERE grid_fid = ?"""
            all_failure = self.gutils.execute(levee_all_failure_qry, (cell,)).fetchall()
            for f in all_failure:
                self.failureData[f[0]] = [True, f[1], f[2], f[3], f[4], f[5], f[6]]

            qry_levee_cell = """SELECT ldir, levcrest FROM levee_data WHERE grid_fid = ?"""
            levees_for_this_cell = self.gutils.execute(qry_levee_cell, (cell,)).fetchall()
            high_light_this = 999
            for levee in levees_for_this_cell:
                dir = levee[0]
                crest_elev = levee[1]
                if dir == 1:
                    self.N_chbox.setChecked(True)
                    self.N_dbox.setEnabled(True)
                    self.N_dbox.setValue(float_or_zero(crest_elev))
                    high_light_this = min(high_light_this, 1)
                elif dir == 2:
                    self.E_chbox.setChecked(True)
                    self.E_dbox.setEnabled(True)
                    self.E_dbox.setValue(float_or_zero(crest_elev))
                elif dir == 3:
                    self.S_chbox.setChecked(True)
                    self.S_dbox.setEnabled(True)
                    self.S_dbox.setValue(float_or_zero(crest_elev))
                elif dir == 4:
                    self.W_chbox.setChecked(True)
                    self.W_dbox.setEnabled(True)
                    self.W_dbox.setValue(float_or_zero(crest_elev))
                elif dir == 5:
                    self.NE_chbox.setChecked(True)
                    self.NE_dbox.setEnabled(True)
                    self.NE_dbox.setValue(float_or_zero(crest_elev))
                elif dir == 6:
                    self.SE_chbox.setChecked(True)
                    self.SE_dbox.setEnabled(True)
                    self.SE_dbox.setValue(float_or_zero(crest_elev))
                elif dir == 7:
                    self.SW_chbox.setChecked(True)
                    self.SW_dbox.setEnabled(True)
                    self.SW_dbox.setValue(float_or_zero(crest_elev))
                elif dir == 8:
                    self.NW_chbox.setChecked(True)
                    self.NW_dbox.setEnabled(True)
                    self.NW_dbox.setValue(float_or_zero(crest_elev))

                high_light_this = min(high_light_this, dir)

            #starttime = datetime.now()
            grid_elev = self.gutils.execute("SELECT elevation FROM grid WHERE fid = ?", (cell,)).fetchone()[0]
            #print ("Grid_elev: %s"  % (datetime.now() - starttime).total_seconds())
            #starttime = datetime.now()
            #grid_elev = cellElevNumpyArray[cellIDNumpyArray == int(cell)][0]
            #print ("Grid_elev_np: %s"  % (datetime.now() - starttime).total_seconds())
            
            self.grid_elevation_lbl.setText(str(grid_elev))

            levee_failure_qry = """SELECT failevel, failtime, levbase, failwidthmax, failrate, failwidrate
                                   FROM levee_failure 
                                   WHERE grid_fid = ? AND lfaildir = ?"""
            failure = self.gutils.execute(levee_failure_qry, (cell, dir)).fetchone()
            if failure:
                self.levee_failure_grp.setChecked(True)
                self.failure_elevation_dbox.setValue(float_or_zero(failure[0]))
                self.failure_duration_dbox.setValue(float_or_zero(failure[1]))
                self.failure_base_elevation_dbox.setValue(float_or_zero(failure[2]))
                self.failure_max_width_dbox.setValue(float_or_zero(failure[3]))
                self.failure_vertical_rate_dbox.setValue(float_or_zero(failure[4]))
                self.failure_horizontal_rate_dbox.setValue(float_or_zero(failure[5]))
            else:
                self.levee_failure_grp.setChecked(False)

            self.cell_to_find_le.setText(str(cell))

            # Find elevations of adjacent cells:

            try:

                sel_elev_qry = """SELECT elevation FROM grid WHERE fid = ?;"""
                cell_size = float(self.gutils.get_cont_par("CELLSIZE"))
                if self.gutils.get_cont_par("METRIC") == "1":
                    unit = "   mts"
                else:
                    unit = "   ft"
                    
                
                #starttime = datetime.now()
                #elevs = adjacent_grid_elevations(self.gutils, self.grid_lyr, cell, cell_size)
                #print ("Adjacent_grid_elevations: %s"  % (datetime.now() - starttime).total_seconds())
                cell = int(cell)
                #starttime = datetime.now()
                elevs = adjacent_grid_elevations_np(cell, cellIDNumpyArray, cellElevNumpyArray)
                #print ("Adjacent_grid_elevations_np: %s"  % (datetime.now() - starttime).total_seconds())
                
                
                if self.grid_count >= cell and cell > 0:
                    self.currentCell = next(self.grid_lyr.getFeatures(QgsFeatureRequest(cell)))
                    xx, yy = self.currentCell.geometry().centroid().asPoint()

                    # North cell:
                    N_elev = elevs[0]
                    self.N_lbl.setText(str(N_elev) + unit if N_elev != -999 else "(boundary)")

                    # NorthEast cell:
                    NE_elev = elevs[1]
                    self.NE_lbl.setText(str(NE_elev) + unit if NE_elev != -999 else "(boundary)")

                    # East cell:
                    E_elev = elevs[2]
                    self.E_lbl.setText(str(E_elev) + unit if E_elev != -999 else "(boundary)")

                    # SouthEast cell:
                    SE_elev = elevs[3]
                    self.SE_lbl.setText(str(SE_elev) + unit if SE_elev != -999 else "(boundary)")

                    # South cell:
                    S_elev = elevs[4]
                    self.S_lbl.setText(str(S_elev) + unit if S_elev != -999 else "(boundary)")

                    # SouthWest cell:
                    SW_elev = elevs[5]
                    self.SW_lbl.setText(str(SW_elev) + unit if SW_elev != -999 else "(boundary)")

                    # West cell:
                    W_elev = elevs[6]
                    self.W_lbl.setText(str(W_elev) + unit if W_elev != -999 else "(boundary)")

                    # NorthWest cell:
                    NW_elev = elevs[7]
                    self.NW_lbl.setText(str(NW_elev) + unit if NW_elev != -999 else "(boundary)")

                    self.highlight_cell(cell)

            except ValueError:
                self.uc.bar_warn("ERROR 031219.0709: Cell " + str(cell) + " is not valid.")
                pass

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 280319.1510: could not load levee data!"
                + "\n__________________________________________________",
                e,
            )
            return False
        finally:
            QApplication.restoreOverrideCursor()
    @timer
    def get_adjacent_cell_elevation(self, xx, yy, cell_size, unit, dir):
        sel_elev_qry = """SELECT elevation FROM grid WHERE fid = ?;"""
        elev = -999
        if dir == "N":
            # North cell:
            y = yy + cell_size
            x = xx
            grid = self.gutils.grid_on_point(x, y)
            if grid is not None:
                elev = self.gutils.execute(sel_elev_qry, (grid,)).fetchone()[0]
                self.N_lbl.setText(str(elev) + unit)
            else:
                self.N_lbl.setText("(boundary)")

        elif dir == "NE":
            # NorthEast cell:
            y = yy + cell_size
            x = xx + cell_size
            grid = self.gutils.grid_on_point(x, y)
            if grid is not None:
                elev = self.gutils.execute(sel_elev_qry, (grid,)).fetchone()[0]
                self.NE_lbl.setText(str(elev) + unit)
            else:
                self.NE_lbl.setText("(boundary)")

        elif dir == "E":
            # East cell:
            x = xx + cell_size
            y = yy
            grid = self.gutils.grid_on_point(x, y)
            if grid is not None:
                elev = self.gutils.execute(sel_elev_qry, (grid,)).fetchone()[0]
                self.E_lbl.setText(str(elev) + unit)
            else:
                self.E_lbl.setText("(boundary)")

        elif dir == "SE":
            # SouthEast cell:
            y = yy - cell_size
            x = xx + cell_size
            grid = self.gutils.grid_on_point(x, y)
            if grid is not None:
                elev = self.gutils.execute(sel_elev_qry, (grid,)).fetchone()[0]
                self.SE_lbl.setText(str(elev) + unit)
            else:
                self.SE_lbl.setText("(boundary)")

        elif dir == "S":
            # South cell:
            y = yy - cell_size
            x = xx
            grid = self.gutils.grid_on_point(x, y)
            if grid is not None:
                elev = self.gutils.execute(sel_elev_qry, (grid,)).fetchone()[0]
                self.S_lbl.setText(str(elev) + unit)
            else:
                self.S_lbl.setText("(boundary)")

        elif dir == "SW":
            # SouthWest cell:
            y = yy - cell_size
            x = xx - cell_size
            grid = self.gutils.grid_on_point(x, y)
            if grid is not None:
                elev = self.gutils.execute(sel_elev_qry, (grid,)).fetchone()[0]
                self.SW_lbl.setText(str(elev) + unit)
            else:
                self.SW_lbl.setText("(boundary)")

        elif dir == "W":
            # West cell:
            y = yy
            x = xx - cell_size
            grid = self.gutils.grid_on_point(x, y)
            if grid is not None:
                elev = self.gutils.execute(sel_elev_qry, (grid,)).fetchone()[0]
                self.W_lbl.setText(str(elev) + unit)
            else:
                self.W_lbl.setText("(boundary)")

        elif dir == "NW":
            # NorthWest cell:
            y = yy + cell_size
            x = xx - cell_size
            grid = self.gutils.grid_on_point(x, y)
            if grid is not None:
                elev = self.gutils.execute(sel_elev_qry, (grid,)).fetchone()[0]
                self.NW_lbl.setText(str(elev) + unit)
            else:
                self.NW_lbl.setText("(boundary)")

        else:
            self.uc.bar_warn("Invalid direction!")

        return elev
    @timer
    def clear_all_directions(self):
        self.N_chbox.setChecked(False)
        self.E_chbox.setChecked(False)
        self.S_chbox.setChecked(False)
        self.W_chbox.setChecked(False)
        self.NE_chbox.setChecked(False)
        self.SE_chbox.setChecked(False)
        self.SW_chbox.setChecked(False)
        self.NW_chbox.setChecked(False)

        self.N_dbox.setValue(0)
        self.E_dbox.setValue(0)
        self.S_dbox.setValue(0)
        self.W_dbox.setValue(0)
        self.NE_dbox.setValue(0)
        self.SE_dbox.setValue(0)
        self.SW_dbox.setValue(0)
        self.NW_dbox.setValue(0)

        self.N_dbox.setEnabled(False)
        self.E_dbox.setEnabled(False)
        self.S_dbox.setEnabled(False)
        self.W_dbox.setEnabled(False)
        self.NE_dbox.setEnabled(False)
        self.SE_dbox.setEnabled(False)
        self.SW_dbox.setEnabled(False)
        self.NW_dbox.setEnabled(False)

    def N_chbox_checked(self):
        self.N_dbox.setEnabled(self.N_chbox.isChecked())
        self.levee_failure_grp.setChecked(self.N_chbox.isChecked())

    def E_chbox_checked(self):
        self.E_dbox.setEnabled(self.E_chbox.isChecked())
        self.levee_failure_grp.setChecked(self.E_chbox.isChecked())

    def S_chbox_checked(self):
        self.S_dbox.setEnabled(self.S_chbox.isChecked())
        self.levee_failure_grp.setChecked(self.S_chbox.isChecked())

    def W_chbox_checked(self):
        self.W_dbox.setEnabled(self.W_chbox.isChecked())
        self.levee_failure_grp.setChecked(self.W_chbox.isChecked())

    def NE_chbox_checked(self):
        self.NE_dbox.setEnabled(self.NE_chbox.isChecked())
        self.levee_failure_grp.setChecked(self.NE_chbox.isChecked())

    def SE_chbox_checked(self):
        self.SE_dbox.setEnabled(self.SE_chbox.isChecked())
        self.levee_failure_grp.setChecked(self.SE_chbox.isChecked())

    def SW_chbox_checked(self):
        self.SW_dbox.setEnabled(self.SW_chbox.isChecked())
        self.levee_failure_grp.setChecked(self.SW_chbox.isChecked())

    def NW_chbox_checked(self):
        self.NW_dbox.setEnabled(self.NW_chbox.isChecked())
        self.levee_failure_grp.setChecked(self.NW_chbox.isChecked())

    #     def NW_dbox_valueChanged (self):
    #         self.NW_dbox.setStyleSheet("background-color:yellow; border: 2px solid Red")

    def NW_dbox_editingFinished(self):
        #         self.NW_dbox.setStyleSheet("background-color:blue; border: 2px solid Yellow")
        self.NW_dbox.setStyleSheet("")

    def save_individual_levee_data(self):
        """
        Save changes to individual levee.
        """

        cell_size = float(self.gutils.get_cont_par("CELLSIZE"))
        levee_grid = self.individual_levee_element_cbo.currentText()

        if levee_grid == "":
            return
        else:
            cell = int(levee_grid)
            n_cells = number_of_elements(self.gutils, self.grid_lyr)          
            if cell > n_cells or cell < 0:
                self.uc.bar_warn("WARNING 221219.1141: Cell is outside the computational domain!")
                return

        try:

            # Retrive previous levee user_line_fid:
            user_line_fid = self.gutils.execute("SELECT user_line_fid FROM levee_data WHERE grid_fid = ?;", (levee_grid,)).fetchone()
            user_line_fid = None if not user_line_fid else user_line_fid[0]
            
            # Delete all features of this cell in levee_data and levee_failure:
            self.gutils.execute("DELETE FROM levee_data WHERE grid_fid = ?;", (levee_grid,))
            self.gutils.execute("DELETE FROM levee_failure WHERE grid_fid = ?;", (levee_grid,))
            
            
            insert_qry = "INSERT INTO levee_data (ldir, levcrest,  grid_fid, user_line_fid, geom) VALUES (?,?,?,?,?);"
            insert_failure_qry = """INSERT INTO levee_failure
                                     (grid_fid, lfaildir,  failevel, failtime, levbase, failwidthmax, failrate, failwidrate ) 
                                    VALUES (?,?,?,?,?,?,?,?);"""            

            if self.N_chbox.isChecked():
                geom = self.gutils.build_levee(levee_grid, "1", cell_size)
                self.gutils.execute(insert_qry, (1, self.N_dbox.value(), levee_grid, user_line_fid, geom))
                if self.failureData.get(1)[0]:
                    self.gutils.execute(
                        insert_failure_qry,
                        (
                            levee_grid,
                            1,
                            self.failureData.get(1)[1],
                            self.failureData.get(1)[2],
                            self.failureData.get(1)[3],
                            self.failureData.get(1)[4],
                            self.failureData.get(1)[5],
                            self.failureData.get(1)[6],
                        ),
                    )

            if self.E_chbox.isChecked():
                geom = self.gutils.build_levee(levee_grid, "2", cell_size)
                self.gutils.execute(insert_qry, (2, self.E_dbox.value(), levee_grid, user_line_fid, geom))
                if self.failureData.get(2)[0]:
                    self.gutils.execute(
                        insert_failure_qry,
                        (
                            levee_grid,
                            2,
                            self.failureData.get(2)[1],
                            self.failureData.get(2)[2],
                            self.failureData.get(2)[3],
                            self.failureData.get(2)[4],
                            self.failureData.get(2)[5],
                            self.failureData.get(2)[6],
                        ),
                    )

            if self.S_chbox.isChecked():
                geom = self.gutils.build_levee(levee_grid, "3", cell_size)
                self.gutils.execute(insert_qry, (3, self.S_dbox.value(), levee_grid, user_line_fid, geom))
                if self.failureData.get(3)[0]:
                    self.gutils.execute(
                        insert_failure_qry,
                        (
                            levee_grid,
                            3,
                            self.failureData.get(3)[1],
                            self.failureData.get(3)[2],
                            self.failureData.get(3)[3],
                            self.failureData.get(3)[4],
                            self.failureData.get(3)[5],
                            self.failureData.get(3)[6],
                        ),
                    )

            if self.W_chbox.isChecked():
                geom = self.gutils.build_levee(levee_grid, "4", cell_size)
                self.gutils.execute(insert_qry, (4, self.W_dbox.value(), levee_grid, user_line_fid, geom))
                if self.failureData.get(4)[0]:
                    self.gutils.execute(
                        insert_failure_qry,
                        (
                            levee_grid,
                            4,
                            self.failureData.get(4)[1],
                            self.failureData.get(4)[2],
                            self.failureData.get(4)[3],
                            self.failureData.get(4)[4],
                            self.failureData.get(4)[5],
                            self.failureData.get(4)[6],
                        ),
                    )

            if self.NE_chbox.isChecked():
                geom = self.gutils.build_levee(levee_grid, "5", cell_size)
                self.gutils.execute(insert_qry, (5, self.NE_dbox.value(), levee_grid, user_line_fid, geom))
                if self.failureData.get(5)[0]:
                    self.gutils.execute(
                        insert_failure_qry,
                        (
                            levee_grid,
                            5,
                            self.failureData.get(5)[1],
                            self.failureData.get(5)[2],
                            self.failureData.get(5)[3],
                            self.failureData.get(5)[4],
                            self.failureData.get(5)[5],
                            self.failureData.get(5)[6],
                        ),
                    )

            if self.SE_chbox.isChecked():
                geom = self.gutils.build_levee(levee_grid, "6", cell_size)
                self.gutils.execute(insert_qry, (6, self.SE_dbox.value(), levee_grid, user_line_fid, geom))
                if self.failureData.get(6)[0]:
                    self.gutils.execute(
                        insert_failure_qry,
                        (
                            levee_grid,
                            6,
                            self.failureData.get(6)[1],
                            self.failureData.get(6)[2],
                            self.failureData.get(6)[3],
                            self.failureData.get(6)[4],
                            self.failureData.get(6)[5],
                            self.failureData.get(6)[6],
                        ),
                    )

            if self.SW_chbox.isChecked():
                geom = self.gutils.build_levee(levee_grid, "7", cell_size)
                self.gutils.execute(insert_qry, (7, self.SW_dbox.value(), levee_grid, user_line_fid, geom))
                if self.failureData.get(7)[0]:
                    self.gutils.execute(
                        insert_failure_qry,
                        (
                            levee_grid,
                            7,
                            self.failureData.get(7)[1],
                            self.failureData.get(7)[2],
                            self.failureData.get(7)[3],
                            self.failureData.get(7)[4],
                            self.failureData.get(7)[5],
                            self.failureData.get(7)[6],
                        ),
                    )

            if self.NW_chbox.isChecked():
                geom = self.gutils.build_levee(levee_grid, "8", cell_size)
                self.gutils.execute(insert_qry, (8, self.NW_dbox.value(), levee_grid, user_line_fid, geom))
                if self.failureData.get(8)[0]:
                    self.gutils.execute(
                        insert_failure_qry,
                        (
                            levee_grid,
                            8,
                            self.failureData.get(8)[1],
                            self.failureData.get(8)[2],
                            self.failureData.get(8)[3],
                            self.failureData.get(8)[4],
                            self.failureData.get(8)[5],
                            self.failureData.get(8)[6],
                        ),
                    )

            self.lyrs.lyrs_to_repaint = [
                self.lyrs.data["levee_data"]["qlyr"],
                self.lyrs.data["levee_failure"]["qlyr"]
            ]
            self.lyrs.repaint_layers()
            
            levees = self.lyrs.data["levee_data"]["qlyr"]
            levees.triggerRepaint()

            QApplication.restoreOverrideCursor()
            self.uc.bar_info("Individual Levee Data for cell " + levee_grid + " saved.")

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 280319.1651: update of Individual Levee Data failed!"
                + "\n__________________________________________________",
                e,
            )
            return False        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        # """
        # Save changes to individual levee.
        # """
        #
        # levee_grid = self.individual_levee_element_cbo.currentText()
        #
        # if levee_grid == "":
        #     return
        # else:
        #     cell = int(levee_grid)
        #     n_cells = number_of_elements(self.gutils, self.grid_lyr)          
        #     if cell > n_cells or cell < 0:
        #         self.uc.bar_warn("WARNING 221219.1141: Cell is outside the computational domain!")
        #         return
        #
        # try:
        #
        #     insert_qry = "INSERT INTO levee_data (ldir, levcrest,  grid_fid ) VALUES (?,?,?);"
        #     insert_failure_qry = """INSERT INTO levee_failure
        #                              (grid_fid, lfaildir,  failevel, failtime, levbase, failwidthmax, failrate, failwidrate ) 
        #                             VALUES (?,?,?,?,?,?,?,?);"""
        #
        #     # Delete all features of this cell in levee_data and levee_failure:
        #     self.gutils.execute("DELETE FROM levee_data WHERE grid_fid = ?;", (levee_grid,))
        #     self.gutils.execute("DELETE FROM levee_failure WHERE grid_fid = ?;", (levee_grid,))
        #
        #     if self.N_chbox.isChecked():
        #         self.gutils.execute(insert_qry, (1, self.N_dbox.value(), levee_grid))
        #         if self.failureData.get(1)[0]:
        #             self.gutils.execute(
        #                 insert_failure_qry,
        #                 (
        #                     levee_grid,
        #                     1,
        #                     self.failureData.get(1)[1],
        #                     self.failureData.get(1)[2],
        #                     self.failureData.get(1)[3],
        #                     self.failureData.get(1)[4],
        #                     self.failureData.get(1)[5],
        #                     self.failureData.get(1)[6],
        #                 ),
        #             )
        #
        #     if self.E_chbox.isChecked():
        #         self.gutils.execute(insert_qry, (2, self.E_dbox.value(), levee_grid))
        #         if self.failureData.get(2)[0]:
        #             self.gutils.execute(
        #                 insert_failure_qry,
        #                 (
        #                     levee_grid,
        #                     2,
        #                     self.failureData.get(2)[1],
        #                     self.failureData.get(2)[2],
        #                     self.failureData.get(2)[3],
        #                     self.failureData.get(2)[4],
        #                     self.failureData.get(2)[5],
        #                     self.failureData.get(2)[6],
        #                 ),
        #             )
        #
        #     if self.S_chbox.isChecked():
        #         self.gutils.execute(insert_qry, (3, self.S_dbox.value(), levee_grid))
        #         if self.failureData.get(3)[0]:
        #             self.gutils.execute(
        #                 insert_failure_qry,
        #                 (
        #                     levee_grid,
        #                     3,
        #                     self.failureData.get(3)[1],
        #                     self.failureData.get(3)[2],
        #                     self.failureData.get(3)[3],
        #                     self.failureData.get(3)[4],
        #                     self.failureData.get(3)[5],
        #                     self.failureData.get(3)[6],
        #                 ),
        #             )
        #
        #     if self.W_chbox.isChecked():
        #         self.gutils.execute(insert_qry, (4, self.W_dbox.value(), levee_grid))
        #         if self.failureData.get(4)[0]:
        #             self.gutils.execute(
        #                 insert_failure_qry,
        #                 (
        #                     levee_grid,
        #                     4,
        #                     self.failureData.get(4)[1],
        #                     self.failureData.get(4)[2],
        #                     self.failureData.get(4)[3],
        #                     self.failureData.get(4)[4],
        #                     self.failureData.get(4)[5],
        #                     self.failureData.get(4)[6],
        #                 ),
        #             )
        #
        #     if self.NE_chbox.isChecked():
        #         self.gutils.execute(insert_qry, (5, self.NE_dbox.value(), levee_grid))
        #         if self.failureData.get(5)[0]:
        #             self.gutils.execute(
        #                 insert_failure_qry,
        #                 (
        #                     levee_grid,
        #                     5,
        #                     self.failureData.get(5)[1],
        #                     self.failureData.get(5)[2],
        #                     self.failureData.get(5)[3],
        #                     self.failureData.get(5)[4],
        #                     self.failureData.get(5)[5],
        #                     self.failureData.get(5)[6],
        #                 ),
        #             )
        #
        #     if self.SE_chbox.isChecked():
        #         self.gutils.execute(insert_qry, (6, self.SE_dbox.value(), levee_grid))
        #         if self.failureData.get(6)[0]:
        #             self.gutils.execute(
        #                 insert_failure_qry,
        #                 (
        #                     levee_grid,
        #                     6,
        #                     self.failureData.get(6)[1],
        #                     self.failureData.get(6)[2],
        #                     self.failureData.get(6)[3],
        #                     self.failureData.get(6)[4],
        #                     self.failureData.get(6)[5],
        #                     self.failureData.get(6)[6],
        #                 ),
        #             )
        #
        #     if self.SW_chbox.isChecked():
        #         self.gutils.execute(insert_qry, (7, self.SW_dbox.value(), levee_grid))
        #         if self.failureData.get(7)[0]:
        #             self.gutils.execute(
        #                 insert_failure_qry,
        #                 (
        #                     levee_grid,
        #                     7,
        #                     self.failureData.get(7)[1],
        #                     self.failureData.get(7)[2],
        #                     self.failureData.get(7)[3],
        #                     self.failureData.get(7)[4],
        #                     self.failureData.get(7)[5],
        #                     self.failureData.get(7)[6],
        #                 ),
        #             )
        #
        #     if self.NW_chbox.isChecked():
        #         self.gutils.execute(insert_qry, (8, self.NW_dbox.value(), levee_grid))
        #         if self.failureData.get(8)[0]:
        #             self.gutils.execute(
        #                 insert_failure_qry,
        #                 (
        #                     levee_grid,
        #                     8,
        #                     self.failureData.get(8)[1],
        #                     self.failureData.get(8)[2],
        #                     self.failureData.get(8)[3],
        #                     self.failureData.get(8)[4],
        #                     self.failureData.get(8)[5],
        #                     self.failureData.get(8)[6],
        #                 ),
        #             )
        #
        #     # levee_data layer queries:
        #     select_qry = "SELECT * FROM levee_data WHERE grid_fid = ? AND ldir = ?"
        #     update_qry = "UPDATE levee_data SET ldir = ?, levcrest = ? WHERE grid_fid = ? AND ldir = ?"
        #     insert_qry = "INSERT INTO levee_data (ldir, levcrest,  grid_fid ) VALUES (?,?,?);"
        #     delete_qry = "DELETE FROM levee_data WHERE grid_fid = ? AND ldir = ?"
        #     delete_failure_qry = "DELETE FROM levee_failure WHERE grid_fid = ? and lfaildir = ?;"
        #
        #     # levee_failure layer queries:
        #     select_failure_qry = "SELECT * FROM levee_failure WHERE grid_fid = ? AND lfaildir = ?;"
        #     insert_failure_qry = """INSERT INTO levee_failure
        #                              (grid_fid, lfaildir,  failevel, failtime, levbase, failwidthmax, failrate, failwidrate ) 
        #                             VALUES (?,?,?,?,?,?,?,?);"""
        #     update_levee_failure_qry = """UPDATE levee_failure 
        #                                     SET failevel = ?, 
        #                                         failtime = ?, 
        #                                         levbase = ?, 
        #                                         failwidthmax  = ?, 
        #                                         failrate = ?, 
        #                                         failwidrate = ?
        #                                     WHERE grid_fid = ? AND lfaildir = ? ; """
        #
        #     #             if self.N_chbox.isChecked():
        #     #                 # Does this direction exists for this cell? If so update, otherwise insert:
        #     #                 if self.gutils.execute(select_qry, (levee_grid, 1)).fetchone():
        #     #                    self.gutils.execute(update_qry, (1, self.N_dbox.value(), int(levee_grid), 1))
        #     #                 else:
        #     #                     self.gutils.execute(insert_qry, (1,self.N_dbox.value(), levee_grid))
        #     #             else:
        #     #                 # This direction is not selected, if exists, delete it:
        #     # #                 if self.gutils.execute(select_qry, (levee_grid, 1)).fetchone():
        #     #                 self.gutils.execute(delete_qry, (levee_grid, 1))
        #     #                 self.gutils.execute(delete_failure_qry, (levee_grid, 1))
        #     #
        #     #
        #     #
        #     #
        #     #             if self.E_chbox.isChecked():
        #     #                 # Does this direction exists for this cell? If so update, otherwise insert:
        #     #                 if self.gutils.execute(select_qry, (levee_grid, 2)).fetchone():
        #     #                    self.gutils.execute(update_qry, (2, self.E_dbox.value(), int(levee_grid), 2))
        #     #                 else:
        #     #                     self.gutils.execute(insert_qry, (2,self.E_dbox.value(), levee_grid))
        #     #             else:
        #     #                 # This direction is not selected, if exists, delete it:
        #     # #                 if self.gutils.execute(select_qry, (levee_grid, 2)).fetchone():
        #     #                 self.gutils.execute(delete_qry, (levee_grid, 2))
        #     #                 self.gutils.execute(delete_failure_qry, (levee_grid, 2))
        #     #
        #     #
        #     #
        #     #
        #     #             if self.S_chbox.isChecked():
        #     #                 # Does this direction exists for this cell? If so update, otherwise insert:
        #     #                 if self.gutils.execute(select_qry, (levee_grid, 3)).fetchone():
        #     #                    self.gutils.execute(update_qry, (3, self.S_dbox.value(), int(levee_grid), 3))
        #     #                 else:
        #     #                     self.gutils.execute(insert_qry, (3,self.S_dbox.value(), levee_grid))
        #     #             else:
        #     #                 # This direction is not selected, if exists, delete it:
        #     # #                 if self.gutils.execute(select_qry, (levee_grid, 3)).fetchone():
        #     #                 self.gutils.execute(delete_qry, (levee_grid, 3))
        #     #                 self.gutils.execute(delete_failure_qry, (levee_grid, 3))
        #     #
        #     #
        #     #
        #     #
        #     #             if self.W_chbox.isChecked():
        #     #                 # Does this direction exists for this cell? If so update, otherwise insert:
        #     #                 if self.gutils.execute(select_qry, (levee_grid, 4)).fetchone():
        #     #                    self.gutils.execute(update_qry, (4, self.W_dbox.value(), int(levee_grid), 4))
        #     #                 else:
        #     #                     self.gutils.execute(insert_qry, (4,self.W_dbox.value(), levee_grid))
        #     #             else:
        #     #                 # This direction is not selected, if exists, delete it:
        #     # #                 if self.gutils.execute(select_qry, (levee_grid, 4)).fetchone():
        #     #                 self.gutils.execute(delete_qry, (levee_grid, 4))
        #     #                 self.gutils.execute(delete_failure_qry, (levee_grid, 4))
        #     #
        #     #
        #     #
        #     #
        #     #             if self.NE_chbox.isChecked():
        #     #                 # Does this direction exists for this cell? If so update, otherwise insert:
        #     #                 if  self.gutils.execute(select_qry, (levee_grid, 5)).fetchone():
        #     #                    self.gutils.execute(update_qry, (5, self.NE_dbox.value(), int(levee_grid), 5))
        #     #                 else:
        #     #                     self.gutils.execute(insert_qry, (5,self.NE_dbox.value(), levee_grid))
        #     #             else:
        #     #                 # This direction is not selected, if exists, delete it:
        #     # #                 if self.gutils.execute(select_qry, (levee_grid, 5)).fetchone():
        #     #                 self.gutils.execute(delete_qry, (levee_grid, 5))
        #     #                 self.gutils.execute(delete_failure_qry, (levee_grid, 5))
        #     #
        #     #
        #     #
        #     #
        #     #             if self.SE_chbox.isChecked():
        #     #                 # Does this direction exists for this cell? If so update, otherwise insert:
        #     #                 if self.gutils.execute(select_qry, (levee_grid, 6)).fetchone():
        #     #                    self.gutils.execute(update_qry, (6, self.SE_dbox.value(), int(levee_grid), 6))
        #     #                 else:
        #     #                     self.gutils.execute(insert_qry, (6,self.SE_dbox.value(), levee_grid))
        #     #             else:
        #     #                 # This direction is not selected, if exists, delete it:
        #     # #                 if self.gutils.execute(select_qry, (levee_grid, 6)).fetchone():
        #     #                 self.gutils.execute(delete_qry, (levee_grid, 6))
        #     #                 self.gutils.execute(delete_failure_qry, (levee_grid, 6))
        #     #
        #     #
        #     #
        #     #
        #     #             if self.SW_chbox.isChecked():
        #     #                 # Does this direction exists for this cell? If so update, otherwise insert:
        #     #                 if self.gutils.execute(select_qry, (levee_grid, 7)).fetchone():
        #     #                    self.gutils.execute(update_qry, (7, self.SW_dbox.value(), int(levee_grid), 7))
        #     #                 else:
        #     #                     self.gutils.execute(insert_qry, (7,self.SW_dbox.value(), levee_grid))
        #     #             else:
        #     #                 # If this direction is not selected and exists, delete it:
        #     # #                 if self.gutils.execute(select_qry, (levee_grid, 7)).fetchone():
        #     #                 self.gutils.execute(delete_qry, (levee_grid, 7))
        #     #                 self.gutils.execute(delete_failure_qry, (levee_grid, 7))
        #     #
        #     #
        #     #
        #     #
        #     #             if self.NW_chbox.isChecked():
        #     #                 # Does this direction exists for this cell? If so update, otherwise insert:
        #     #                 if self.gutils.execute(select_qry, (levee_grid, 8)).fetchone():
        #     #                    self.gutils.execute(update_qry, (8, self.NW_dbox.value(), int(levee_grid), 8))
        #     #                 else:
        #     #                     self.gutils.execute(insert_qry, (8,self.NW_dbox.value(), levee_grid))
        #     #             else:
        #     #                 # If this direction is not selected and exists, delete it:
        #     # #                 if self.gutils.execute(select_qry, (levee_grid, 8)).fetchone():
        #     #                 self.gutils.execute(delete_qry, (levee_grid, 8))
        #     #                 self.gutils.execute(delete_failure_qry, (levee_grid, 8))
        #
        #     self.uc.bar_info("Individual Levee Data for cell " + levee_grid + " saved.")
        #
        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.show_error(
        #         "ERROR 280319.1651: update of Individual Levee Data failed!"
        #         + "\n__________________________________________________",
        #         e,
        #     )
        #     return False
        #
        # try:
        #
        #     select_failure_qry = "SELECT * FROM levee_failure WHERE grid_fid = ? AND lfaildir = ?;"
        #     update_levee_failure_qry = """UPDATE levee_failure 
        #                                     SET failevel = ?, 
        #                                         failtime = ?, 
        #                                         levbase = ?, 
        #                                         failwidthmax  = ?, 
        #                                         failrate = ?, 
        #                                         failwidrate = ?
        #                                     WHERE grid_fid = ? AND lfaildir = ? ; """
        #
        #     insert_failure_qry = """INSERT INTO levee_failure
        #                      (grid_fid, lfaildir,  failevel, failtime, levbase, failwidthmax, failrate, failwidrate ) 
        #                     VALUES (?,?,?,?,?,?,?,?);"""
        #
        #     delete_failure_qry = "DELETE FROM levee_failure WHERE grid_fid = ? and lfaildir = ?;"
        #
        #     #             for f in self.failureData:
        #     #                 if f[0]:
        #     #
        #     #                 self.failureData[f[0]] = [True, f[1], f[2], f[3], f[4], f[5], f[6]]
        #
        #     #             if self.levee_failure_grp.isChecked():
        #     #                 # Does this failure exists for this cell, in this direction? If so update, otherwise insert:
        #     #                 if self.gutils.execute(select_failure_qry, (levee_grid, self.previousDirection) ).fetchone():
        #     #                     # Update:
        #     #                     self.gutils.execute(update_levee_failure_qry,
        #     #                                        (self.failure_elevation_dbox.value(),
        #     #                                         self.failure_duration_dbox.value(),
        #     #                                         self.failure_base_elevation_dbox.value(),
        #     #                                         self.failure_max_width_dbox.value(),
        #     #                                         self.failure_vertical_rate_dbox.value(),
        #     #                                         self.failure_horizontal_rate_dbox.value(),
        #     #                                         levee_grid, self.previousDirection
        #     #                                         ))
        #     #                 else:
        #     #                     # Insert:
        #     #                     self.gutils.execute(insert_failure_qry,
        #     #                                        (levee_grid,
        #     #                                         self.previousDirection,
        #     #                                         self.failure_elevation_dbox.value(),
        #     #                                         self.failure_duration_dbox.value(),
        #     #                                         self.failure_base_elevation_dbox.value(),
        #     #                                         self.failure_max_width_dbox.value(),
        #     #                                         self.failure_vertical_rate_dbox.value(),
        #     #                                         self.failure_horizontal_rate_dbox.value()
        #     #                                         ))
        #     #             else:
        #     #                 # If this direction is not selected and exists, delete it:
        #     #                 pass
        #     #                 if self.gutils.execute(select_failure_qry, (levee_grid, self.previousDirection) ).fetchone():
        #     #                     self.gutils.execute(delete_failure_qry, (levee_grid, self.previousDirection))
        #
        #     return True
        #
        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.show_error(
        #         "ERROR 290319.1204: error updating levee failures!"
        #         + "\n__________________________________________________",
        #         e,
        #     )
        #     return False

    def highlight_cell(self, cell):
        try:
            if self.grid_lyr is not None:
                #                 if self.grid_lyr:
                if cell != "":
                    cell = int(cell)
                    if self.grid_count >= cell and cell > 0:
                        self.lyrs.show_feat_rubber(self.grid_lyr.id(), cell, QColor(Qt.yellow))
                        feat = next(self.grid_lyr.getFeatures(QgsFeatureRequest(cell)))
                        x, y = feat.geometry().centroid().asPoint()
                        self.lyrs.zoom_to_all()
                        center_canvas(self.iface, x, y)
                        zoom(self.iface, 0.45)

                    else:
                        self.uc.bar_warn("WARNING 221219.1140: Cell " + str(cell) + " not found.")
                        self.lyrs.clear_rubber()
                else:
                    self.uc.bar_warn("WARNING 221219.1139: Cell " + str(cell) + " not found.")
                    self.lyrs.clear_rubber()
        except ValueError:
            self.uc.bar_warn("WARNING 221219.1134: Cell " + str(cell) + "is not valid.")
            self.lyrs.clear_rubber()
            pass

    def zoom_in(self):
        if self.currentCell:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = self.currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, 0.4)
            self.update_extent()
            QApplication.restoreOverrideCursor()

    def zoom_out(self):
        if self.currentCell:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            x, y = self.currentCell.geometry().centroid().asPoint()
            center_canvas(self.iface, x, y)
            zoom(self.iface, -0.4)
            self.update_extent()
            QApplication.restoreOverrideCursor()

    def update_extent(self):
        self.ext = self.iface.mapCanvas().extent()

    def find_levee_cell(self):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.grid_lyr is not None:
                if self.grid_lyr:
                    cell = self.cell_to_find_le.text()
                    if cell != "":
                        cell = int(cell)
                        if self.grid_count >= cell and cell > 0:
                            idx_all = [y[0] for y in self.levee_rows].index(cell)
                            if idx_all != -1:
                                idx_combo = self.individual_levee_element_cbo.findText(str(cell))
                                if idx_combo == -1:
                                    self.uc.bar_warn("WARNING 221219.1138: Cell " + str(cell) + " not in this group!.")
                                    frac, whole = modf(idx_all / self.n_levees)

                                    self.individual_levee_element_cbo.blockSignals(True)

                                    self.individual_levee_element_cbo.clear()
                                    begin = int(whole) * self.n_levees
                                    for i in range(begin, begin + self.n_levees):
                                        if i == len(self.levee_rows):
                                            break
                                        self.individual_levee_element_cbo.addItem(str(self.levee_rows[i][0]))
                                    idx_combo = self.individual_levee_element_cbo.findText(str(cell))

                                    # Set arrows in dialog:
                                    if whole == 0:
                                        self.previous_levees_btn.setEnabled(False)
                                        self.next_levees_btn.setEnabled(True)
                                    elif whole > 0 and whole < len(self.levee_rows) / self.n_levees:
                                        self.previous_levees_btn.setEnabled(True)
                                        self.next_levees_btn.setEnabled(True)
                                    elif whole >= len(self.levee_rows) / self.n_levees:
                                        self.previous_levees_btn.setEnabled(True)
                                        self.next_levees_btn.setEnabled(False)

                                    self.individual_levee_element_cbo.blockSignals(False)

                                self.individual_levee_element_cbo.setCurrentIndex(idx_combo)
                            else:
                                self.uc.bar_warn("WARNING 221219.1138: Cell " + str(cell) + " not found.")
                        else:
                            self.uc.bar_warn("WARNING 221219.1137: Cell " + str(cell) + " not found.")
                    else:
                        self.uc.bar_warn("WARNING 221219.1136: Cell " + str(cell) + " not found.")
        except ValueError:
            self.uc.bar_warn("WARNING 221219.1135: Cell " + str(cell) + " is not a levee cell.")
            pass
        finally:
            QApplication.restoreOverrideCursor()
