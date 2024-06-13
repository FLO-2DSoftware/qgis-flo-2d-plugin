# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QDockWidget

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version


from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication

uiDialog, qtBaseClass = load_ui("inlet_attributes")


class InletAttributes(qtBaseClass, uiDialog):
    def __init__(self, con, iface, layers):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = layers
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = con
        self.gutils = GeoPackageUtils(con, iface)

        # Create a dock widget
        self.dock_widget = QDockWidget("", self.iface.mainWindow())
        self.dock_widget.setObjectName("Inlets/Junctions")
        self.dock_widget.setWidget(self)

        self.current_node = None
        self.previous_node = None
        self.next_node = None

        # Connections
        self.name.editingFinished.connect(self.save_inlets_junctions)
        # self.external_inflow.editingFinished.connect(self.save_inlets_junctions)
        self.junction_invert_elev.editingFinished.connect(self.save_inlets_junctions)
        self.max_depth.editingFinished.connect(self.save_inlets_junctions)
        self.init_depth.editingFinished.connect(self.save_inlets_junctions)
        self.surcharge_depth.editingFinished.connect(self.save_inlets_junctions)
        self.sd_type.currentTextChanged.connect(self.save_inlets_junctions)
        self.intype.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_length.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_width.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_height.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_coeff.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_feature.editingFinished.connect(self.save_inlets_junctions)
        self.curbheight.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_clogging_factor.editingFinished.connect(self.save_inlets_junctions)
        self.swmm_time_for_clogging.editingFinished.connect(self.save_inlets_junctions)
        self.drboxarea.editingFinished.connect(self.save_inlets_junctions)

        self.user_swmm_nodes_lyr = self.lyrs.data["user_swmm_nodes"]["qlyr"]

        self.dock_widget.visibilityChanged.connect(self.clear_rubber)

        self.next_btn.clicked.connect(self.populate_next_node)
        self.previous_btn.clicked.connect(self.populate_previous_node)

    def populate_attributes(self, fid):
        """
        Function to populate the attributes
        """
        if not fid:
            return

        self.current_node = fid
        self.lyrs.show_feat_rubber(self.user_swmm_nodes_lyr.id(), fid, QColor(Qt.red))

        # Get the attributes
        attributes = self.gutils.execute(
                                            f"""SELECT 
                                                grid,
                                                name, 
                                                external_inflow, 
                                                junction_invert_elev, 
                                                max_depth,
                                                init_depth,
                                                surcharge_depth,
                                                sd_type,
                                                intype,
                                                swmm_length, 
                                                swmm_width, 
                                                swmm_height, 
                                                swmm_coeff, 
                                                swmm_feature,
                                                curbheight,
                                                swmm_clogging_factor, 
                                                swmm_time_for_clogging,
                                                drboxarea
                                            FROM
                                                user_swmm_nodes
                                            WHERE
                                                fid = {fid};"""
                                         ).fetchall()[0]

        # Assign attributes to the dialog
        self.grid.setText(str(attributes[0]))
        self.name.setText(str(attributes[1]))
        # self.external_inflow = attributes[2]
        self.junction_invert_elev.setValue(float(attributes[3]))
        self.max_depth.setValue(float(attributes[4]))
        self.init_depth.setValue(float(attributes[5]))
        self.surcharge_depth.setValue(float(attributes[6]))
        if str(attributes[7]).lower().startswith("i"):
            sd_type = 'Inlet'
        else:
            sd_type = 'Outlet'
        self.sd_type.setCurrentIndex(self.sd_type.findText(sd_type))
        self.intype.setValue(int(attributes[8]))
        self.swmm_length.setValue(float(attributes[9]))
        self.swmm_width.setValue(float(attributes[10]))
        self.swmm_height.setValue(float(attributes[11]))
        self.swmm_coeff.setValue(float(attributes[12]))
        self.swmm_feature.setValue(int(attributes[13]))
        self.curbheight.setValue(float(attributes[14]))
        self.swmm_clogging_factor.setValue(float(attributes[15]))
        self.swmm_time_for_clogging.setValue(float(attributes[16]))
        self.drboxarea.setValue(float(attributes[17]))

        self.previous_btn.setEnabled(False)
        self.next_btn.setEnabled(False)

        self.next_node = self.gutils.execute(
            f"""
            SELECT 
                conduit_inlet
            FROM 
                user_swmm_conduits
            WHERE 
                conduit_outlet = '{str(attributes[1])}' LIMIT 1;
            """
        ).fetchall()

        if self.next_node:
            self.next_btn.setEnabled(True)
            self.next_lbl.setText(self.next_node[0][0])

        self.previous_node = self.gutils.execute(
            f"""
            SELECT 
                conduit_outlet
            FROM 
                user_swmm_conduits
            WHERE 
                conduit_inlet = '{str(attributes[1])}' LIMIT 1;
            """
        ).fetchall()

        if self.previous_node:
            self.previous_btn.setEnabled(True)
            self.previous_lbl.setText(self.previous_node[0][0])

    def save_inlets_junctions(self):
        """
        Function to save the inlets everytime an attribute is changed
        """

        old_name_qry = self.gutils.execute(f"""SELECT name FROM user_swmm_nodes WHERE fid = '{self.current_node}';""").fetchall()
        old_name = ""
        if old_name_qry:
            old_name = old_name_qry[0][0]

        name = self.name.text()
        # external_inflow = self..value()
        junction_invert_elev = self.junction_invert_elev.value()
        max_depth = self.max_depth.value()
        init_depth = self.init_depth.value()
        surcharge_depth = self.surcharge_depth.value()
        sd_type = self.sd_type.currentText()[0]
        intype = self.intype.value()
        swmm_length = self.swmm_length.value()
        swmm_width = self.swmm_width.value()
        swmm_height = self.swmm_height.value()
        swmm_coeff = self.swmm_coeff.value()
        swmm_feature = self.swmm_feature.value()
        curbheight = self.curbheight.value()
        swmm_clogging_factor = self.swmm_clogging_factor.value()
        swmm_time_for_clogging = self.swmm_time_for_clogging.value()
        drboxarea = self.drboxarea.value()

        self.gutils.execute(f"""
                                UPDATE 
                                    user_swmm_nodes
                                SET 
                                    name = '{name}',
                                    junction_invert_elev = '{junction_invert_elev}',
                                    max_depth = '{max_depth}',
                                    init_depth = '{init_depth}',
                                    surcharge_depth = '{surcharge_depth}',
                                    sd_type = '{sd_type}',
                                    intype = '{intype}',
                                    swmm_length = '{swmm_length}', 
                                    swmm_width = '{swmm_width}', 
                                    swmm_height = '{swmm_height}', 
                                    swmm_coeff = '{swmm_coeff}', 
                                    swmm_feature = '{swmm_feature}',
                                    curbheight = '{curbheight}',
                                    swmm_clogging_factor = '{swmm_clogging_factor}', 
                                    swmm_time_for_clogging = '{swmm_time_for_clogging}',
                                    drboxarea = '{drboxarea}'
                                WHERE 
                                    fid = '{self.current_node}';
                            """)

        self.user_swmm_nodes_lyr.triggerRepaint()

        # update the name on the user_swmm_conduits
        if old_name != name:
            update_inlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_conduits
                WHERE 
                    conduit_inlet = '{old_name}';
                """
            ).fetchall()
            if update_inlets_qry:
                for inlet in update_inlets_qry:
                    self.gutils.execute(f"""
                                            UPDATE 
                                                user_swmm_conduits
                                            SET 
                                                conduit_inlet = '{name}'
                                            WHERE 
                                                fid = '{inlet[0]}';
                                        """)

            update_outlets_qry = self.gutils.execute(
                f"""
                SELECT 
                    fid
                FROM 
                    user_swmm_conduits
                WHERE 
                    conduit_outlet = '{old_name}';
                """
            ).fetchall()
            if update_outlets_qry:
                for outlet in update_outlets_qry:
                    self.gutils.execute(f"""
                                            UPDATE 
                                                user_swmm_conduits
                                            SET 
                                                conduit_outlet = '{name}'
                                            WHERE 
                                                fid = '{outlet[0]}';
                                        """)

    def dock_widget(self):
        """ Close and delete the dock widget. """
        if self.dock_widget:
            self.uc.log_info("TTteste")
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget.close()
            self.dock_widget.deleteLater()
            self.dock_widget = None

    def clear_rubber(self):
        """
        Function to clear the rubber when closing the widget
        """
        self.lyrs.clear_rubber()

    def populate_next_node(self):
        """
        Function to populate data when the user clicks on the next btn
        """
        next_node_name = self.next_lbl.text()

        fid = self.gutils.execute(
            f"""
            SELECT
                fid
            FROM
                user_swmm_nodes
            WHERE
                name = '{next_node_name}'
            """
        ).fetchone()

        if fid:
            self.populate_attributes(fid[0])

    def populate_previous_node(self):
        """
        Function to populate data when the user clicks on the previous btn
        """
        previous_node_name = self.previous_lbl.text()

        fid = self.gutils.execute(
            f"""
            SELECT
                fid
            FROM
                user_swmm_nodes
            WHERE
                name = '{previous_node_name}'
            """
        ).fetchone()

        if fid:
            self.populate_attributes(fid[0])

