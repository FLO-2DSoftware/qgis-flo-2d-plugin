# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.core import NULL, QgsFeature, QgsGeometry, QgsWkbTypes, QgsFieldProxyModel
from PyQt5.QtCore import QVariant
from qgis.gui import QgsFieldComboBox
from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtWidgets import QApplication, QComboBox, QDialogButtonBox

from ..flo2d_tools.schema2user_tools import remove_features
from ..geopackage_utils import GeoPackageUtils, extractPoints
from ..user_communication import UserCommunication
from ..utils import is_true
from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("storm_drain_shapefile")


class StormDrainShapefile(qtBaseClass, uiDialog):
    def __init__(self, con, iface, layers):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = layers
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.con = con
        self.gutils = GeoPackageUtils(con, iface)
        self.user_swmm_nodes_lyr = self.lyrs.data["user_swmm_nodes"]["qlyr"]
        self.user_swmm_strge_units_lyr = self.lyrs.data["user_swmm_storage_units"]["qlyr"]
        self.user_swmm_conduits_lyr = self.lyrs.data["user_swmm_conduits"]["qlyr"]
        self.user_swmm_pumps_lyr = self.lyrs.data["user_swmm_pumps"]["qlyr"]
        self.user_swmm_orifices_lyr = self.lyrs.data["user_swmm_orifices"]["qlyr"]
        self.user_swmm_weirs_lyr = self.lyrs.data["user_swmm_weirs"]["qlyr"]
        self.current_lyr = None
        self.saveSelected = None
        self.TRUE = ("1", "YES", "Yes", "yes", "TRUE", "True", "true", "ON", "on")
        self.FALSE = ("0", "NO", "No", "FALSE", "False", "false", "OFF", "off", "Off")

        self.shape = (
            "CIRCULAR",
            "FORCE_MAIN",
            "FILLED_CIRCULAR",
            "RECT_CLOSED",
            "RECT_OPEN",
            "TRAPEZOIDAL",
            "TRIANGULAR",
            "HORIZ_ELLIPSE",
            "VERT_ELLIPSE",
            "ARCH",
            "PARABOLIC",
            "POWER",
            "RECT_TRIANGULAR",
            "RECT_ROUND",
            "MODBASKETHANDLE",
            "EGG",
            "HORSESHOE",
            "GOTHIC",
            "CATENARY",
            "SEMIELLIPTICAL",
            "BASKETHANDLE",
            "SEMICIRCULAR",
        )

        self.SDSF_buttonBox.button(QDialogButtonBox.Save).setText("Assign Selected Fields")
        self.inlets_shapefile_cbo.currentIndexChanged.connect(self.populate_inlet_attributes)
        self.outfalls_shapefile_cbo.currentIndexChanged.connect(self.populate_outfall_attributes)
        self.strge_units_shapefile_cbo.currentIndexChanged.connect(self.populate_strge_units_attributes)
        self.conduits_shapefile_cbo.currentIndexChanged.connect(self.populate_conduit_attributes)
        self.pumps_shapefile_cbo.currentIndexChanged.connect(self.populate_pump_attributes)
        self.orifices_shapefile_cbo.currentIndexChanged.connect(self.populate_orifices_attributes)
        self.weirs_shapefile_cbo.currentIndexChanged.connect(self.populate_weirs_attributes)

        # Connections to clear inlets fields.
        self.clear_inlets_name_btn.clicked.connect(self.clear_inlets_name)
        self.clear_inlets_type_btn.clicked.connect(self.clear_inlets_type)
        self.clear_inlets_invert_elev_btn.clicked.connect(self.clear_inlets_invert_elevation)
        self.clear_inlets_max_depth_btn.clicked.connect(self.clear_inlets_max_depth)
        self.clear_inlets_init_depth_btn.clicked.connect(self.clear_inlets_init_depth)
        self.clear_inlets_surcharge_depth_btn.clicked.connect(self.clear_inlets_surcharge_dept)
        self.clear_inlets_length_perimeter_btn.clicked.connect(self.clear_inlets_length_perimeter)
        self.clear_inlets_width_area_btn.clicked.connect(self.clear_inlets_width_area)
        self.clear_inlets_height_sag_surch_btn.clicked.connect(self.clear_inlets_height_sag_surch)
        self.clear_inlets_weir_coeff_btn.clicked.connect(self.clear_inlets_weir_coeff)
        self.clear_inlets_feature_btn.clicked.connect(self.clear_inlets_feature)
        self.clear_inlets_curb_height_btn.clicked.connect(self.clear_inlets_curb_height)
        self.clear_inlets_clogging_factor_btn.clicked.connect(self.clear_inlets_clogging_factor)
        self.clear_inlets_time_for_clogging_btn.clicked.connect(self.clear_inlets_time_for_clogging)
        self.clear_inlets_dropbox_area_btn.clicked.connect(self.clear_inlets_dropbox_area)

        # Connections to clear outfalls fields.
        self.clear_outfall_name_btn.clicked.connect(self.clear_outfall_name)
        self.clear_outfall_invert_elevation_btn.clicked.connect(self.clear_outfall_invert_elevation)
        self.clear_outfall_flap_gate_btn.clicked.connect(self.clear_outfall_flap_gate)
        self.clear_outfall_allow_discharge_btn.clicked.connect(self.clear_outfall_allow_discharge)
        self.clear_outfall_type_btn.clicked.connect(self.clear_outfall_type)
        self.clear_outfall_water_depth_btn.clicked.connect(self.clear_outfall_water_depth)
        self.clear_outfall_tidal_curve_btn.clicked.connect(self.clear_outfall_tidal_curve)
        self.clear_outfall_time_series_btn.clicked.connect(self.clear_outfall_time_series)

        # Connections to clear storage units fields.
        self.clear_strge_unit_name_btn.clicked.connect(lambda: self.clear_fieldCombo(self.strge_unit_name_FieldCbo))
        self.clear_strge_unit_invert_elevation_btn.clicked.connect(
            lambda: self.clear_fieldCombo(self.strge_unit_invert_elevation_FieldCbo))
        self.clear_strge_unit_max_depth_btn.clicked.connect(
            lambda: self.clear_fieldCombo(self.strge_unit_max_depth_FieldCbo))
        self.clear_strge_unit_initial_depth_btn.clicked.connect(
            lambda: self.clear_fieldCombo(self.strge_unit_initial_depth_FieldCbo))
        self.clear_strge_unit_external_inflow_btn.clicked.connect(
            lambda: self.clear_fieldCombo(self.strge_unit_external_inflow_FieldCbo))
        # self.clear_strge_unit_ponded_area_btn.clicked.connect(
        #     lambda: self.clear_fieldCombo(self.strge_unit_ponded_area_FieldCbo))
        self.clear_strge_unit_evap_factor_btn.clicked.connect(
            lambda: self.clear_fieldCombo(self.strge_unit_evap_factor_FieldCbo))
        self.clear_strge_unit_treatment_btn.clicked.connect(
            lambda: self.clear_fieldCombo(self.strge_unit_treatment_FieldCbo))
        self.clear_strge_unit_infiltration_btn.clicked.connect(
            lambda: self.clear_fieldCombo(self.strge_unit_infiltration_FieldCbo))
        self.clear_strge_infil_method_btn.clicked.connect(
            lambda: self.clear_fieldCombo(self.strge_unit_infil_method_FieldCbo))
        self.clear_strge_unit_suction_head_btn.clicked.connect(
            lambda: self.clear_fieldCombo(self.strge_unit_suction_head_FieldCbo))
        self.clear_strge_unit_conductivity_btn.clicked.connect(
            lambda: self.clear_fieldCombo(self.strge_unit_conductivity_FieldCbo))
        self.clear_strge_unit_initial_deficit_btn.clicked.connect(
            lambda: self.clear_fieldCombo(self.strge_unit_initial_deficit_FieldCbo))
        self.clear_strge_storage_curve_btn.clicked.connect(
            lambda: self.clear_fieldCombo(self.strge_unit_storage_curve_FieldCbo))
        self.clear_strge_unit_coefficient_btn.clicked.connect(
            lambda: self.clear_fieldCombo(self.strge_unit_coefficient_FieldCbo))
        self.clear_strge_unit_exponent_btn.clicked.connect(
            lambda: self.clear_fieldCombo(self.strge_unit_exponent_FieldCbo))
        self.clear_strge_unit_constant_btn.clicked.connect(
            lambda: self.clear_fieldCombo(self.strge_unit_constant_FieldCbo))
        self.clear_strge_unit_curve_name_btn.clicked.connect(
            lambda: self.clear_fieldCombo(self.strge_unit_curve_name_FieldCbo))

        # Connections to clear conduits fields.
        self.clear_conduit_name_btn.clicked.connect(self.clear_conduit_name)
        self.clear_conduit_from_inlet_btn.clicked.connect(self.clear_conduit_from_inlet)
        self.clear_conduit_to_outlet_btn.clicked.connect(self.clear_conduit_to_outlet)
        self.clear_conduit_inlet_offset_btn.clicked.connect(self.clear_conduit_inlet_offset)
        self.clear_conduit_outlet_offset_btn.clicked.connect(self.clear_conduit_outlet_offset)
        self.clear_conduit_shape_btn.clicked.connect(self.clear_conduit_shape)
        self.clear_conduit_barrels_btn.clicked.connect(self.clear_conduit_barrels)
        self.clear_conduit_max_depth_btn.clicked.connect(self.clear_conduit_max_depth)
        self.clear_conduit_geom2_btn.clicked.connect(self.clear_conduit_geom2)
        self.clear_conduit_geom3_btn.clicked.connect(self.clear_conduit_geom3)
        self.clear_conduit_geom4_btn.clicked.connect(self.clear_conduit_geom4)
        self.clear_conduit_length_btn.clicked.connect(self.clear_conduit_length)
        self.clear_conduit_manning_btn.clicked.connect(self.clear_conduit_manning)
        self.clear_conduit_initial_flow_btn.clicked.connect(self.clear_conduit_initial_flow)
        self.clear_conduit_max_flow_btn.clicked.connect(self.clear_conduit_max_flow)
        self.clear_conduit_entry_loss_btn.clicked.connect(self.clear_conduit_entry_loss)
        self.clear_conduit_exit_loss_btn.clicked.connect(self.clear_conduit_exit_loss)
        self.clear_conduit_average_loss_btn.clicked.connect(self.clear_conduit_average_loss)
        self.clear_conduit_flap_gate_btn.clicked.connect(self.clear_conduit_flap_gate)

        # Connections to clear pump fields.
        self.clear_pump_name_btn.clicked.connect(self.clear_pump_name)
        self.clear_pump_from_inlet_btn.clicked.connect(self.clear_pump_from_inlet)
        self.clear_pump_to_outlet_btn.clicked.connect(self.clear_pump_to_outlet)
        self.clear_pump_initial_status_btn.clicked.connect(self.clear_pump_initial_status)
        self.clear_pump_startup_depth_btn.clicked.connect(self.clear_pump_startup_depth)
        self.clear_pump_shutoff_depth_btn.clicked.connect(self.clear_pump_shutoff_depth)
        self.clear_pump_curve_name_btn.clicked.connect(self.clear_pump_curve_name)
        self.clear_pump_curve_type_btn.clicked.connect(self.clear_pump_curve_type)
        self.clear_pump_curve_description_btn.clicked.connect(self.clear_pump_curve_description)

        # Connections to clear orifices fields.
        self.clear_orifice_name_btn.clicked.connect(self.clear_orifice_name)
        self.clear_orifice_from_inlet_btn.clicked.connect(self.clear_orifice_from_inlet)
        self.clear_orifice_to_outlet_btn.clicked.connect(self.clear_orifice_to_outlet)
        self.clear_orifice_type_btn.clicked.connect(self.clear_orifice_type)
        self.clear_orifice_crest_height_btn.clicked.connect(self.clear_orifice_crest_height)
        self.clear_orifice_discharge_coeff_btn.clicked.connect(self.clear_orifice_discharge_coeff)
        self.clear_orifice_flap_gate_btn.clicked.connect(self.clear_orifice_flap_gate)
        self.clear_orifice_time_open_close_btn.clicked.connect(self.clear_orifice_time_open_close)
        self.clear_orifice_shape_btn.clicked.connect(self.clear_orifice_shape)
        self.clear_orifice_height_btn.clicked.connect(self.clear_orifice_height)
        self.clear_orifice_width_btn.clicked.connect(self.clear_orifice_width)

        # Connections to clear weirs fields.
        self.clear_weir_name_btn.clicked.connect(self.clear_weir_name)
        self.clear_weir_from_inlet_btn.clicked.connect(self.clear_weir_from_inlet)
        self.clear_weir_to_outlet_btn.clicked.connect(self.clear_weir_to_outlet)
        self.clear_weir_type_btn.clicked.connect(self.clear_weir_type)
        self.clear_weir_crest_height_btn.clicked.connect(self.clear_weir_crest_height)
        self.clear_weir_discharge_coeff_btn.clicked.connect(self.clear_weir_discharge_coeff)
        self.clear_weir_flap_gate_btn.clicked.connect(self.clear_weir_flap_gate)
        self.clear_weir_end_contrac_btn.clicked.connect(self.clear_weir_end_contrac)
        self.clear_weir_end_coeff_btn.clicked.connect(self.clear_weir_end_coeff)
        self.clear_weir_side_slope_btn.clicked.connect(self.clear_weir_side_slope)
        self.clear_weir_shape_btn.clicked.connect(self.clear_weir_shape)
        self.clear_weir_height_btn.clicked.connect(self.clear_weir_height)
        self.clear_weir_length_btn.clicked.connect(self.clear_weir_length)

        self.clear_all_inlets_btn.clicked.connect(self.clear_all_inlet_attributes)
        self.clear_all_outfalls_btn.clicked.connect(self.clear_all_outfall_attributes)
        self.clear_all_strge_units_btn.clicked.connect(self.clear_all_strge_units_attributes)
        self.clear_all_conduits_btn.clicked.connect(self.clear_all_conduit_attributes)
        self.clear_all_pumps_btn.clicked.connect(self.clear_all_pump_attributes)
        self.clear_all_orifices_btn.clicked.connect(self.clear_all_orifice_attributes)
        self.clear_all_weirs_btn.clicked.connect(self.clear_all_weir_attributes)

        self.SDSF_buttonBox.accepted.connect(self.assign_components_from_shapefile)
        self.SDSF_buttonBox.rejected.connect(self.cancel_message)

        self.load_inlets = False
        self.load_outfalls = False
        self.load_strge_units = False
        self.load_conduits = False
        self.load_pumps = False
        self.load_orifices = False
        self.load_weirs = False
        self.no_in_out = ""

        self.unit = int(self.gutils.get_cont_par("METRIC"))

        self.setup_layers_comboxes()

        self.restore_storm_drain_shapefile_fields()

    def setup_layers_comboxes(self):
        try:
            
            self.inlets_shapefile_cbo.blockSignals(True)
            self.outfalls_shapefile_cbo.blockSignals(True)
            self.strge_units_shapefile_cbo.blockSignals(True)
            self.conduits_shapefile_cbo.blockSignals(True)
            self.pumps_shapefile_cbo.blockSignals(True)
            self.orifices_shapefile_cbo.blockSignals(True)
            self.weirs_shapefile_cbo.blockSignals(True)
            
            lyrs = self.lyrs.list_group_vlayers()
            for l in lyrs:
                if l.geometryType() == QgsWkbTypes.PointGeometry:
                    if l.featureCount() > 0:
                        self.inlets_shapefile_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
                        self.outfalls_shapefile_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
                        self.strge_units_shapefile_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())

                if l.geometryType() == QgsWkbTypes.LineGeometry:
                    if l.featureCount() > 0:
                        self.conduits_shapefile_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
                        self.pumps_shapefile_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
                        self.orifices_shapefile_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
                        self.weirs_shapefile_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
                else:
                    pass



            sf_inlets_layer_name = self.gutils.execute(f"SELECT field FROM sd_fields WHERE name = 'sf_inlets_layer_name'").fetchone()
            previous_inlet = "" if sf_inlets_layer_name is None else sf_inlets_layer_name[0]
            idx = self.inlets_shapefile_cbo.findText(previous_inlet)
            if idx != -1:
                self.inlets_shapefile_cbo.setCurrentIndex(idx)
                self.populate_inlet_attributes(self.inlets_shapefile_cbo.currentIndex())
            else:
                self.inlets_shapefile_cbo.setCurrentIndex(idx)

            sf_outfalls_layer_name = self.gutils.execute(f"SELECT field FROM sd_fields WHERE name = 'sf_outfalls_layer_name'").fetchone()
            previous_outfall = "" if sf_outfalls_layer_name is None else sf_outfalls_layer_name[0]
            idx = self.outfalls_shapefile_cbo.findText(previous_outfall)
            if idx != -1:
                self.outfalls_shapefile_cbo.setCurrentIndex(idx)
                self.populate_outfall_attributes(self.outfalls_shapefile_cbo.currentIndex())
            else:
                self.outfalls_shapefile_cbo.setCurrentIndex(idx)

            sf_strge_units_layer_name = self.gutils.execute(f"SELECT field FROM sd_fields WHERE name = 'sf_strge_units_layer_name'").fetchone()
            previous_strge_unit = "" if sf_strge_units_layer_name is None else sf_strge_units_layer_name[0]
            idx = self.strge_units_shapefile_cbo.findText(previous_strge_unit)
            if idx != -1:
                self.strge_units_shapefile_cbo.setCurrentIndex(idx)
                self.populate_strge_units_attributes(self.strge_units_shapefile_cbo.currentIndex())
            else:
                self.strge_units_shapefile_cbo.setCurrentIndex(idx)

            sf_conduits_layer_name = self.gutils.execute(f"SELECT field FROM sd_fields WHERE name = 'sf_conduits_layer_name'").fetchone()
            previous_conduit = "" if sf_conduits_layer_name is None else sf_conduits_layer_name[0]
            idx = self.conduits_shapefile_cbo.findText(previous_conduit)
            if idx != -1:
                self.conduits_shapefile_cbo.setCurrentIndex(idx)
                self.populate_conduit_attributes(self.conduits_shapefile_cbo.currentIndex())
            else:
                self.conduits_shapefile_cbo.setCurrentIndex(idx)

            sf_pumps_layer_name = self.gutils.execute(f"SELECT field FROM sd_fields WHERE name = 'sf_pumps_layer_name'").fetchone()
            previous_pump = "" if sf_pumps_layer_name is None else sf_pumps_layer_name[0]
            idx = self.pumps_shapefile_cbo.findText(previous_pump)
            if idx != -1:
                self.pumps_shapefile_cbo.setCurrentIndex(idx)
                self.populate_pump_attributes(self.pumps_shapefile_cbo.currentIndex())
            else:
                self.pumps_shapefile_cbo.setCurrentIndex(idx)

            sf_orifices_layer_name = self.gutils.execute(f"SELECT field FROM sd_fields WHERE name = 'sf_orifices_layer_name'").fetchone()
            previous_orifice = "" if sf_orifices_layer_name is None else sf_orifices_layer_name[0]
            idx = self.orifices_shapefile_cbo.findText(previous_orifice)
            if idx != -1:
                self.orifices_shapefile_cbo.setCurrentIndex(idx)
                self.populate_orifices_attributes(self.orifices_shapefile_cbo.currentIndex())
            else:
                self.orifices_shapefile_cbo.setCurrentIndex(idx)

            sf_weirs_layer_name = self.gutils.execute(f"SELECT field FROM sd_fields WHERE name = 'sf_weirs_layer_name'").fetchone()
            previous_weir = "" if sf_weirs_layer_name is None else sf_weirs_layer_name[0]
            idx = self.weirs_shapefile_cbo.findText(previous_weir)
            if idx != -1:
                self.weirs_shapefile_cbo.setCurrentIndex(idx)
                self.populate_weirs_attributes(self.weirs_shapefile_cbo.currentIndex())
            else:
                self.weirs_shapefile_cbo.setCurrentIndex(idx)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 051218.1146: couldn't load point or/and line layers!"
                + "\n__________________________________________________",
                e,
            )
            
        finally:
            self.inlets_shapefile_cbo.blockSignals(False)
            self.outfalls_shapefile_cbo.blockSignals(False)
            self.strge_units_shapefile_cbo.blockSignals(False)
            self.conduits_shapefile_cbo.blockSignals(False)
            self.pumps_shapefile_cbo.blockSignals(False)
            self.orifices_shapefile_cbo.blockSignals(False)
            self.weirs_shapefile_cbo.blockSignals(False)               

    def populate_inlet_attributes(self, idx):
        try:
            if idx == -1:
                return
            uri = self.inlets_shapefile_cbo.itemData(idx)
            lyr_id = self.lyrs.layer_exists_in_group(uri)
            self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()

            # List of combo boxes that should be filtered to string fields:
            string_combos = [self.inlets_fields_groupBox.findChild(QgsFieldComboBox, 'inlets_name_FieldCbo')                            
                             ]
            
            # List of combo boxes that should be filtered to numeric fields:
            numeric_combos = [self.inlets_fields_groupBox.findChild(QgsFieldComboBox, 'inlets_invert_elevation_FieldCbo'), 
                              self.inlets_fields_groupBox.findChild(QgsFieldComboBox, 'inlets_max_depth_FieldCbo'),
                              self.inlets_fields_groupBox.findChild(QgsFieldComboBox, 'inlets_init_depth_FieldCbo'),
                              self.inlets_fields_groupBox.findChild(QgsFieldComboBox, 'inlets_surcharge_depth_FieldCbo'),
                              self.inlets_fields_groupBox.findChild(QgsFieldComboBox, 'inlets_weir_coeff_FieldCbo'), 
                              self.inlets_fields_groupBox.findChild(QgsFieldComboBox, 'inlets_feature_FieldCbo'),
                              self.inlets_fields_groupBox.findChild(QgsFieldComboBox, 'inlets_curb_height_FieldCbo'),
                              self.inlets_fields_groupBox.findChild(QgsFieldComboBox, 'inlets_clogging_factor_FieldCbo'),
                              self.inlets_fields_groupBox.findChild(QgsFieldComboBox, 'inlets_time_for_clogging_FieldCbo'),                              
                              self.inlets_fields_groupBox.findChild(QgsFieldComboBox, 'inlets_dropbox_area_FieldCbo'),
                              self.inlets_fields_groupBox.findChild(QgsFieldComboBox, 'inlets_length_perimeter_FieldCbo'),                              
                              self.inlets_fields_groupBox.findChild(QgsFieldComboBox, 'inlets_width_area_FieldCbo'),                              
                              self.inlets_fields_groupBox.findChild(QgsFieldComboBox, 'inlets_height_sag_surch_FieldCbo'),                              
                              self.inlets_fields_groupBox.findChild(QgsFieldComboBox, 'inlets_dropbox_area_FieldCbo'),                              
                              ]

            all_combos = [self.inlets_fields_groupBox.findChild(QgsFieldComboBox, 'inlets_type_FieldCbo')]            
            for combo in string_combos:
                combo.clear()
                combo.setLayer(self.current_lyr)
                combo.setFilters(QgsFieldProxyModel.String)  # Only show string fields
            
            for combo in numeric_combos:
                combo.clear()
                combo.setLayer(self.current_lyr)
                combo.setFilters(QgsFieldProxyModel.Numeric)  # Only show numeric fields
                
            for combo in all_combos:
                combo.clear()
                combo.setLayer(self.current_lyr)
                combo.setFilters(QgsFieldProxyModel.AllTypes)  # Show all types              
           
            nFeatures = self.current_lyr.featureCount()
            self.inlets_fields_groupBox.setTitle(
                "Inlets Fields Selection (from '"
                + self.inlets_shapefile_cbo.currentText()
                + "' layer with "
                + str(nFeatures)
                + " features (points))"
            )

            self.restore_SD_shapefile_inlet_field_names()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 051218.0559:  there are not defined or visible point layers to select inlets/junctions components!"
                + "\n__________________________________________________",
                e,
            )

    def populate_outfall_attributes(self, idx):
        try:
            if idx == -1:
                return
            
            uri = self.outfalls_shapefile_cbo.itemData(idx)
            lyr_id = self.lyrs.layer_exists_in_group(uri)
            self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()

            # List of combo boxes that should be filtered to string fields:
            string_combos = [self.outfalls_fields_groupBox.findChild(QgsFieldComboBox, 'outfall_name_FieldCbo'),
                             self.outfalls_fields_groupBox.findChild(QgsFieldComboBox, 'outfall_flap_gate_FieldCbo'),
                             self.outfalls_fields_groupBox.findChild(QgsFieldComboBox, 'outfall_type_FieldCbo'),
                             self.outfalls_fields_groupBox.findChild(QgsFieldComboBox, 'outfall_allow_discharge_FieldCbo'),
                             self.outfalls_fields_groupBox.findChild(QgsFieldComboBox, 'outfall_tidal_curve_FieldCbo'),
                             self.outfalls_fields_groupBox.findChild(QgsFieldComboBox, 'outfall_time_series_FieldCbo')                             
                             ]
            
            # List of combo boxes that should be filtered to numeric fields:
            numeric_combos = [self.outfalls_fields_groupBox.findChild(QgsFieldComboBox, 'outfall_invert_elevation_FieldCbo'),    
                              self.outfalls_fields_groupBox.findChild(QgsFieldComboBox, 'outfall_water_depth_FieldCbo'),
                              ]
            
            for combo in string_combos:
                combo.clear()
                combo.setLayer(self.current_lyr)
                combo.setFilters(QgsFieldProxyModel.String)  # Only show string fields
            
            for combo in numeric_combos:
                combo.clear()
                combo.setLayer(self.current_lyr)
                combo.setFilters(QgsFieldProxyModel.Numeric)  # Only show numeric fields
    
            nFeatures = self.current_lyr.featureCount()
            self.outfalls_fields_groupBox.setTitle(
                "Outfalls Fields Selection (from '"
                + self.outfalls_shapefile_cbo.currentText()
                + "' layer with "
                + str(nFeatures)
                + " features (points))"
            )

            self.restore_SD_shapefile_outfall_field_names()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 051218.0600: there are not defined or visible point layers to select outfall components!"
                + "\n__________________________________________________",
                e,
            )

    def populate_strge_units_attributes(self, idx):
        try:
            if idx == -1:
                return
            uri = self.strge_units_shapefile_cbo.itemData(idx)
            lyr_id = self.lyrs.layer_exists_in_group(uri)
            self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()

            # List of combo boxes that should be filtered to string fields:
            string_combos = [self.strge_unit_fields_groupBox.findChild(QgsFieldComboBox, 'strge_unit_name_FieldCbo'),
                             self.strge_unit_fields_groupBox.findChild(QgsFieldComboBox, 'strge_unit_external_inflow_FieldCbo'), 
                             self.strge_unit_fields_groupBox.findChild(QgsFieldComboBox, 'strge_unit_treatment_FieldCbo'),                         
                             self.strge_unit_fields_groupBox.findChild(QgsFieldComboBox, 'strge_unit_infiltration_FieldCbo'),                         
                             self.strge_unit_fields_groupBox.findChild(QgsFieldComboBox, 'strge_unit_infil_method_FieldCbo'),                         
                             self.strge_unit_fields_groupBox.findChild(QgsFieldComboBox, 'strge_unit_storage_curve_FieldCbo'),                         
                             self.strge_unit_fields_groupBox.findChild(QgsFieldComboBox, 'strge_unit_curve_name_FieldCbo'),                         

                             ]
            
            # List of combo boxes that should be filtered to numeric fields:
            numeric_combos = [self.strge_unit_fields_groupBox.findChild(QgsFieldComboBox, 'strge_unit_invert_elevation_FieldCbo'),    
                              self.strge_unit_fields_groupBox.findChild(QgsFieldComboBox, 'strge_unit_max_depth_FieldCbo'),
                              self.strge_unit_fields_groupBox.findChild(QgsFieldComboBox, 'strge_unit_initial_depth_FieldCbo'),
                              self.strge_unit_fields_groupBox.findChild(QgsFieldComboBox, 'strge_unit_evap_factor_FieldCbo'), 
                              self.strge_unit_fields_groupBox.findChild(QgsFieldComboBox, 'strge_unit_suction_head_FieldCbo'),
                              self.strge_unit_fields_groupBox.findChild(QgsFieldComboBox, 'strge_unit_conductivity_FieldCbo'),
                              self.strge_unit_fields_groupBox.findChild(QgsFieldComboBox, 'strge_unit_initial_deficit_FieldCbo'),
                              self.strge_unit_fields_groupBox.findChild(QgsFieldComboBox, 'strge_unit_coefficient_FieldCbo'),                              
                              self.strge_unit_fields_groupBox.findChild(QgsFieldComboBox, 'strge_unit_exponent_FieldCbo'),
                              self.strge_unit_fields_groupBox.findChild(QgsFieldComboBox, 'strge_unit_constant_FieldCbo'),                                                        
                              ]
            
            for combo in string_combos:
                combo.clear()
                combo.setLayer(self.current_lyr)
                combo.setFilters(QgsFieldProxyModel.String)  # Only show string fields
            
            for combo in numeric_combos:
                combo.clear()
                combo.setLayer(self.current_lyr)
                combo.setFilters(QgsFieldProxyModel.Numeric)  # Only show numeric fields

            nFeatures = self.current_lyr.featureCount()
            self.strge_unit_fields_groupBox.setTitle(
                "Storage Units Fields Selection (from '"
                + self.strge_units_shapefile_cbo.currentText()
                + "' layer with "
                + str(nFeatures)
                + " features (points))"
            )

            self.restore_SD_shapefile_strge_units_field_names()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 250424.1025: there are not defined or visible point layers to select storage units components!"
                + "\n__________________________________________________",
                e,
            )

    def populate_conduit_attributes(self, idx):
        try:
            if idx == -1:
                return
            uri = self.conduits_shapefile_cbo.itemData(idx)
            lyr_id = self.lyrs.layer_exists_in_group(uri)
            self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()

            # List of combo boxes that should be filtered to string fields:
            string_combos = [self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_name_FieldCbo'),
                             self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_from_inlet_FieldCbo'), 
                             self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_to_outlet_FieldCbo'),                         
                             self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_shape_FieldCbo'),                         
                             self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_flap_gate_FieldCbo'),                                                
                             ]
            
            # List of combo boxes that should be filtered to numeric fields:
            numeric_combos = [self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_inlet_offset_FieldCbo'),    
                              self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_outlet_offset_FieldCbo'),
                              self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_barrels_FieldCbo'),
                              self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_max_depth_FieldCbo'), 
                              self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_geom2_FieldCbo'),
                              self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_geom3_FieldCbo'),
                              self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_geom4_FieldCbo'),
                              self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_length_FieldCbo'),                              
                              self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_manning_FieldCbo'),
                              self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_initial_flow_FieldCbo'),
                              self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_max_flow_FieldCbo'),                              
                              self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_entry_loss_FieldCbo'),
                              self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_exit_loss_FieldCbo'),  
                              self.conduits_fields_groupBox.findChild(QgsFieldComboBox, 'conduit_average_loss_FieldCbo'),                              
                              ]
            
            for combo in string_combos:
                combo.clear()
                combo.setLayer(self.current_lyr)
                combo.setFilters(QgsFieldProxyModel.String)  # Only show string fields
            
            for combo in numeric_combos:
                combo.clear()
                combo.setLayer(self.current_lyr)
                combo.setFilters(QgsFieldProxyModel.Numeric)  # Only show numeric fields

            nFeatures = self.current_lyr.featureCount()
            self.conduits_fields_groupBox.setTitle(
                "Conduits Fields Selection (from '"
                + self.conduits_shapefile_cbo.currentText()
                + "' layer with "
                + str(nFeatures)
                + " features (lines))"
            )

            self.restore_SD_shapefile_conduit_field_names()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 051218.0601: there are not defined or visible line layers to select conduits components!"
                + "\n__________________________________________________",
                e,
            )

    def populate_pump_attributes(self, idx):
        try:
            if idx == -1:
                return
            uri = self.pumps_shapefile_cbo.itemData(idx)
            lyr_id = self.lyrs.layer_exists_in_group(uri)
            self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()

            # List of combo boxes that should be filtered to string fields:
            string_combos = [self.pumps_fields_groupBox.findChild(QgsFieldComboBox, 'pump_name_FieldCbo'),
                             self.pumps_fields_groupBox.findChild(QgsFieldComboBox, 'pump_from_inlet_FieldCbo'), 
                             self.pumps_fields_groupBox.findChild(QgsFieldComboBox, 'pump_to_outlet_FieldCbo'),                         
                             self.pumps_fields_groupBox.findChild(QgsFieldComboBox, 'pump_curve_name_FieldCbo'),                         
                             self.pumps_fields_groupBox.findChild(QgsFieldComboBox, 'pump_initial_status_FieldCbo')                                                
                             ]
            
            # List of combo boxes that should be filtered to numeric fields:
            numeric_combos = [self.pumps_fields_groupBox.findChild(QgsFieldComboBox, 'pump_startup_depth_FieldCbo'),    
                              self.pumps_fields_groupBox.findChild(QgsFieldComboBox, 'pump_shutoff_depth_FieldCbo')                           
                              ]
            
            for combo in string_combos:
                combo.clear()
                combo.setLayer(self.current_lyr)
                combo.setFilters(QgsFieldProxyModel.String)  # Only show string fields
            
            for combo in numeric_combos:
                combo.clear()
                combo.setLayer(self.current_lyr)
                combo.setFilters(QgsFieldProxyModel.Numeric)  # Only show numeric fields

            nFeatures = self.current_lyr.featureCount()
            self.pumps_fields_groupBox.setTitle(
                "Pumps Fields Selection (from '"
                + self.pumps_shapefile_cbo.currentText()
                + "' layer with "
                + str(nFeatures)
                + " features (lines))"
            )

            self.restore_SD_shapefile_pump_field_names()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 230222.0953: there are not defined or visible line layers to select pumps components!"
                + "\n__________________________________________________",
                e,
            )

    def populate_orifices_attributes(self, idx):
        try:
            if idx == -1:
                return
            uri = self.orifices_shapefile_cbo.itemData(idx)
            lyr_id = self.lyrs.layer_exists_in_group(uri)
            self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()

            # List of combo boxes that should be filtered to string fields:
            string_combos = [self.orifices_fields_groupBox.findChild(QgsFieldComboBox, 'orifice_name_FieldCbo'),
                             self.orifices_fields_groupBox.findChild(QgsFieldComboBox, 'orifice_from_inlet_FieldCbo'), 
                             self.orifices_fields_groupBox.findChild(QgsFieldComboBox, 'orifice_to_outlet_FieldCbo'),                         
                             self.orifices_fields_groupBox.findChild(QgsFieldComboBox, 'orifice_type_FieldCbo'),                         
                             self.orifices_fields_groupBox.findChild(QgsFieldComboBox, 'orifice_flap_gate_FieldCbo'),
                             self.orifices_fields_groupBox.findChild(QgsFieldComboBox, 'orifice_shape_FieldCbo')                                              


                             ]
            
            # List of combo boxes that should be filtered to numeric fields:
            numeric_combos = [self.orifices_fields_groupBox.findChild(QgsFieldComboBox, 'orifice_crest_height_FieldCbo'),    
                              self.orifices_fields_groupBox.findChild(QgsFieldComboBox, 'orifice_discharge_coeff_FieldCbo'),
                              self.orifices_fields_groupBox.findChild(QgsFieldComboBox, 'orifice_time_open_close_FieldCbo'),
                              self.orifices_fields_groupBox.findChild(QgsFieldComboBox, 'orifice_height_FieldCbo'), 
                              self.orifices_fields_groupBox.findChild(QgsFieldComboBox, 'orifice_width_FieldCbo')                           
                              ]
            
            for combo in string_combos:
                combo.clear()
                combo.setLayer(self.current_lyr)
                combo.setFilters(QgsFieldProxyModel.String)  # Only show string fields
            
            for combo in numeric_combos:
                combo.clear()
                combo.setLayer(self.current_lyr)
                combo.setFilters(QgsFieldProxyModel.Numeric)  # Only show numeric fields

            nFeatures = self.current_lyr.featureCount()
            self.orifices_fields_groupBox.setTitle(
                "Orifices Fields Selection (from '"
                + self.orifices_shapefile_cbo.currentText()
                + "' layer with "
                + str(nFeatures)
                + " features (lines))"
            )

            self.restore_SD_shapefile_orifice_field_names()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 230222.0954: there are not defined or visible line layers to select orifice components!"
                + "\n__________________________________________________",
                e,
            )

    def populate_weirs_attributes(self, idx):
        try:
            if idx == -1:
                return
            uri = self.weirs_shapefile_cbo.itemData(idx)
            lyr_id = self.lyrs.layer_exists_in_group(uri)
            self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()

            # List of combo boxes that should be filtered to string fields:
            string_combos = [self.weirs_fields_groupBox.findChild(QgsFieldComboBox, 'weir_name_FieldCbo'),
                             self.weirs_fields_groupBox.findChild(QgsFieldComboBox, 'weir_from_inlet_FieldCbo'), 
                             self.weirs_fields_groupBox.findChild(QgsFieldComboBox, 'weir_to_outlet_FieldCbo'),                         
                             self.weirs_fields_groupBox.findChild(QgsFieldComboBox, 'weir_type_FieldCbo'),                         
                             self.weirs_fields_groupBox.findChild(QgsFieldComboBox, 'weir_flap_gate_FieldCbo'),                                    
                             self.weirs_fields_groupBox.findChild(QgsFieldComboBox, 'weir_shape_FieldCbo')
                             ]
            
            # List of combo boxes that should be filtered to numeric fields:
            numeric_combos = [self.weirs_fields_groupBox.findChild(QgsFieldComboBox, 'weir_crest_height_FieldCbo'),    
                              self.weirs_fields_groupBox.findChild(QgsFieldComboBox, 'weir_discharge_coeff_FieldCbo'),
                              self.weirs_fields_groupBox.findChild(QgsFieldComboBox, 'weir_end_contrac_FieldCbo'),     
                              self.weirs_fields_groupBox.findChild(QgsFieldComboBox, 'weir_end_coeff_FieldCbo'),
                              self.weirs_fields_groupBox.findChild(QgsFieldComboBox, 'weir_height_FieldCbo'), 
                              self.weirs_fields_groupBox.findChild(QgsFieldComboBox, 'weir_length_FieldCbo'),
                              self.weirs_fields_groupBox.findChild(QgsFieldComboBox, 'weir_side_slope_FieldCbo')
                              ]
            
            for combo in string_combos:
                combo.clear()
                combo.setLayer(self.current_lyr)
                combo.setFilters(QgsFieldProxyModel.String)  # Only show string fields
            
            for combo in numeric_combos:
                combo.clear()
                combo.setLayer(self.current_lyr)
                combo.setFilters(QgsFieldProxyModel.Numeric)  # Only show numeric fields

            nFeatures = self.current_lyr.featureCount()
            self.weirs_fields_groupBox.setTitle(
                "Weirs Fields Selection (from '"
                + self.weirs_shapefile_cbo.currentText()
                + "' layer with "
                + str(nFeatures)
                + " features (lines))"
            )

            self.restore_SD_shapefile_weir_field_names()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 120422.0508: there are not defined or visible line layers to select weir components!"
                + "\n__________________________________________________",
                e,
            )

    # CLEAR INLETS FIELDS:
    def clear_inlets_name(self):
        self.inlets_name_FieldCbo.setCurrentIndex(-1)

    def clear_inlets_type(self):
        self.inlets_type_FieldCbo.setCurrentIndex(-1)

    def clear_inlets_invert_elevation(self):
        self.inlets_invert_elevation_FieldCbo.setCurrentIndex(-1)

    def clear_inlets_max_depth(self):
        self.inlets_max_depth_FieldCbo.setCurrentIndex(-1)

    def clear_inlets_init_depth(self):
        self.inlets_init_depth_FieldCbo.setCurrentIndex(-1)

    def clear_inlets_surcharge_dept(self):
        self.inlets_surcharge_depth_FieldCbo.setCurrentIndex(-1)

    def clear_inlets_weir_coeff(self):
        self.inlets_weir_coeff_FieldCbo.setCurrentIndex(-1)

    def clear_inlets_feature(self):
        self.inlets_feature_FieldCbo.setCurrentIndex(-1)

    def clear_inlets_curb_height(self):
        self.inlets_curb_height_FieldCbo.setCurrentIndex(-1)

    def clear_inlets_clogging_factor(self):
        self.inlets_clogging_factor_FieldCbo.setCurrentIndex(-1)

    def clear_inlets_time_for_clogging(self):
        self.inlets_time_for_clogging_FieldCbo.setCurrentIndex(-1)

    def clear_inlets_dropbox_area(self):
        self.inlets_dropbox_area_FieldCbo.setCurrentIndex(-1)

    def clear_inlets_length_perimeter(self):
        self.inlets_length_perimeter_FieldCbo.setCurrentIndex(-1)

    def clear_inlets_width_area(self):
        self.inlets_width_area_FieldCbo.setCurrentIndex(-1)

    def clear_inlets_height_sag_surch(self):
        self.inlets_height_sag_surch_FieldCbo.setCurrentIndex(-1)

    # CLEAR OUTFALLS FIELDS:
    def clear_outfall_name(self):
        self.outfall_name_FieldCbo.setCurrentIndex(-1)

    def clear_outfall_invert_elevation(self):
        self.outfall_invert_elevation_FieldCbo.setCurrentIndex(-1)

    def clear_outfall_flap_gate(self):
        self.outfall_flap_gate_FieldCbo.setCurrentIndex(-1)

    def clear_outfall_allow_discharge(self):
        self.outfall_allow_discharge_FieldCbo.setCurrentIndex(-1)

    def clear_outfall_type(self):
        self.outfall_type_FieldCbo.setCurrentIndex(-1)

    def clear_outfall_water_depth(self):
        self.outfall_water_depth_FieldCbo.setCurrentIndex(-1)

    def clear_outfall_tidal_curve(self):
        self.outfall_tidal_curve_FieldCbo.setCurrentIndex(-1)

    def clear_outfall_time_series(self):
        self.outfall_time_series_FieldCbo.setCurrentIndex(-1)

    # CLEAR FIELDS:

    def clear_fieldCombo(self, fieldCombo):
        fieldCombo.setCurrentIndex(-1)

    # CLEAR CONDUITS FIELDS:

    def clear_conduit_name(self):
        self.conduit_name_FieldCbo.setCurrentIndex(-1)

    def clear_conduit_from_inlet(self):
        self.conduit_from_inlet_FieldCbo.setCurrentIndex(-1)

    def clear_conduit_to_outlet(self):
        self.conduit_to_outlet_FieldCbo.setCurrentIndex(-1)

    def clear_conduit_inlet_offset(self):
        self.conduit_inlet_offset_FieldCbo.setCurrentIndex(-1)

    def clear_conduit_outlet_offset(self):
        self.conduit_outlet_offset_FieldCbo.setCurrentIndex(-1)

    def clear_conduit_shape(self):
        self.conduit_shape_FieldCbo.setCurrentIndex(-1)

    def clear_conduit_barrels(self):
        self.conduit_barrels_FieldCbo.setCurrentIndex(-1)

    def clear_conduit_max_depth(self):
        self.conduit_max_depth_FieldCbo.setCurrentIndex(-1)

    def clear_conduit_geom2(self):
        self.conduit_geom2_FieldCbo.setCurrentIndex(-1)

    def clear_conduit_geom3(self):
        self.conduit_geom3_FieldCbo.setCurrentIndex(-1)

    def clear_conduit_geom4(self):
        self.conduit_geom4_FieldCbo.setCurrentIndex(-1)

    def clear_conduit_length(self):
        self.conduit_length_FieldCbo.setCurrentIndex(-1)

    def clear_conduit_manning(self):
        self.conduit_manning_FieldCbo.setCurrentIndex(-1)

    def clear_conduit_initial_flow(self):
        self.conduit_initial_flow_FieldCbo.setCurrentIndex(-1)

    def clear_conduit_max_flow(self):
        self.conduit_max_flow_FieldCbo.setCurrentIndex(-1)

    def clear_conduit_entry_loss(self):
        self.conduit_entry_loss_FieldCbo.setCurrentIndex(-1)

    def clear_conduit_exit_loss(self):
        self.conduit_exit_loss_FieldCbo.setCurrentIndex(-1)

    def clear_conduit_average_loss(self):
        self.conduit_average_loss_FieldCbo.setCurrentIndex(-1)

    def clear_conduit_flap_gate(self):
        self.conduit_flap_gate_FieldCbo.setCurrentIndex(-1)

    # CLEAR PUMPS FIELDS:

    def clear_pump_name(self):
        self.pump_name_FieldCbo.setCurrentIndex(-1)

    def clear_pump_from_inlet(self):
        self.pump_from_inlet_FieldCbo.setCurrentIndex(-1)

    def clear_pump_to_outlet(self):
        self.pump_to_outlet_FieldCbo.setCurrentIndex(-1)

    def clear_pump_initial_status(self):
        self.pump_initial_status_FieldCbo.setCurrentIndex(-1)

    def clear_pump_startup_depth(self):
        self.pump_startup_depth_FieldCbo.setCurrentIndex(-1)

    def clear_pump_shutoff_depth(self):
        self.pump_shutoff_depth_FieldCbo.setCurrentIndex(-1)

    def clear_pump_curve_name(self):
        self.pump_curve_name_FieldCbo.setCurrentIndex(-1)

    def clear_pump_curve_type(self):
        self.pump_curve_type_FieldCbo.setCurrentIndex(-1)

    def clear_pump_curve_description(self):
        self.pump_curve_description_FieldCbo.setCurrentIndex(-1)

    # CLEAR ORIFICE FIELDS:

    def clear_orifice_name(self):
        self.orifice_name_FieldCbo.setCurrentIndex(-1)

    def clear_orifice_from_inlet(self):
        self.orifice_from_inlet_FieldCbo.setCurrentIndex(-1)

    def clear_orifice_to_outlet(self):
        self.orifice_to_outlet_FieldCbo.setCurrentIndex(-1)

    def clear_orifice_type(self):
        self.orifice_type_FieldCbo.setCurrentIndex(-1)

    def clear_orifice_crest_height(self):
        self.orifice_crest_height_FieldCbo.setCurrentIndex(-1)

    def clear_orifice_discharge_coeff(self):
        self.orifice_discharge_coeff_FieldCbo.setCurrentIndex(-1)

    def clear_orifice_flap_gate(self):
        self.orifice_flap_gate_FieldCbo.setCurrentIndex(-1)

    def clear_orifice_time_open_close(self):
        self.orifice_time_open_close_FieldCbo.setCurrentIndex(-1)

    def clear_orifice_shape(self):
        self.orifice_shape_FieldCbo.setCurrentIndex(-1)

    def clear_orifice_height(self):
        self.orifice_height_FieldCbo.setCurrentIndex(-1)

    def clear_orifice_width(self):
        self.orifice_width_FieldCbo.setCurrentIndex(-1)

    # CLEAR WEIR FIELDS:

    def clear_weir_name(self):
        self.weir_name_FieldCbo.setCurrentIndex(-1)

    def clear_weir_from_inlet(self):
        self.weir_from_inlet_FieldCbo.setCurrentIndex(-1)

    def clear_weir_to_outlet(self):
        self.weir_to_outlet_FieldCbo.setCurrentIndex(-1)

    def clear_weir_type(self):
        self.weir_type_FieldCbo.setCurrentIndex(-1)

    def clear_weir_crest_height(self):
        self.weir_crest_height_FieldCbo.setCurrentIndex(-1)

    def clear_weir_discharge_coeff(self):
        self.weir_discharge_coeff_FieldCbo.setCurrentIndex(-1)

    def clear_weir_flap_gate(self):
        self.weir_flap_gate_FieldCbo.setCurrentIndex(-1)

    def clear_weir_end_contrac(self):
        self.weir_end_contrac_FieldCbo.setCurrentIndex(-1)

    def clear_weir_end_coeff(self):
        self.weir_end_coeff_FieldCbo.setCurrentIndex(-1)

    def clear_weir_side_slope(self):
        self.weir_side_slope_FieldCbo.setCurrentIndex(-1)

    def clear_weir_shape(self):
        self.weir_shape_FieldCbo.setCurrentIndex(-1)

    def clear_weir_height(self):
        self.weir_height_FieldCbo.setCurrentIndex(-1)

    def clear_weir_length(self):
        self.weir_length_FieldCbo.setCurrentIndex(-1)

    def clear_all_inlet_attributes(self):
        self.inlets_name_FieldCbo.setCurrentIndex(-1)
        self.inlets_type_FieldCbo.setCurrentIndex(-1)
        self.inlets_invert_elevation_FieldCbo.setCurrentIndex(-1)
        self.inlets_max_depth_FieldCbo.setCurrentIndex(-1)
        self.inlets_init_depth_FieldCbo.setCurrentIndex(-1)
        self.inlets_surcharge_depth_FieldCbo.setCurrentIndex(-1)
        self.inlets_weir_coeff_FieldCbo.setCurrentIndex(-1)
        self.inlets_feature_FieldCbo.setCurrentIndex(-1)
        self.inlets_curb_height_FieldCbo.setCurrentIndex(-1)
        self.inlets_clogging_factor_FieldCbo.setCurrentIndex(-1)
        self.inlets_time_for_clogging_FieldCbo.setCurrentIndex(-1)
        self.inlets_dropbox_area_FieldCbo.setCurrentIndex(-1)
        self.inlets_length_perimeter_FieldCbo.setCurrentIndex(-1)
        self.inlets_width_area_FieldCbo.setCurrentIndex(-1)
        self.inlets_height_sag_surch_FieldCbo.setCurrentIndex(-1)

    def clear_all_outfall_attributes(self):
        self.outfall_name_FieldCbo.setCurrentIndex(-1)
        self.outfall_invert_elevation_FieldCbo.setCurrentIndex(-1)
        self.outfall_flap_gate_FieldCbo.setCurrentIndex(-1)
        self.outfall_allow_discharge_FieldCbo.setCurrentIndex(-1)
        self.outfall_type_FieldCbo.setCurrentIndex(-1)
        self.outfall_water_depth_FieldCbo.setCurrentIndex(-1)
        self.outfall_tidal_curve_FieldCbo.setCurrentIndex(-1)
        self.outfall_time_series_FieldCbo.setCurrentIndex(-1)

    def clear_all_strge_units_attributes(self):
        self.strge_unit_name_FieldCbo.setCurrentIndex(-1)
        self.strge_unit_invert_elevation_FieldCbo.setCurrentIndex(-1)
        self.strge_unit_max_depth_FieldCbo.setCurrentIndex(-1)
        self.strge_unit_initial_depth_FieldCbo.setCurrentIndex(-1)
        self.strge_unit_external_inflow_FieldCbo.setCurrentIndex(-1)
        # self.strge_unit_ponded_area_FieldCbo.setCurrentIndex(-1)
        self.strge_unit_evap_factor_FieldCbo.setCurrentIndex(-1)
        self.strge_unit_treatment_FieldCbo.setCurrentIndex(-1)
        self.strge_unit_infiltration_FieldCbo.setCurrentIndex(-1)
        self.strge_unit_infil_method_FieldCbo.setCurrentIndex(-1)
        self.strge_unit_suction_head_FieldCbo.setCurrentIndex(-1)
        self.strge_unit_conductivity_FieldCbo.setCurrentIndex(-1)
        self.strge_unit_initial_deficit_FieldCbo.setCurrentIndex(-1)
        self.strge_unit_storage_curve_FieldCbo.setCurrentIndex(-1)
        self.strge_unit_coefficient_FieldCbo.setCurrentIndex(-1)
        self.strge_unit_exponent_FieldCbo.setCurrentIndex(-1)
        self.strge_unit_constant_FieldCbo.setCurrentIndex(-1)
        self.strge_unit_curve_name_FieldCbo.setCurrentIndex(-1)

    def clear_all_conduit_attributes(self):
        self.conduit_name_FieldCbo.setCurrentIndex(-1)
        self.conduit_from_inlet_FieldCbo.setCurrentIndex(-1)
        self.conduit_to_outlet_FieldCbo.setCurrentIndex(-1)
        self.conduit_inlet_offset_FieldCbo.setCurrentIndex(-1)
        self.conduit_outlet_offset_FieldCbo.setCurrentIndex(-1)
        self.conduit_shape_FieldCbo.setCurrentIndex(-1)
        self.conduit_barrels_FieldCbo.setCurrentIndex(-1)
        self.conduit_max_depth_FieldCbo.setCurrentIndex(-1)
        self.conduit_geom2_FieldCbo.setCurrentIndex(-1)
        self.conduit_geom3_FieldCbo.setCurrentIndex(-1)
        self.conduit_geom4_FieldCbo.setCurrentIndex(-1)
        self.conduit_length_FieldCbo.setCurrentIndex(-1)
        self.conduit_manning_FieldCbo.setCurrentIndex(-1)
        self.conduit_initial_flow_FieldCbo.setCurrentIndex(-1)
        self.conduit_max_flow_FieldCbo.setCurrentIndex(-1)
        self.conduit_entry_loss_FieldCbo.setCurrentIndex(-1)
        self.conduit_exit_loss_FieldCbo.setCurrentIndex(-1)
        self.conduit_average_loss_FieldCbo.setCurrentIndex(-1)
        self.conduit_flap_gate_FieldCbo.setCurrentIndex(-1)

    def clear_all_pump_attributes(self):
        self.pump_name_FieldCbo.setCurrentIndex(-1)
        self.pump_from_inlet_FieldCbo.setCurrentIndex(-1)
        self.pump_to_outlet_FieldCbo.setCurrentIndex(-1)
        self.pump_initial_status_FieldCbo.setCurrentIndex(-1)
        self.pump_startup_depth_FieldCbo.setCurrentIndex(-1)
        self.pump_shutoff_depth_FieldCbo.setCurrentIndex(-1)
        self.pump_curve_name_FieldCbo.setCurrentIndex(-1)
        self.pump_curve_type_FieldCbo.setCurrentIndex(-1)
        self.pump_curve_description_FieldCbo.setCurrentIndex(-1)

    def clear_all_orifice_attributes(self):
        self.orifice_name_FieldCbo.setCurrentIndex(-1)
        self.orifice_from_inlet_FieldCbo.setCurrentIndex(-1)
        self.orifice_to_outlet_FieldCbo.setCurrentIndex(-1)
        self.orifice_type_FieldCbo.setCurrentIndex(-1)
        self.orifice_crest_height_FieldCbo.setCurrentIndex(-1)
        self.orifice_discharge_coeff_FieldCbo.setCurrentIndex(-1)
        self.orifice_flap_gate_FieldCbo.setCurrentIndex(-1)
        self.orifice_time_open_close_FieldCbo.setCurrentIndex(-1)
        self.orifice_shape_FieldCbo.setCurrentIndex(-1)
        self.orifice_height_FieldCbo.setCurrentIndex(-1)
        self.orifice_width_FieldCbo.setCurrentIndex(-1)

    def clear_all_weir_attributes(self):
        self.weir_name_FieldCbo.setCurrentIndex(-1)
        self.weir_from_inlet_FieldCbo.setCurrentIndex(-1)
        self.weir_to_outlet_FieldCbo.setCurrentIndex(-1)
        self.weir_type_FieldCbo.setCurrentIndex(-1)
        self.weir_crest_height_FieldCbo.setCurrentIndex(-1)
        self.weir_discharge_coeff_FieldCbo.setCurrentIndex(-1)
        self.weir_flap_gate_FieldCbo.setCurrentIndex(-1)
        self.weir_end_contrac_FieldCbo.setCurrentIndex(-1)
        self.weir_end_coeff_FieldCbo.setCurrentIndex(-1)
        self.weir_side_slope_FieldCbo.setCurrentIndex(-1)
        self.weir_shape_FieldCbo.setCurrentIndex(-1)
        self.weir_height_FieldCbo.setCurrentIndex(-1)
        self.weir_length_FieldCbo.setCurrentIndex(-1)

    def assign_components_from_shapefile(self):
        self.uc.clear_bar_messages()

        if self.gutils.is_table_empty("user_model_boundary"):
            self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
            return
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        for combo_inlet in self.inlets_fields_groupBox.findChildren(QComboBox):
            if combo_inlet.currentIndex() != -1:
                self.load_inlets = True
                break
        for combo_outfall in self.outfalls_fields_groupBox.findChildren(QComboBox):
            if combo_outfall.currentIndex() != -1:
                self.load_outfalls = True
                break
        for combo_strge_unit in self.strge_unit_fields_groupBox.findChildren(QComboBox):
            if combo_strge_unit.currentIndex() != -1:
                self.load_strge_units = True
                break
        for combo_conduit in self.conduits_fields_groupBox.findChildren(QComboBox):
            if combo_conduit.currentIndex() != -1:
                self.load_conduits = True
                break
        for combo_pump in self.pumps_fields_groupBox.findChildren(QComboBox):
            if combo_pump.currentIndex() != -1:
                self.load_pumps = True
                break
        for combo_orifice in self.orifices_fields_groupBox.findChildren(QComboBox):
            if combo_orifice.currentIndex() != -1:
                self.load_orifices = True
                break
        for combo_weir in self.weirs_fields_groupBox.findChildren(QComboBox):
            if combo_weir.currentIndex() != -1:
                self.load_weirs = True
                break

        if self.load_inlets:
            if self.inlets_name_FieldCbo.currentText() == "":
                QApplication.restoreOverrideCursor()
                self.uc.show_info(
                    "The 'Inlet Name' field must be selected if the Inlets/Junctions component is picked!"
                )
                return
        if self.load_outfalls:
            if self.outfall_name_FieldCbo.currentText() == "":
                QApplication.restoreOverrideCursor()
                self.uc.show_info("The 'Outfall Name' field must be selected if the Outfalls component is picked!")
                return
        if self.load_strge_units:
            if self.strge_unit_name_FieldCbo.currentText() == "":
                QApplication.restoreOverrideCursor()
                self.uc.show_info(
                    "The 'Storage Unit Name' field must be selected if the Storage Units component is picked!")
                return
        if self.load_conduits:
            if self.conduit_name_FieldCbo.currentText() == "":
                QApplication.restoreOverrideCursor()
                self.uc.show_info("The 'Conduit Name' field must be selected if the Conduits component is picked!")
                return
        if self.load_pumps:
            if self.pump_name_FieldCbo.currentText() == "":
                QApplication.restoreOverrideCursor()
                self.uc.show_info("The 'Pump Name' field must be selected if the Pumps component is picked!")
                return
        if self.load_orifices:
            if self.orifice_name_FieldCbo.currentText() == "":
                QApplication.restoreOverrideCursor()
                self.uc.show_info("The 'Orifice Name' field must be selected if the Orifices component is picked!")
                return
        if self.load_weirs:
            if self.weir_name_FieldCbo.currentText() == "":
                QApplication.restoreOverrideCursor()
                self.uc.show_info("The 'Weir Name' field must be selected if the Weirs component is picked!")
                return

        if (
                not self.load_inlets
                and not self.load_outfalls
                and not self.load_strge_units
                and not self.load_conduits
                and not self.load_pumps
                and not self.load_orifices
                and not self.load_weirs
        ):
            self.uc.bar_warn("No data was selected!")
            self.save_storm_drain_shapefile_field_names()

        else:
            self.load_inlets_from_shapefile()
            self.load_outfalls_from_shapefile()
            self.load_strge_units_from_shapefile()
            self.load_conduits_from_shapefile()
            self.load_pumps_from_shapefile()
            self.load_orifices_from_shapefile()
            self.load_weirs_from_shapefile()

            self.save_storm_drain_shapefile_field_names()

            QApplication.restoreOverrideCursor()

            if (
                    self.load_inlets
                    or self.load_outfalls
                    or self.load_strge_units
                    or self.load_conduits
                    or self.load_pumps
                    or self.load_orifices
                    or self.load_weirs
            ):

                if len(self.no_in_out) > 0:
                    self.uc.show_warn(
                        "WARNING 040524.0806:\nLinks with no inlet and/or outlet:\n"
                        + str(self.no_in_out)
                        + "\n\nThe value '?' will be assigned to the missing inlets and/or outlets.\nThey will cause errors during their processing.\n\n"
                        + "Did you select the 'From Inlet' and 'To Oulet' fields in the shapefile?\n\n"
                        + "You can also use the 'Auto-assign link nodes' button to automatically fill the node names required for the link connections."
                    )

                self.uc.show_info(
                    "Importing Nodes and Links finished!\n\n"
                    + "Use the Components (Nodes and Links) buttons in the Storm Drain Editor to view/edit data.\n\n"
                    + "Complete the storm drain by clicking the Schematize Storm Drain Components button."
                )

            else:
                self.uc.show_info("No Storm Drain nodes or links selected!")

    def load_inlets_from_shapefile(self):
        if self.load_inlets:
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                fields = self.user_swmm_nodes_lyr.fields()
                new_feats = []
                outside_inlets = ""
                inlets_shapefile = self.inlets_shapefile_cbo.currentText()
                lyr = self.lyrs.get_layer_by_name(inlets_shapefile).layer()

                inlets_shapefile_fts = lyr.getFeatures()
                modified = 0
                for f in inlets_shapefile_fts:
                    name = (
                        f[self.inlets_name_FieldCbo.currentText()]
                        if self.inlets_name_FieldCbo.currentText() != ""
                        else ""
                    )
                    intype = (
                        f[self.inlets_type_FieldCbo.currentText()]
                        if self.inlets_type_FieldCbo.currentText() != ""
                        else 1
                    )
                    junction_invert_elev = (
                        f[self.inlets_invert_elevation_FieldCbo.currentText()]
                        if self.inlets_invert_elevation_FieldCbo.currentText() != ""
                        else 0
                    )
                    max_depth = (
                        f[self.inlets_max_depth_FieldCbo.currentText()]
                        if self.inlets_max_depth_FieldCbo.currentText() != ""
                        else 0
                    )
                    init_depth = (
                        f[self.inlets_init_depth_FieldCbo.currentText()]
                        if self.inlets_init_depth_FieldCbo.currentText() != ""
                        else 0
                    )
                    surcharge_depth = (
                        f[self.inlets_surcharge_depth_FieldCbo.currentText()]
                        if self.inlets_surcharge_depth_FieldCbo.currentText() != ""
                        else 0
                    )
                    swmm_length = (
                        f[self.inlets_length_perimeter_FieldCbo.currentText()]
                        if self.inlets_length_perimeter_FieldCbo.currentText() != ""
                        else 0
                    )
                    swmm_width = (
                        f[self.inlets_width_area_FieldCbo.currentText()]
                        if self.inlets_width_area_FieldCbo.currentText() != ""
                        else 0
                    )
                    swmm_height = (
                        f[self.inlets_height_sag_surch_FieldCbo.currentText()]
                        if self.inlets_height_sag_surch_FieldCbo.currentText() != ""
                        else 0
                    )
                    swmm_coeff = (
                        f[self.inlets_weir_coeff_FieldCbo.currentText()]
                        if self.inlets_weir_coeff_FieldCbo.currentText() != ""
                        else 0
                    )
                    swmm_feature = (
                        f[self.inlets_feature_FieldCbo.currentText()]
                        if self.inlets_feature_FieldCbo.currentText() != ""
                        else 0
                    )
                    curbheight = (
                        f[self.inlets_curb_height_FieldCbo.currentText()]
                        if self.inlets_curb_height_FieldCbo.currentText() != ""
                        else 0
                    )
                    swmm_clogging_factor = (
                        f[self.inlets_clogging_factor_FieldCbo.currentText()]
                        if self.inlets_clogging_factor_FieldCbo.currentText() != ""
                        else 0
                    )
                    swmm_time_for_clogging = (
                        f[self.inlets_time_for_clogging_FieldCbo.currentText()]
                        if self.inlets_time_for_clogging_FieldCbo.currentText() != ""
                        else 0
                    )
                    drboxarea = (
                        f[self.inlets_dropbox_area_FieldCbo.currentText()]
                        if self.inlets_dropbox_area_FieldCbo.currentText() != "" and name[0] != "J"
                        else 0
                    )

                    feat = QgsFeature()
                    feat.setFields(fields)

                    if f.geometry() is None:
                        self.uc.show_warn("WARNING 280920.1816: Error processing geometry of inlet/junction  " + name)
                        continue

                    geom = f.geometry()
                    if geom is None or geom.type() != 0:
                        self.uc.show_warn("WARNING 060319.1822: Error processing geometry of inlet/junction  " + name)
                        continue

                    point = geom.asPoint()
                    if point is None:
                        self.uc.show_warn("WARNING 060319.1656: Inlet/junction  " + name + "  is faulty!")
                        continue

                    try:
                        cell = self.gutils.grid_on_point(point.x(), point.y())
                    except:
                        cell = None

                    # Inlet outside the grid
                    if cell is None and name.startswith("I"):
                        outside_inlets += "\n" + name
                        continue

                    new_geom = QgsGeometry.fromPointXY(point)
                    feat.setGeometry(new_geom)

                    feat.setAttribute("grid", cell)
                    feat.setAttribute("sd_type", "I")
                    feat.setAttribute("name", name)
                    feat.setAttribute("intype", intype)
                    feat.setAttribute("junction_invert_elev", junction_invert_elev)
                    feat.setAttribute("max_depth", max_depth)
                    feat.setAttribute("init_depth", init_depth)
                    feat.setAttribute("surcharge_depth", surcharge_depth)
                    feat.setAttribute("outfall_invert_elev", 0)
                    feat.setAttribute("outfall_type", "NORMAL")
                    feat.setAttribute("tidal_curve", "*")
                    feat.setAttribute("time_series", "*")
                    feat.setAttribute("flapgate", "False")
                    feat.setAttribute("swmm_length", swmm_length)
                    feat.setAttribute("swmm_width", swmm_width)
                    feat.setAttribute("swmm_height", swmm_height)

                    # Check valid ranges and maybe assign defaults inlet type:

                    if intype in {1, 3, 5}:
                        if self.unit == 1:  # Metric
                            if 1.3 <= swmm_coeff <= 1.9:
                                # OK
                                pass
                            else:
                                swmm_coeff = 1.60
                                modified += 1
                        else:  # English
                            if 2.85 <= swmm_coeff <= 3.30:
                                # OK
                                pass
                            else:
                                swmm_coeff = 3.00
                                modified += 1
                    elif intype == 2:
                        if self.unit == 1:  # Metric
                            if 1.0 <= swmm_coeff <= 1.6:
                                # OK
                                pass
                            else:
                                swmm_coeff = 1.25
                                modified += 1
                        else:  # English
                            if 2.0 <= swmm_coeff <= 2.6:
                                # OK
                                pass
                            else:
                                swmm_coeff = 2.30
                                modified += 1

                    feat.setAttribute("swmm_coeff", swmm_coeff)
                    feat.setAttribute("swmm_feature", swmm_feature)
                    feat.setAttribute("curbheight", curbheight)
                    feat.setAttribute("swmm_clogging_factor", swmm_clogging_factor)
                    feat.setAttribute("swmm_time_for_clogging", swmm_time_for_clogging)
                    feat.setAttribute("drboxarea", drboxarea)
                    feat.setAttribute("swmm_allow_discharge", "0")
                    feat.setAttribute("water_depth", 0)
                    feat.setAttribute("rt_fid", 0)
                    feat.setAttribute("outf_flo", 0)
                    feat.setAttribute("invert_elev_inp", 0)
                    feat.setAttribute("max_depth_inp", 0)
                    feat.setAttribute("rim_elev_inp", 0)
                    feat.setAttribute("rim_elev", 0)
                    feat.setAttribute("ge_elev", 0)
                    feat.setAttribute("difference", 0)

                    new_feats.append(feat)

                if new_feats:
                    if not self.inlets_append_chbox.isChecked():
                        remove_features(self.user_swmm_nodes_lyr)

                    self.user_swmm_nodes_lyr.startEditing()
                    self.user_swmm_nodes_lyr.addFeatures(new_feats)
                    self.user_swmm_nodes_lyr.commitChanges()
                    self.user_swmm_nodes_lyr.updateExtents()
                    self.user_swmm_nodes_lyr.triggerRepaint()
                    self.user_swmm_nodes_lyr.removeSelection()
                else:
                    self.load_inlets = False

                QApplication.restoreOverrideCursor()

                if outside_inlets != "":
                    self.uc.bar_info(
                        "WARNING 060319.1657: Inlets/junctions are outside the computational domain!"
                    )
                    self.uc.log_info(
                        "WARNING 060319.1657: The following inlets/junctions are outside the computational domain!\n"
                        + outside_inlets
                    )

                if modified > 0:
                    self.uc.bar_warn(
                        "WARNING 050820.1901: "
                        + str(modified)
                        + " Weir Coefficients in shapefile are outside valid ranges. "
                        + "Default values were assigned to "
                        + str(modified)
                        + " inlets!"
                    )

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error(
                    "ERROR 070618.0451: creation of Storm Drain Nodes (Inlets) layer failed after reading "
                    + str(len(new_feats))
                    + " inlets!"
                    + "\n__________________________________________________",
                    e,
                )
                self.load_inlets = False

    def load_outfalls_from_shapefile(self):
        if self.load_outfalls:
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                fields = self.user_swmm_nodes_lyr.fields()
                new_feats = []
                outside_outfalls = ""

                outfalls_shapefile = self.outfalls_shapefile_cbo.currentText()
                lyr = self.lyrs.get_layer_by_name(outfalls_shapefile).layer()
                outfalls_shapefile_fts = lyr.getFeatures()

                for f in outfalls_shapefile_fts:
                    name = (
                        f[self.outfall_name_FieldCbo.currentText()]
                        if self.outfall_name_FieldCbo.currentText() != ""
                        else ""
                    )
                    outfall_invert_elev = (
                        f[self.outfall_invert_elevation_FieldCbo.currentText()]
                        if self.outfall_invert_elevation_FieldCbo.currentText() != ""
                        else ""
                    )
                    flapgate = (
                        f[self.outfall_flap_gate_FieldCbo.currentText()]
                        if self.outfall_flap_gate_FieldCbo.currentText() != ""
                        else ""
                    )
                    flapgate = "True" if is_true(flapgate) else "False"
                    
                    swmm_allow_discharge = (
                        f[self.outfall_allow_discharge_FieldCbo.currentText()]
                        if self.outfall_allow_discharge_FieldCbo.currentText() != ""
                        else ""
                    )
                    swmm_allow_discharge = str(swmm_allow_discharge) if swmm_allow_discharge in ["0", "1", "2", 0, 1, 2]  else "0"
                    
                    outfall_type = (
                        f[self.outfall_type_FieldCbo.currentText()]
                        if self.outfall_type_FieldCbo.currentText() != ""
                        else ""
                    )
                    water_depth = self.outfall_water_depth_FieldCbo.currentText()
                    water_depth = f[water_depth] if water_depth != "" and water_depth is not None else ""

                    feat = QgsFeature()
                    feat.setFields(fields)

                    if f.geometry() is None:
                        self.uc.show_warn("WARNING 261220.1013: Error processing geometry of outfall  " + name)
                        continue

                    geom = f.geometry()
                    if geom is None or geom.type() != 0:
                        self.uc.show_warn("WARNING 060319.1658: Error processing geometry of outfall  " + name)
                        continue

                    point = geom.asPoint()
                    if point is None:
                        self.uc.show_warn("WARNING 060319.1659: Outfall  " + name + "  is faulty!")
                        continue

                    try:
                        cell = self.gutils.grid_on_point(point.x(), point.y())
                    except:
                        cell = None

                    if cell is None and swmm_allow_discharge == '1':
                        outside_outfalls += "\n" + name
                        continue

                    new_geom = QgsGeometry.fromPointXY(point)
                    feat.setGeometry(new_geom)

                    feat.setAttribute("grid", cell)
                    feat.setAttribute("sd_type", "O")
                    feat.setAttribute("name", name)
                    feat.setAttribute("intype", 1)
                    feat.setAttribute("junction_invert_elev", 0)
                    feat.setAttribute("max_depth", 0)
                    feat.setAttribute("init_depth", 0)
                    feat.setAttribute("surcharge_depth", 0)
                    feat.setAttribute("ponded_area", 0)
                    feat.setAttribute("outfall_invert_elev", outfall_invert_elev)
                    feat.setAttribute("outfall_type", outfall_type)
                    feat.setAttribute("tidal_curve", "...")
                    feat.setAttribute("time_series", "...")
                    feat.setAttribute("flapgate", flapgate)
                    feat.setAttribute("swmm_length", 0)
                    feat.setAttribute("swmm_width", 0)
                    feat.setAttribute("swmm_height", 0)
                    feat.setAttribute("swmm_coeff", 0)
                    feat.setAttribute("swmm_feature", 0)
                    feat.setAttribute("curbheight", 0)
                    feat.setAttribute("swmm_clogging_factor", 0)
                    feat.setAttribute("swmm_time_for_clogging", 0)
                    feat.setAttribute("swmm_allow_discharge", swmm_allow_discharge)
                    feat.setAttribute("water_depth", 0)
                    feat.setAttribute("rt_fid", 0)
                    feat.setAttribute("outf_flo", 0)
                    feat.setAttribute("invert_elev_inp", 0)
                    feat.setAttribute("max_depth_inp", 0)
                    feat.setAttribute("rim_elev_inp", 0)
                    feat.setAttribute("rim_elev", 0)
                    feat.setAttribute("ge_elev", 0)
                    feat.setAttribute("difference", 0)

                    new_feats.append(feat)

                if new_feats:
                    if not self.outfall_append_chbox.isChecked() and not self.load_inlets:
                        remove_features(self.user_swmm_nodes_lyr)

                    self.user_swmm_nodes_lyr.startEditing()
                    self.user_swmm_nodes_lyr.addFeatures(new_feats)
                    self.user_swmm_nodes_lyr.commitChanges()
                    self.user_swmm_nodes_lyr.updateExtents()
                    self.user_swmm_nodes_lyr.triggerRepaint()
                    self.user_swmm_nodes_lyr.removeSelection()
                else:
                    self.load_outfalls = False

                QApplication.restoreOverrideCursor()

                if outside_outfalls != "":
                    self.uc.bar_info(
                        "WARNING 060319.1700: Outfalls are outside the computational domain!"
                    )
                    self.uc.log_info(
                        "WARNING 060319.1700: The following outfalls are outside the computational domain!\n"
                        + outside_outfalls
                    )

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error(
                    "ERROR 070618.0454: creation of Storm Drain Nodes (Outfalls) layer failed after reading "
                    + str(len(new_feats))
                    + " outfalls!"
                    + "\n__________________________________________________",
                    e,
                )
                self.load_outfalls = False

    def load_strge_units_from_shapefile(self):
        if self.load_strge_units:
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                fields = self.user_swmm_strge_units_lyr.fields()
                new_feats = []
                outside_strge_units = ""

                strge_units_shapefile = self.strge_units_shapefile_cbo.currentText()
                lyr = self.lyrs.get_layer_by_name(strge_units_shapefile).layer()
                strge_units_shapefile_fts = lyr.getFeatures()

                for f in strge_units_shapefile_fts:
                    name = (
                        f[self.strge_unit_name_FieldCbo.currentText()]
                        if self.strge_unit_name_FieldCbo.currentText() != ""
                        else ""
                    )
                    invert_elev = (
                        f[self.strge_unit_invert_elevation_FieldCbo.currentText()]
                        if self.strge_unit_invert_elevation_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    max_depth = (
                        f[self.strge_unit_max_depth_FieldCbo.currentText()]
                        if self.strge_unit_max_depth_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    initial_depth = (
                        f[self.strge_unit_initial_depth_FieldCbo.currentText()]
                        if self.strge_unit_initial_depth_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    external_inflow = (
                        f[self.strge_unit_external_inflow_FieldCbo.currentText()]
                        if self.strge_unit_external_inflow_FieldCbo.currentText() != ""
                        else "False")

                    ponded_area = 0.0
                    # ponded_area = (
                    #     f[self.strge_unit_ponded_area_FieldCbo.currentText()]
                    #     if self.strge_unit_ponded_area_FieldCbo.currentText() != ""
                    #     else 0.0
                    # )
                    evap_factor = (
                        f[self.strge_unit_evap_factor_FieldCbo.currentText()]
                        if self.strge_unit_evap_factor_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    treatment = (
                        f[self.strge_unit_treatment_FieldCbo.currentText()]
                        if self.strge_unit_treatment_FieldCbo.currentText() != ""
                        else "NO"
                    )
                    infiltration = (
                        f[self.strge_unit_infiltration_FieldCbo.currentText()]
                        if self.strge_unit_infiltration_FieldCbo.currentText() != ""
                        else "False"
                    )
                    infil_method = (
                        f[self.strge_unit_infil_method_FieldCbo.currentText()]
                        if self.strge_unit_infil_method_FieldCbo.currentText() != ""
                        else "GREEN_AMPT"
                    )
                    suction_head = (
                        f[self.strge_unit_suction_head_FieldCbo.currentText()]
                        if self.strge_unit_suction_head_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    conductivity = (
                        f[self.strge_unit_conductivity_FieldCbo.currentText()]
                        if self.strge_unit_conductivity_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    initial_deficit = (
                        f[self.strge_unit_initial_deficit_FieldCbo.currentText()]
                        if self.strge_unit_initial_deficit_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    storage_curve = (
                        f[self.strge_unit_storage_curve_FieldCbo.currentText()]
                        if self.strge_unit_storage_curve_FieldCbo.currentText() != ""
                        else "FUNCTIONAL"
                    )
                    coefficient = (
                        f[self.strge_unit_coefficient_FieldCbo.currentText()]
                        if self.strge_unit_coefficient_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    exponent = (
                        f[self.strge_unit_exponent_FieldCbo.currentText()]
                        if self.strge_unit_exponent_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    constant = (
                        f[self.strge_unit_constant_FieldCbo.currentText()]
                        if self.strge_unit_constant_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    curve_name = (
                        f[self.strge_unit_curve_name_FieldCbo.currentText()]
                        if self.strge_unit_curve_name_FieldCbo.currentText() != ""
                        else "*"
                    )

                    feat = QgsFeature()
                    feat.setFields(fields)

                    if f.geometry() is None:
                        self.uc.show_warn("WARNING 250424.1943: Error processing geometry of storage unit  " + name)
                        continue

                    geom = f.geometry()
                    if geom is None or geom.type() != 0:
                        self.uc.show_warn("WARNING 250424.1944: Error processing geometry of storage unit  " + name)
                        continue

                    point = geom.asPoint()
                    if point is None:
                        self.uc.show_warn("WARNING 250424.1945: Storage unit  " + name + "  is faulty!")
                        continue

                    cell = self.gutils.grid_on_point(point.x(), point.y())
                    if cell is None and external_inflow == 'NO':
                        outside_strge_units += "\n" + name
                        continue

                    new_geom = QgsGeometry.fromPointXY(point)
                    feat.setGeometry(new_geom)

                    feat.setAttribute("grid", cell)
                    feat.setAttribute("name", name)
                    feat.setAttribute("invert_elev", invert_elev)
                    feat.setAttribute("max_depth", max_depth)
                    feat.setAttribute("init_depth", initial_depth)
                    feat.setAttribute("external_inflow", external_inflow)
                    feat.setAttribute("treatment", treatment)
                    feat.setAttribute("ponded_area", ponded_area)
                    feat.setAttribute("evap_factor", evap_factor)
                    feat.setAttribute("infiltration", infiltration)
                    feat.setAttribute("infil_method", infil_method)
                    feat.setAttribute("suction_head", suction_head)
                    feat.setAttribute("conductivity", conductivity)
                    feat.setAttribute("initial_deficit", initial_deficit)
                    feat.setAttribute("storage_curve", storage_curve)
                    feat.setAttribute("coefficient", coefficient)
                    feat.setAttribute("exponent", exponent)
                    feat.setAttribute("constant", constant)
                    feat.setAttribute("curve_name", curve_name)

                    new_feats.append(feat)

                if new_feats:
                    if not self.strge_unit_append_chbox.isChecked():
                        remove_features(self.user_swmm_strge_units_lyr)

                    self.user_swmm_strge_units_lyr.startEditing()
                    self.user_swmm_strge_units_lyr.addFeatures(new_feats)
                    self.user_swmm_strge_units_lyr.commitChanges()
                    self.user_swmm_strge_units_lyr.updateExtents()
                    self.user_swmm_strge_units_lyr.triggerRepaint()
                    self.user_swmm_strge_units_lyr.removeSelection()
                else:
                    self.load_strge_units = False

                QApplication.restoreOverrideCursor()

                if outside_strge_units != "":
                    self.uc.bar_info(
                        "WARNING 250424.2002: Storage units are outside the computational domain!"
                    )
                    self.uc.log_info(
                        "WARNING 250424.2002: The following storage units are outside the computational domain!\n"
                        + outside_strge_units
                    )

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error(
                    "ERROR 250424.2003: creation of Storm Drain Storage Units layer failed after reading "
                    + str(len(new_feats))
                    + " storage units!"
                    + "\n__________________________________________________",
                    e,
                )
                self.load_strge_units = False

    def load_conduits_from_shapefile(self):
        if self.load_conduits:
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                fields = self.user_swmm_conduits_lyr.fields()
                new_feats = []
                outside_conduits = []
                inlets_outlets_inside = []

                conduits_shapefile = self.conduits_shapefile_cbo.currentText()
                lyr = self.lyrs.get_layer_by_name(conduits_shapefile).layer()
                conduits_shapefile_fts = lyr.getFeatures()
                no_in_out = 0

                for f in conduits_shapefile_fts:
                    conduit_name = (
                        f[self.conduit_name_FieldCbo.currentText()]
                        if self.conduit_name_FieldCbo.currentText() != ""
                        else ""
                    )
                    conduit_inlet = (
                        f[self.conduit_from_inlet_FieldCbo.currentText()]
                        if self.conduit_from_inlet_FieldCbo.currentText() != ""
                        else "?"
                    )
                    conduit_inlet = conduit_inlet if conduit_inlet != NULL else "?"

                    conduit_outlet = (
                        f[self.conduit_to_outlet_FieldCbo.currentText()]
                        if self.conduit_to_outlet_FieldCbo.currentText() != ""
                        else "?"
                    )
                    conduit_outlet = conduit_outlet if conduit_outlet != NULL else "?"

                    conduit_inlet_offset = (
                        f[self.conduit_inlet_offset_FieldCbo.currentText()]
                        if self.conduit_inlet_offset_FieldCbo.currentText() != ""
                        else 0
                    )
                    conduit_outlet_offset = (
                        f[self.conduit_outlet_offset_FieldCbo.currentText()]
                        if self.conduit_outlet_offset_FieldCbo.currentText() != ""
                        else 0
                    )
                    conduit_shape = (
                        f[self.conduit_shape_FieldCbo.currentText()]
                        if self.conduit_shape_FieldCbo.currentText() != ""
                        else "CIRCULAR"
                    )
                    conduit_max_depth = (
                        f[self.conduit_max_depth_FieldCbo.currentText()]
                        if self.conduit_max_depth_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    conduit_geom2 = (
                        f[self.conduit_geom2_FieldCbo.currentText()]
                        if self.conduit_geom2_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    conduit_geom3 = (
                        f[self.conduit_geom3_FieldCbo.currentText()]
                        if self.conduit_geom3_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    conduit_geom4 = (
                        f[self.conduit_geom4_FieldCbo.currentText()]
                        if self.conduit_geom4_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    conduit_barrels = (
                        f[self.conduit_barrels_FieldCbo.currentText()]
                        if self.conduit_barrels_FieldCbo.currentText() != ""
                        else 0
                    )
                    conduit_length = (
                        f[self.conduit_length_FieldCbo.currentText()]
                        if self.conduit_length_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    conduit_manning = (
                        f[self.conduit_manning_FieldCbo.currentText()]
                        if self.conduit_manning_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    conduit_init_flow = (
                        f[self.conduit_initial_flow_FieldCbo.currentText()]
                        if self.conduit_initial_flow_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    conduit_max_flow = (
                        f[self.conduit_max_flow_FieldCbo.currentText()]
                        if self.conduit_max_flow_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    conduit_entry_loss = (
                        f[self.conduit_entry_loss_FieldCbo.currentText()]
                        if self.conduit_entry_loss_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    conduit_exit_loss = (
                        f[self.conduit_exit_loss_FieldCbo.currentText()]
                        if self.conduit_exit_loss_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    conduit_loss_average = (
                        f[self.conduit_average_loss_FieldCbo.currentText()]
                        if self.conduit_average_loss_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    conduits_flap_gate = (
                        f[self.conduit_flap_gate_FieldCbo.currentText()]
                        if self.conduit_flap_gate_FieldCbo.currentText() != ""
                        else 0
                    )

                    if conduit_inlet == "?" or conduit_outlet == "?":
                        no_in_out += 1

                    feat = QgsFeature()
                    feat.setFields(fields)

                    geom = f.geometry()
                    if geom is None or geom.type() != 1:
                        self.uc.show_warn("WARNING 060319.1701: Error processing geometry of conduit  " + conduit_name)
                        continue

                    points = extractPoints(geom)
                    if points is None:
                        self.uc.show_warn("WARNING 060319.1702: Conduit  " + conduit_name + "  is faulty!")
                        continue

                    conduit_inlet_cell = self.gutils.grid_on_point(points[0].x(), points[0].y())
                    conduit_outlet_cell = self.gutils.grid_on_point(points[len(points) - 1].x(), points[len(points) - 1].y())
                    # Both ends of the conduit is outside the grid
                    if conduit_inlet_cell is None and conduit_outlet_cell is None:
                        if not (conduit_name in outside_conduits):
                            outside_conduits.append(conduit_name)
                            continue

                    # Conduit inlet is outside the grid and it is an Inlet
                    elif conduit_inlet_cell is None and conduit_inlet.startswith("I"):
                        if not (conduit_name in outside_conduits):
                            outside_conduits.append(conduit_name)
                            continue

                    new_geom = QgsGeometry.fromPolylineXY(points)
                    feat.setGeometry(new_geom)

                    feat.setAttribute("conduit_name", conduit_name)
                    feat.setAttribute("conduit_inlet", conduit_inlet)
                    feat.setAttribute("conduit_outlet", conduit_outlet)
                    feat.setAttribute(
                        "conduit_inlet_offset",
                        conduit_inlet_offset if conduit_inlet_offset != NULL else 0.0,
                    )
                    feat.setAttribute(
                        "conduit_outlet_offset",
                        conduit_outlet_offset if conduit_outlet_offset != NULL else 0.0,
                    )
                    feat.setAttribute(
                        "conduit_length",
                        conduit_length if conduit_length != NULL else 0.0,
                    )
                    feat.setAttribute(
                        "conduit_manning",
                        conduit_manning if conduit_manning != NULL else 0.0,
                    )
                    feat.setAttribute(
                        "conduit_init_flow",
                        conduit_init_flow if conduit_init_flow != NULL else 0.0,
                    )
                    feat.setAttribute(
                        "conduit_max_flow",
                        conduit_max_flow if conduit_max_flow != NULL else 0.0,
                    )
                    feat.setAttribute(
                        "losses_inlet",
                        conduit_entry_loss if conduit_entry_loss != NULL else 0.0,
                    )
                    feat.setAttribute(
                        "losses_outlet",
                        conduit_exit_loss if conduit_exit_loss != NULL else 0.0,
                    )
                    feat.setAttribute(
                        "losses_average",
                        conduit_loss_average if conduit_loss_average != NULL else 0.0,
                    )
                    feat.setAttribute(
                        "losses_flapgate",
                        conduits_flap_gate if conduits_flap_gate != NULL else 0,
                    )

                    feat.setAttribute(
                        "xsections_shape",
                        conduit_shape if conduit_shape in self.shape else "CIRCULAR",
                    )

                    feat.setAttribute(
                        "xsections_barrels",
                        conduit_barrels if conduit_barrels != NULL else 0,
                    )
                    feat.setAttribute(
                        "xsections_max_depth",
                        conduit_max_depth if conduit_max_depth != NULL else 0.0,
                    )
                    feat.setAttribute(
                        "xsections_geom2",
                        conduit_geom2 if conduit_geom2 != NULL else 0.0,
                    )
                    feat.setAttribute(
                        "xsections_geom3",
                        conduit_geom3 if conduit_geom3 != NULL else 0.0,
                    )
                    feat.setAttribute(
                        "xsections_geom4",
                        conduit_geom4 if conduit_geom4 != NULL else 0.0,
                    )

                    new_feats.append(feat)
                    if conduit_inlet not in inlets_outlets_inside:
                        inlets_outlets_inside.append(conduit_inlet)
                    if conduit_outlet not in inlets_outlets_inside:
                        inlets_outlets_inside.append(conduit_outlet)

                if new_feats:
                    if not self.conduits_append_chbox.isChecked():
                        remove_features(self.user_swmm_conduits_lyr)
                    self.user_swmm_conduits_lyr.startEditing()
                    self.user_swmm_conduits_lyr.addFeatures(new_feats)
                    self.user_swmm_conduits_lyr.commitChanges()
                    self.user_swmm_conduits_lyr.updateExtents()
                    self.user_swmm_conduits_lyr.triggerRepaint()
                    self.user_swmm_conduits_lyr.removeSelection()
                else:
                    self.load_conduits = False

                # Remove junctions not connected to conduits
                self.user_swmm_nodes_lyr.startEditing()
                for feat in self.user_swmm_nodes_lyr.getFeatures():
                    node_name = feat['name']
                    if len(inlets_outlets_inside) > 1:
                        if node_name not in inlets_outlets_inside:
                            self.user_swmm_nodes_lyr.deleteFeature(feat.id())
                self.user_swmm_nodes_lyr.commitChanges()
                self.user_swmm_nodes_lyr.updateExtents()
                self.user_swmm_nodes_lyr.triggerRepaint()

                QApplication.restoreOverrideCursor()

                if no_in_out != 0:
                    self.no_in_out += "\n" + str(no_in_out) + " conduits."

                if len(outside_conduits) > 0:
                    self.uc.bar_info(
                        "WARNING 231220.0954: Conduits are outside the computational domain!"
                    )
                    self.uc.log_info(
                        "WARNING 231220.0954: The following conduits are outside the computational domain!\n"
                        + '\n'.join(outside_conduits)
                    )

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error(
                    "ERROR 070618.0500: creation of Storm Drain Conduits User layer failed after reading "
                    + str(len(new_feats))
                    + " conduits!"
                    + "\n__________________________________________________",
                    e,
                )
                self.load_conduits = False

    def load_pumps_from_shapefile(self):
        if self.load_pumps:
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                fields = self.user_swmm_pumps_lyr.fields()
                new_feats = []
                outside_pumps = ""
                wrong_status = 0

                pumps_shapefile = self.pumps_shapefile_cbo.currentText()
                lyr = self.lyrs.get_layer_by_name(pumps_shapefile).layer()
                pumps_shapefile_fts = lyr.getFeatures()
                no_in_out = 0

                for f in pumps_shapefile_fts:
                    pump_name = (
                        f[self.pump_name_FieldCbo.currentText()] if self.pump_name_FieldCbo.currentText() != "" else ""
                    )
                    pump_inlet = (
                        f[self.pump_from_inlet_FieldCbo.currentText()]
                        if self.pump_from_inlet_FieldCbo.currentText() != ""
                        else "?"
                    )
                    pump_inlet = pump_inlet if pump_inlet != NULL else "?"

                    pump_outlet = (
                        f[self.pump_to_outlet_FieldCbo.currentText()]
                        if self.pump_to_outlet_FieldCbo.currentText() != ""
                        else "?"
                    )
                    pump_outlet = pump_outlet if pump_outlet != NULL else "?"

                    status = (
                        f[self.pump_initial_status_FieldCbo.currentText()]
                        if self.pump_initial_status_FieldCbo.currentText() != ""
                        else "OFF"
                    )
                    if status in self.TRUE:
                        status = "ON"
                    elif status in self.FALSE:
                        status = "OFF"
                    else:
                        status = "OFF"
                        wrong_status += 1
                    pump_initial_status = status

                    pump_startup_depth = (
                        f[self.pump_startup_depth_FieldCbo.currentText()]
                        if self.pump_startup_depth_FieldCbo.currentText() != ""
                        else 0
                    )
                    pump_shutoff_depth = (
                        f[self.pump_shutoff_depth_FieldCbo.currentText()]
                        if self.pump_shutoff_depth_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    pump_curve_name = (
                        f[self.pump_curve_name_FieldCbo.currentText()]
                        if self.pump_curve_name_FieldCbo.currentText() != ""
                        else "*"
                    )

                    if pump_inlet == "?" or pump_outlet == "?":
                        no_in_out += 1

                    feat = QgsFeature()
                    feat.setFields(fields)

                    geom = f.geometry()
                    if geom is None or geom.type() != 1:
                        self.uc.show_warn("WARNING 280222.0951: Error processing geometry of pump  " + pump_name)
                        continue

                    points = extractPoints(geom)
                    if points is None:
                        self.uc.show_warn("WARNING 280222.0951: Pump  " + pump_name + " is faulty!")
                        continue

                    cell = self.gutils.grid_on_point(points[0].x(), points[0].y())
                    if cell is None:
                        outside_pumps += "\n" + pump_name
                        continue

                    cell = self.gutils.grid_on_point(points[1].x(), points[1].y())
                    if cell is None:
                        outside_pumps += "\n" + pump_name
                        continue

                    new_geom = QgsGeometry.fromPolylineXY(points)
                    feat.setGeometry(new_geom)

                    feat.setAttribute("pump_name", pump_name)
                    feat.setAttribute("pump_inlet", pump_inlet)
                    feat.setAttribute("pump_outlet", pump_outlet)
                    feat.setAttribute("pump_init_status", pump_initial_status)
                    feat.setAttribute(
                        "pump_startup_depth",
                        pump_startup_depth if pump_startup_depth != NULL else 0.0,
                    )
                    feat.setAttribute(
                        "pump_shutoff_depth",
                        pump_shutoff_depth if pump_shutoff_depth != NULL else 0.0,
                    )
                    feat.setAttribute(
                        "pump_curve",
                        pump_curve_name if pump_curve_name != NULL else "*",
                    )

                    new_feats.append(feat)

                if new_feats:
                    if not self.pumps_append_chbox.isChecked():
                        remove_features(self.user_swmm_pumps_lyr)

                    self.user_swmm_pumps_lyr.startEditing()
                    self.user_swmm_pumps_lyr.addFeatures(new_feats)
                    self.user_swmm_pumps_lyr.commitChanges()
                    self.user_swmm_pumps_lyr.updateExtents()
                    self.user_swmm_pumps_lyr.triggerRepaint()
                    self.user_swmm_pumps_lyr.removeSelection()
                else:
                    self.load_pumps = False

                QApplication.restoreOverrideCursor()

                if no_in_out != 0:
                    self.no_in_out += "\n" + str(no_in_out) + " pumps."

                if outside_pumps != "":
                    self.uc.show_warn(
                        "WARNING 220222.1031: The following pumps are outside the computational domain!\n"
                        + outside_pumps
                    )

                if wrong_status > 0:
                    self.uc.show_info(
                        "WARNING 010322.1054: there were "
                        + str(wrong_status)
                        + " pumps with wrong initial status!\n\n"
                        + "All wrong initial status were changed to 'OFF'.\n\n"
                        + "Edit them as wished with the 'Pumps' dialog from the Storm Drain Editor widget."
                    )

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error(
                    "ERROR 280222.1032: creation of Storm Drain Pumps User layer failed after reading "
                    + str(len(new_feats))
                    + " pumps!"
                    + "\n__________________________________________________",
                    e,
                )
                self.load_pumps = False

    def load_orifices_from_shapefile(self):
        if self.load_orifices:
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                fields = self.user_swmm_orifices_lyr.fields()
                new_feats = []
                outside_orifices = ""

                orifices_shapefile = self.orifices_shapefile_cbo.currentText()
                lyr = self.lyrs.get_layer_by_name(orifices_shapefile).layer()
                orifices_shapefile_fts = lyr.getFeatures()
                no_in_out = 0

                for f in orifices_shapefile_fts:
                    orifice_name = (
                        f[self.orifice_name_FieldCbo.currentText()]
                        if self.orifice_name_FieldCbo.currentText() != ""
                        else ""
                    )
                    orifice_inlet = (
                        f[self.orifice_from_inlet_FieldCbo.currentText()]
                        if self.orifice_from_inlet_FieldCbo.currentText() != ""
                        else "?"
                    )
                    orifice_inlet = orifice_inlet if orifice_inlet != NULL else "?"

                    orifice_outlet = (
                        f[self.orifice_to_outlet_FieldCbo.currentText()]
                        if self.orifice_to_outlet_FieldCbo.currentText() != ""
                        else "?"
                    )
                    orifice_outlet = orifice_outlet if orifice_outlet != NULL else "?"

                    orifice_type = (
                        f[self.orifice_type_FieldCbo.currentText()]
                        if self.orifice_type_FieldCbo.currentText() in ["SIDE", "BOTTOM"]
                        else "SIDE"
                    )
                    orifice_crest_height = (
                        f[self.orifice_crest_height_FieldCbo.currentText()]
                        if self.orifice_crest_height_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    orifice_disch_coeff = (
                        f[self.orifice_discharge_coeff_FieldCbo.currentText()]
                        if self.orifice_discharge_coeff_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    orifice_flap_gate = (
                        f[self.orifice_flap_gate_FieldCbo.currentText()]
                        if self.orifice_flap_gate_FieldCbo.currentText() in ["NO", "YES"]
                        else "NO"
                    )
                    orifice_open_close_time = (
                        f[self.orifice_time_open_close_FieldCbo.currentText()]
                        if self.orifice_time_open_close_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    orifice_shape = (
                        f[self.orifice_shape_FieldCbo.currentText()]
                        if self.orifice_shape_FieldCbo.currentText() in ["CIRCULAR", "RECT_CLOSED"]
                        else "CIRCULAR"
                    )
                    orifice_height = (
                        f[self.orifice_height_FieldCbo.currentText()]
                        if self.orifice_height_FieldCbo.currentText() != ""
                        else "0.0"
                    )
                    orifice_width = (
                        f[self.orifice_width_FieldCbo.currentText()]
                        if self.orifice_width_FieldCbo.currentText() != ""
                        else 0.0
                    )

                    if orifice_inlet == "?" or orifice_outlet == "?":
                        no_in_out += 1

                    feat = QgsFeature()
                    feat.setFields(fields)

                    geom = f.geometry()
                    if geom is None or geom.type() != 1:
                        self.uc.show_warn("WARNING 110422.0808: Error processing geometry of orifice  " + orifice_name)
                        continue

                    points = extractPoints(geom)
                    if points is None:
                        self.uc.show_warn("WARNING 1104220809.0951: Orifice  " + orifice_name + " is faulty!")
                        continue

                    cell = self.gutils.grid_on_point(points[0].x(), points[0].y())
                    if cell is None:
                        outside_orifices += "\n" + orifice_name
                        continue

                    cell = self.gutils.grid_on_point(points[1].x(), points[1].y())
                    if cell is None:
                        outside_orifices += "\n" + orifice_name
                        continue

                    new_geom = QgsGeometry.fromPolylineXY(points)
                    feat.setGeometry(new_geom)

                    feat.setAttribute("orifice_name", orifice_name)
                    feat.setAttribute("orifice_inlet", orifice_inlet)
                    feat.setAttribute("orifice_outlet", orifice_outlet)
                    feat.setAttribute("orifice_type", orifice_type)
                    feat.setAttribute("orifice_crest_height", orifice_crest_height)
                    feat.setAttribute("orifice_disch_coeff", orifice_disch_coeff)
                    feat.setAttribute("orifice_flap_gate", orifice_flap_gate)
                    feat.setAttribute("orifice_open_close_time", orifice_open_close_time)
                    feat.setAttribute("orifice_shape", orifice_shape)
                    feat.setAttribute("orifice_height", orifice_height)
                    feat.setAttribute("orifice_width", orifice_width)
                    new_feats.append(feat)

                if new_feats:
                    if not self.orifices_append_chbox.isChecked():
                        remove_features(self.user_swmm_orifices_lyr)

                    self.user_swmm_orifices_lyr.startEditing()
                    self.user_swmm_orifices_lyr.addFeatures(new_feats)
                    self.user_swmm_orifices_lyr.commitChanges()
                    self.user_swmm_orifices_lyr.updateExtents()
                    self.user_swmm_orifices_lyr.triggerRepaint()
                    self.user_swmm_orifices_lyr.removeSelection()
                else:
                    self.load_orifices = False

                QApplication.restoreOverrideCursor()

                if no_in_out != 0:
                    self.no_in_out += "\n" + str(no_in_out) + " orifices."

                if outside_orifices != "":
                    self.uc.show_warn(
                        "WARNING 110422.0811: The following orifices are outside the computational domain!\n"
                        + outside_orifices
                    )

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error(
                    "ERROR 110422.0813: creation of Storm Drain Orifices User layer failed after reading "
                    + str(len(new_feats))
                    + " orifices!"
                    + "\n__________________________________________________",
                    e,
                )
                self.load_orifices = False

    def load_weirs_from_shapefile(self):
        if self.load_weirs:
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                fields = self.user_swmm_weirs_lyr.fields()
                new_feats = []
                outside_weirs = ""

                weirs_shapefile = self.weirs_shapefile_cbo.currentText()
                lyr = self.lyrs.get_layer_by_name(weirs_shapefile).layer()
                weirs_shapefile_fts = lyr.getFeatures()
                no_in_out = 0
                wrong_types = 0
                wrong_shapes = 0

                for f in weirs_shapefile_fts:
                    weir_name = (
                        f[self.weir_name_FieldCbo.currentText()] if self.weir_name_FieldCbo.currentText() != "" else ""
                    )
                    weir_inlet = (
                        f[self.weir_from_inlet_FieldCbo.currentText()]
                        if self.weir_from_inlet_FieldCbo.currentText() != ""
                        else "?"
                    )
                    weir_inlet = weir_inlet if weir_inlet != NULL else "?"

                    weir_outlet = (
                        f[self.weir_to_outlet_FieldCbo.currentText()]
                        if self.weir_to_outlet_FieldCbo.currentText() != ""
                        else "?"
                    )
                    weir_outlet = weir_outlet if weir_outlet != NULL else "?"

                    weir_type = (
                        f[self.weir_type_FieldCbo.currentText()]
                        if self.weir_type_FieldCbo.currentText() != ""
                        else "TRANSVERSE"
                    )
                    if not weir_type in [
                        "TRANSVERSE",
                        "SIDEFLOW",
                        "V-NOTCH",
                        "TRAPEZOIDAL",
                    ]:
                        weir_type = "TRANSVERSE"
                        wrong_types += 1

                    weir_crest_height = (
                        f[self.weir_crest_height_FieldCbo.currentText()]
                        if self.weir_crest_height_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    weir_disch_coeff = (
                        f[self.weir_discharge_coeff_FieldCbo.currentText()]
                        if self.weir_discharge_coeff_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    weir_flap_gate = (
                        f[self.weir_flap_gate_FieldCbo.currentText()]
                        if self.weir_flap_gate_FieldCbo.currentText() in ["NO", "YES"]
                        else "NO"
                    )
                    weir_end_contrac = (
                        f[self.weir_end_contrac_FieldCbo.currentText()]
                        if self.weir_end_contrac_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    weir_end_coeff = (
                        f[self.weir_end_coeff_FieldCbo.currentText()]
                        if self.weir_end_coeff_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    weir_side_slope = (
                        f[self.weir_side_slope_FieldCbo.currentText()]
                        if self.weir_side_slope_FieldCbo.currentText() != ""
                        else 0.0
                    )
                    weir_shape = (
                        f[self.weir_shape_FieldCbo.currentText()]
                        if self.weir_shape_FieldCbo.currentText() != ""
                        else "RECT_CLOSED"
                    )
                    if not weir_shape in ["TRIANGULAR", "TRAPEZOIDAL", "RECT_CLOSED"]:
                        weir_shape = "RECT_CLOSED"
                        wrong_shapes += 1

                    weir_height = (
                        f[self.weir_height_FieldCbo.currentText()]
                        if self.weir_height_FieldCbo.currentText() != ""
                        else "0.0"
                    )
                    weir_length = (
                        f[self.weir_length_FieldCbo.currentText()]
                        if self.weir_length_FieldCbo.currentText() != ""
                        else 0.0
                    )

                    if weir_inlet == "?" or weir_outlet == "?":
                        no_in_out += 1

                    feat = QgsFeature()
                    feat.setFields(fields)

                    geom = f.geometry()
                    if geom is None or geom.type() != 1:
                        self.uc.show_warn("WARNING 120422.0838: Error processing geometry of weir  " + weir_name)
                        continue

                    points = extractPoints(geom)
                    if points is None:
                        self.uc.show_warn("WARNING 120422.0837: Weir  " + weir_name + " is faulty!")
                        continue

                    cell = self.gutils.grid_on_point(points[0].x(), points[0].y())
                    if cell is None:
                        outside_weirs += "\n" + weir_name
                        continue

                    cell = self.gutils.grid_on_point(points[1].x(), points[1].y())
                    if cell is None:
                        outside_weirs += "\n" + weir_name
                        continue

                    new_geom = QgsGeometry.fromPolylineXY(points)
                    feat.setGeometry(new_geom)

                    feat.setAttribute("weir_name", weir_name)
                    feat.setAttribute("weir_inlet", weir_inlet)
                    feat.setAttribute("weir_outlet", weir_outlet)
                    feat.setAttribute("weir_type", weir_type)
                    feat.setAttribute("weir_crest_height", weir_crest_height)
                    feat.setAttribute("weir_disch_coeff", weir_disch_coeff)
                    feat.setAttribute("weir_flap_gate", weir_flap_gate)
                    feat.setAttribute("weir_end_contrac", weir_end_contrac)
                    feat.setAttribute("weir_end_coeff", weir_end_coeff)
                    feat.setAttribute("weir_side_slope", weir_side_slope)
                    feat.setAttribute("weir_shape", weir_shape)
                    feat.setAttribute("weir_height", weir_height)
                    feat.setAttribute("weir_length", weir_length)
                    new_feats.append(feat)

                if new_feats:
                    if not self.weirs_append_chbox.isChecked():
                        remove_features(self.user_swmm_weirs_lyr)

                    self.user_swmm_weirs_lyr.startEditing()
                    self.user_swmm_weirs_lyr.addFeatures(new_feats)
                    self.user_swmm_weirs_lyr.commitChanges()
                    self.user_swmm_weirs_lyr.updateExtents()
                    self.user_swmm_weirs_lyr.triggerRepaint()
                    self.user_swmm_weirs_lyr.removeSelection()
                else:
                    self.load_weirs = False

                QApplication.restoreOverrideCursor()

                if no_in_out != 0:
                    self.no_in_out += "\n" + str(no_in_out) + "  weirs."

                if outside_weirs != "":
                    self.uc.show_warn(
                        "WARNING 110422.0845: The following weirs are outside the computational domain!\n"
                        + outside_weirs
                    )

                msg = ""
                if wrong_types > 0:
                    msg += "\nThere are " + str(wrong_types) + " weirs with wrong type!"
                if wrong_shapes > 0:
                    msg += "\nThere are " + str(wrong_shapes) + " weirs with wrong shape!"
                if msg != "":
                    self.uc.show_info("WARNING 020622.0540:\n" + msg + "\n\nDefault values were assigned.")

            except Exception as e:
                QApplication.restoreOverrideCursor()
                self.uc.show_error(
                    "ERROR 110422.0846: creation of Storm Drain Weirs User layer failed after reading "
                    + str(len(new_feats))
                    + " weirs!"
                    + "\n__________________________________________________",
                    e,
                )
                self.load_weirs = False

    # def post_process_outside_features(self):
    #     """
    #     Function to remove features that are not connected to the grid.
    #     """
    #     junctions_connected_to_conduits = []
    #     if self.load_conduits:
    #         conduits_weirs_shapefile = self.weirs_shapefile_cbo.currentText()
    #         lyr = self.lyrs.get_layer_by_name(weirs_shapefile).layer()
    #     if self.load_outfalls:
    #             outfalls_shapefile_fts = lyr.getFeatures()

    def cancel_message(self):
        self.uc.bar_info("No data was selected!")

    def save_storm_drain_shapefile_field_names(self):
        """
        Function to save the storm drain shapefiles names into the sd_fields
        """
        sd_shapefile_fields_dict = {
            "sf_inlets_layer_name": self.inlets_shapefile_cbo.currentText(),
            "sf_inlets_name": self.inlets_name_FieldCbo.currentText(),
            "sf_inlets_type": self.inlets_type_FieldCbo.currentText(),
            "sf_inlets_invert_elevation": self.inlets_invert_elevation_FieldCbo.currentText(),
            "sf_inlets_max_depth": self.inlets_max_depth_FieldCbo.currentText(),
            "sf_inlets_init_depth": self.inlets_init_depth_FieldCbo.currentText(),
            "sf_inlets_surcharge_depth": self.inlets_surcharge_depth_FieldCbo.currentText(),
            "sf_inlets_length_perimeter": self.inlets_length_perimeter_FieldCbo.currentText(),
            "sf_inlets_width_area": self.inlets_width_area_FieldCbo.currentText(),
            "sf_inlets_height_sag_surch": self.inlets_height_sag_surch_FieldCbo.currentText(),
            "sf_inlets_weir_coeff": self.inlets_weir_coeff_FieldCbo.currentText(),
            "sf_inlets_feature": self.inlets_feature_FieldCbo.currentText(),
            "sf_inlets_curb_height": self.inlets_curb_height_FieldCbo.currentText(),
            "sf_inlets_clogging_factor": self.inlets_clogging_factor_FieldCbo.currentText(),
            "sf_inlets_time_for_clogging": self.inlets_time_for_clogging_FieldCbo.currentText(),
            "sf_inlets_dropbox_area": self.inlets_dropbox_area_FieldCbo.currentText(),
            "sf_outfalls_layer_name": self.outfalls_shapefile_cbo.currentText(),
            "sf_outfalls_name": self.outfall_name_FieldCbo.currentText(),
            "sf_outfalls_invert_elevation": self.outfall_invert_elevation_FieldCbo.currentText(),
            "sf_outfalls_flap_gate": self.outfall_flap_gate_FieldCbo.currentText(),
            "sf_outfalls_allow_discharge": self.outfall_allow_discharge_FieldCbo.currentText(),
            "sf_outfalls_type": self.outfall_type_FieldCbo.currentText(),
            "sf_outfalls_water_depth": self.outfall_water_depth_FieldCbo.currentText(),
            "sf_outfalls_tidal_curve": self.outfall_tidal_curve_FieldCbo.currentText(),
            "sf_outfalls_time_series": self.outfall_time_series_FieldCbo.currentText(),
            'sf_strge_units_layer_name': self.strge_units_shapefile_cbo.currentText(),
            'sf_strge_unit_name': self.strge_unit_name_FieldCbo.currentText(),
            'sf_strge_unit_invert_elevation': self.strge_unit_invert_elevation_FieldCbo.currentText(),
            'sf_strge_unit_max_depth': self.strge_unit_max_depth_FieldCbo.currentText(),
            'sf_strge_unit_initial_depth': self.strge_unit_initial_depth_FieldCbo.currentText(),
            'sf_strge_unit_external_inflow': self.strge_unit_external_inflow_FieldCbo.currentText(),
            # 'sf_strge_unit_ponded_area': self.strge_unit_ponded_area_FieldCbo.currentText(),
            'sf_strge_unit_evap_factor': self.strge_unit_evap_factor_FieldCbo.currentText(),
            'sf_strge_unit_treatment': self.strge_unit_treatment_FieldCbo.currentText(),
            'sf_strge_unit_infiltration': self.strge_unit_infiltration_FieldCbo.currentText(),
            'sf_strge_unit_infil_method': self.strge_unit_infil_method_FieldCbo.currentText(),
            'sf_strge_unit_suction_head': self.strge_unit_suction_head_FieldCbo.currentText(),
            'sf_strge_unit_conductivity': self.strge_unit_conductivity_FieldCbo.currentText(),
            'sf_strge_unit_initial_deficit': self.strge_unit_initial_deficit_FieldCbo.currentText(),
            'sf_strge_unit_storage_curve': self.strge_unit_storage_curve_FieldCbo.currentText(),
            'sf_strge_unit_coefficient': self.strge_unit_coefficient_FieldCbo.currentText(),
            'sf_strge_unit_exponent': self.strge_unit_exponent_FieldCbo.currentText(),
            'sf_strge_unit_constant': self.strge_unit_constant_FieldCbo.currentText(),
            'sf_strge_unit_curve_name': self.strge_unit_curve_name_FieldCbo.currentText(),
            "sf_conduits_layer_name": self.conduits_shapefile_cbo.currentText(),
            "sf_conduits_name": self.conduit_name_FieldCbo.currentText(),
            "sf_conduits_from_inlet": self.conduit_from_inlet_FieldCbo.currentText(),
            "sf_conduits_to_outlet": self.conduit_to_outlet_FieldCbo.currentText(),
            "sf_conduits_inlet_offset": self.conduit_inlet_offset_FieldCbo.currentText(),
            "sf_conduits_outlet_offset": self.conduit_outlet_offset_FieldCbo.currentText(),
            "sf_conduits_shape": self.conduit_shape_FieldCbo.currentText(),
            "sf_conduits_barrels": self.conduit_barrels_FieldCbo.currentText(),
            "sf_conduits_max_depth": self.conduit_max_depth_FieldCbo.currentText(),
            "sf_conduits_geom2": self.conduit_geom2_FieldCbo.currentText(),
            "sf_conduits_geom3": self.conduit_geom3_FieldCbo.currentText(),
            "sf_conduits_geom4": self.conduit_geom4_FieldCbo.currentText(),
            "sf_conduits_length": self.conduit_length_FieldCbo.currentText(),
            "sf_conduits_manning": self.conduit_manning_FieldCbo.currentText(),
            "sf_conduits_initial_flow": self.conduit_initial_flow_FieldCbo.currentText(),
            "sf_conduits_max_flow": self.conduit_max_flow_FieldCbo.currentText(),
            "sf_conduits_entry_loss": self.conduit_entry_loss_FieldCbo.currentText(),
            "sf_conduits_exit_loss": self.conduit_exit_loss_FieldCbo.currentText(),
            "sf_conduits_average_loss": self.conduit_average_loss_FieldCbo.currentText(),
            "sf_conduits_flap_gate": self.conduit_flap_gate_FieldCbo.currentText(),
            "sf_pumps_layer_name": self.pumps_shapefile_cbo.currentText(),
            "sf_pump_name": self.pump_name_FieldCbo.currentText(),
            "sf_pump_from_inlet": self.pump_from_inlet_FieldCbo.currentText(),
            "sf_pump_to_outlet": self.pump_to_outlet_FieldCbo.currentText(),
            "sf_pump_init_status": self.pump_initial_status_FieldCbo.currentText(),
            "sf_pump_startup_depth": self.pump_startup_depth_FieldCbo.currentText(),
            "sf_pump_shutoff_depth": self.pump_shutoff_depth_FieldCbo.currentText(),
            "sf_pump_curve_name": self.pump_curve_name_FieldCbo.currentText(),
            "sf_pump_curve_type": self.pump_curve_type_FieldCbo.currentText(),
            "sf_pump_curve_description": self.pump_curve_description_FieldCbo.currentText(),
            "sf_orifices_layer_name": self.orifices_shapefile_cbo.currentText(),
            "sf_orifice_name": self.orifice_name_FieldCbo.currentText(),
            "sf_orifice_from_inlet": self.orifice_from_inlet_FieldCbo.currentText(),
            "sf_orifice_to_outlet": self.orifice_to_outlet_FieldCbo.currentText(),
            "sf_orifice_type": self.orifice_type_FieldCbo.currentText(),
            "sf_orifice_crest_height": self.orifice_crest_height_FieldCbo.currentText(),
            "sf_orifice_disch_coeff": self.orifice_discharge_coeff_FieldCbo.currentText(),
            "sf_orifice_flap_gate": self.orifice_flap_gate_FieldCbo.currentText(),
            "sf_orifice_open_close_time": self.orifice_time_open_close_FieldCbo.currentText(),
            "sf_orifice_shape": self.orifice_shape_FieldCbo.currentText(),
            "sf_orifice_height": self.orifice_height_FieldCbo.currentText(),
            "sf_orifice_width": self.orifice_width_FieldCbo.currentText(),
            "sf_weirs_layer_name": self.weirs_shapefile_cbo.currentText(),
            "sf_weir_name": self.weir_name_FieldCbo.currentText(),
            "sf_weir_from_inlet": self.weir_from_inlet_FieldCbo.currentText(),
            "sf_weir_to_outlet": self.weir_to_outlet_FieldCbo.currentText(),
            "sf_weir_type": self.weir_type_FieldCbo.currentText(),
            "sf_weir_crest_height": self.weir_crest_height_FieldCbo.currentText(),
            "sf_weir_disch_coeff": self.weir_discharge_coeff_FieldCbo.currentText(),
            "sf_weir_flap_gate": self.weir_flap_gate_FieldCbo.currentText(),
            "sf_weir_end_contrac": self.weir_end_contrac_FieldCbo.currentText(),
            "sf_weir_end_coeff": self.weir_end_coeff_FieldCbo.currentText(),
            "sf_weir_side_slope": self.weir_side_slope_FieldCbo.currentText(),
            "sf_weir_shape": self.weir_shape_FieldCbo.currentText(),
            "sf_weir_height": self.weir_height_FieldCbo.currentText(),
            "sf_weir_length": self.weir_length_FieldCbo.currentText()
        }

        self.gutils.clear_tables('sd_fields')

        for key, value in sd_shapefile_fields_dict.items():
            self.gutils.execute(f"INSERT INTO sd_fields (name, field) VALUES ('{key}', '{value}')")

    def restore_storm_drain_shapefile_fields(self):
        self.clear_all_SD_shapefile_fields()

        self.restore_SD_shapefile_inlet_field_names()
        self.restore_SD_shapefile_outfall_field_names()
        self.restore_SD_shapefile_strge_units_field_names()
        self.restore_SD_shapefile_conduit_field_names()
        self.restore_SD_shapefile_pump_field_names()
        self.restore_SD_shapefile_orifice_field_names()
        self.restore_SD_shapefile_weir_field_names()

    def clear_all_SD_shapefile_fields(self):
        self.clear_all_inlet_attributes()
        self.clear_all_outfall_attributes()
        self.clear_all_strge_units_attributes()
        self.clear_all_conduit_attributes()
        self.clear_all_pump_attributes()
        self.clear_all_orifice_attributes()
        self.clear_all_weir_attributes()

    def restore_SD_shapefile_inlet_field_names(self):
        # Inlets/Junctions:
        sf_inlets_layer_name = self.gutils.execute(f"SELECT field FROM sd_fields WHERE name = 'sf_inlets_layer_name'").fetchone()
        layer = "" if sf_inlets_layer_name is None else sf_inlets_layer_name[0]
        if layer != "":
            if layer == self.inlets_shapefile_cbo.currentText():
                lyr = self.lyrs.get_layer_by_name(layer).layer()
                field_names = [field.name() for field in lyr.fields()]
                
                self.inlets_name_FieldCbo.setField(self.restore_field_name("sf_inlets_name", field_names))
                self.inlets_type_FieldCbo.setField(self.restore_field_name("sf_inlets_type", field_names))
                self.inlets_invert_elevation_FieldCbo.setField(self.restore_field_name("sf_inlets_invert_elevation", field_names))
                self.inlets_max_depth_FieldCbo.setField(self.restore_field_name("sf_inlets_max_depth", field_names))
                self.inlets_init_depth_FieldCbo.setField(self.restore_field_name("sf_inlets_init_depth", field_names))
                self.inlets_surcharge_depth_FieldCbo.setField(self.restore_field_name("sf_inlets_surcharge_depth", field_names))
                self.inlets_length_perimeter_FieldCbo.setField(self.restore_field_name("sf_inlets_length_perimeter", field_names))
                self.inlets_width_area_FieldCbo.setField(self.restore_field_name("sf_inlets_width_area", field_names))
                self.inlets_height_sag_surch_FieldCbo.setField( self.restore_field_name("sf_inlets_height_sag_surch", field_names))
                self.inlets_weir_coeff_FieldCbo.setField(self.restore_field_name("sf_inlets_weir_coeff", field_names))
                self.inlets_feature_FieldCbo.setField(self.restore_field_name("sf_inlets_feature", field_names))
                self.inlets_curb_height_FieldCbo.setField(self.restore_field_name("sf_inlets_curb_height", field_names))
                self.inlets_clogging_factor_FieldCbo.setField( self.restore_field_name("sf_inlets_clogging_factor", field_names))
                self.inlets_time_for_clogging_FieldCbo.setField(self.restore_field_name("sf_inlets_time_for_clogging", field_names))
                self.inlets_dropbox_area_FieldCbo.setField(self.restore_field_name("sf_inlets_dropbox_area", field_names))
            else:
                self.smart_assign_inlets()
                
        elif layer == "":
            if self.inlets_shapefile_cbo.currentText() != "":
                self.smart_assign_inlets()
        else:
            self.clear_all_inlet_attributes()

    def smart_assign_inlets(self):
        try:
            lyr = self.lyrs.get_layer_by_name(self.inlets_shapefile_cbo.currentText()).layer()
            lyr_fields = lyr.fields()
            for index, field in enumerate(lyr_fields):
                field_name = field.name()
                if "name" in field_name.lower():
                    self.inlets_name_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.inlets_name_FieldCbo, "name"))
                if "type" in field_name.lower():
                    self.inlets_type_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.inlets_type_FieldCbo, "type"))
                if "elev" in field_name.lower():
                    self.inlets_invert_elevation_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.inlets_invert_elevation_FieldCbo, "elev"))
                if "max" in field_name.lower():
                    self.inlets_max_depth_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.inlets_max_depth_FieldCbo, "max"))
                if "init" in field_name.lower():
                    self.inlets_init_depth_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.inlets_init_depth_FieldCbo, "init"))
                if "surch" in field_name.lower():
                    self.inlets_surcharge_depth_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.inlets_surcharge_depth_FieldCbo, "surch"))
                if "len" in field_name.lower():
                    self.inlets_length_perimeter_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.inlets_length_perimeter_FieldCbo, "len"))
                if "width" in field_name.lower():
                    self.inlets_width_area_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.inlets_width_area_FieldCbo, "width"))
                if "height" in field_name.lower():
                    self.inlets_height_sag_surch_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.inlets_height_sag_surch_FieldCbo, "height"))
                if "coeff" in field_name.lower():
                    self.inlets_weir_coeff_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.inlets_weir_coeff_FieldCbo, "coeff"))
                if "feature" in field_name.lower():
                    self.inlets_feature_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.inlets_feature_FieldCbo, "feature"))
                if "curb" in field_name.lower():
                    self.inlets_curb_height_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.inlets_curb_height_FieldCbo, "curb"))
                if "factor" in field_name.lower():
                    self.inlets_clogging_factor_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.inlets_clogging_factor_FieldCbo, "factor"))
                if "time" in field_name.lower():
                    self.inlets_time_for_clogging_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.inlets_time_for_clogging_FieldCbo, "time"))
                if "box" in field_name.lower():
                    self.inlets_dropbox_area_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.inlets_dropbox_area_FieldCbo, "box"))   
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_info("ERROR 240524.1207: inlets shapefile " + self.inlets_shapefile_cbo.currentText() + " not found in the layers panel!")                                       

    def restore_SD_shapefile_outfall_field_names(self):
        # Outfalls
        sf_outfalls_layer_name = self.gutils.execute(f"SELECT field FROM sd_fields WHERE name = 'sf_outfalls_layer_name'").fetchone()
        layer = "" if sf_outfalls_layer_name is None else sf_outfalls_layer_name[0]
        if layer != "":
            if layer == self.outfalls_shapefile_cbo.currentText():
                lyr = self.lyrs.get_layer_by_name(layer).layer()
                field_names = [field.name() for field in lyr.fields()]

                self.outfall_name_FieldCbo.setField(self.restore_field_name("sf_outfalls_name", field_names))
                self.outfall_invert_elevation_FieldCbo.setField(self.restore_field_name("sf_outfalls_invert_elevation", field_names))
                self.outfall_flap_gate_FieldCbo.setField(self.restore_field_name("sf_outfalls_flap_gate", field_names))
                self.outfall_allow_discharge_FieldCbo.setField(self.restore_field_name("sf_outfalls_allow_discharge", field_names))
                self.outfall_type_FieldCbo.setField(self.restore_field_name("sf_outfalls_type", field_names))
                self.outfall_water_depth_FieldCbo.setField(self.restore_field_name("sf_outfalls_water_depth", field_names))
                self.outfall_tidal_curve_FieldCbo.setField(self.restore_field_name("sf_outfalls_tidal_curve", field_names))
                self.outfall_time_series_FieldCbo.setField(self.restore_field_name("sf_outfalls_time_series", field_names))

            else:
                self.smart_assign_outfalls()
        elif layer == "":
            if self.outfalls_shapefile_cbo.currentText() != "":
                self.smart_assign_outfalls()
        else:
            self.clear_all_outfall_attributes()

    def smart_assign_outfalls(self):
        try:
            lyr = self.lyrs.get_layer_by_name(self.outfalls_shapefile_cbo.currentText()).layer()
            lyr_fields = lyr.fields()
            for index, field in enumerate(lyr_fields):
                field_name = field.name()
                if "name" in field_name.lower():
                    self.outfall_name_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.outfall_name_FieldCbo, "name"))
                if "elev" in field_name.lower():
                    self.outfall_invert_elevation_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.outfall_invert_elevation_FieldCbo, "elev"))
                if "flapgate" in field_name.lower():
                    self.outfall_flap_gate_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.outfall_flap_gate_FieldCbo, "flapgate"))
                if "allow" in field_name.lower():
                    self.outfall_allow_discharge_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.outfall_allow_discharge_FieldCbo, "allow"))
                if "type" in field_name.lower():
                    self.outfall_type_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.outfall_type_FieldCbo, "type"))
                if "stage" in field_name.lower():
                    self.outfall_water_depth_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.outfall_water_depth_FieldCbo, "stage"))
                if "curve" in field_name.lower():
                    self.outfall_tidal_curve_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.outfall_tidal_curve_FieldCbo, "curve"))
                if "series" in field_name.lower():
                    self.outfall_time_series_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.outfall_time_series_FieldCbo, "series")) 
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_info("ERROR 240524.1208: outfalls shapefile " + self.inlets_shapefile_cbo.currentText() + " not found in the layers panel!")                         
        
    def restore_SD_shapefile_strge_units_field_names(self):
        # Storage Units:
        sf_strge_units_layer_name = self.gutils.execute(f"SELECT field FROM sd_fields WHERE name = 'sf_strge_units_layer_name'").fetchone()
        layer = "" if sf_strge_units_layer_name is None else sf_strge_units_layer_name[0]
        if layer != "":
            if layer == self.strge_units_shapefile_cbo.currentText():
                lyr = self.lyrs.get_layer_by_name(layer).layer()
                field_names = [field.name() for field in lyr.fields()]
                
                self.strge_unit_name_FieldCbo.setField(self.restore_field_name("sf_strge_unit_name", field_names))
                self.strge_unit_invert_elevation_FieldCbo.setField(self.restore_field_name("sf_strge_unit_invert_elevation", field_names))
                self.strge_unit_max_depth_FieldCbo.setField(self.restore_field_name("sf_strge_unit_max_depth", field_names))
                self.strge_unit_initial_depth_FieldCbo.setField(self.restore_field_name("sf_strge_unit_initial_depth", field_names))
                self.strge_unit_external_inflow_FieldCbo.setField(self.restore_field_name("sf_strge_unit_external_inflow", field_names))
                self.strge_unit_evap_factor_FieldCbo.setField(self.restore_field_name("sf_strge_unit_evap_factor", field_names))
                self.strge_unit_treatment_FieldCbo.setField(self.restore_field_name("sf_strge_unit_treatment", field_names))
                self.strge_unit_infiltration_FieldCbo.setField(self.restore_field_name("sf_strge_unit_infiltration", field_names))
                self.strge_unit_infil_method_FieldCbo.setField(self.restore_field_name("sf_strge_unit_infil_method", field_names))
                self.strge_unit_suction_head_FieldCbo.setField(self.restore_field_name("sf_strge_unit_suction_head", field_names))
                self.strge_unit_conductivity_FieldCbo.setField(self.restore_field_name("sf_strge_unit_conductivity", field_names))
                self.strge_unit_initial_deficit_FieldCbo.setField(self.restore_field_name("sf_strge_unit_initial_deficit", field_names))
                self.strge_unit_storage_curve_FieldCbo.setField(self.restore_field_name("sf_strge_unit_storage_curve", field_names))
                self.strge_unit_coefficient_FieldCbo.setField(self.restore_field_name("sf_strge_unit_coefficient", field_names))
                self.strge_unit_exponent_FieldCbo.setField(self.restore_field_name("sf_strge_unit_exponent", field_names))
                self.strge_unit_constant_FieldCbo.setField(self.restore_field_name("sf_strge_unit_constant", field_names))
                self.strge_unit_curve_name_FieldCbo.setField(self.restore_field_name("sf_strge_unit_curve_name", field_names))
            else:
                self.assign_smart_strge_units()
        elif layer == "":
            if self.strge_units_shapefile_cbo.currentText() != "":
                self.assign_smart_strge_units()
                

        else:
            self.clear_all_strge_units_attributes()

    def assign_smart_strge_units(self):
        try:
            lyr = self.lyrs.get_layer_by_name(self.strge_units_shapefile_cbo.currentText()).layer()
            lyr_fields = lyr.fields()
            for index, field in enumerate(lyr_fields):
                field_name = field.name()
                if "name" in field_name.lower():
                    self.strge_unit_name_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.strge_unit_name_FieldCbo, "name"))
                if "elev" in field_name.lower():
                    self.strge_unit_invert_elevation_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.strge_unit_invert_elevation_FieldCbo, "elev"))
                if "max" in field_name.lower():
                    self.strge_unit_max_depth_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.strge_unit_max_depth_FieldCbo, "max"))
                if "init" in field_name.lower():
                    self.strge_unit_initial_depth_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.strge_unit_initial_depth_FieldCbo, "init"))
                if "external" in field_name.lower():
                    self.strge_unit_external_inflow_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.strge_unit_external_inflow_FieldCbo, "external"))
                if "evap" in field_name.lower():
                    self.strge_unit_evap_factor_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.strge_unit_evap_factor_FieldCbo, "evap"))
                if "treat" in field_name.lower():
                    self.strge_unit_treatment_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.strge_unit_treatment_FieldCbo, "treat"))
                if "infil" in field_name.lower():
                    self.strge_unit_infiltration_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.strge_unit_infiltration_FieldCbo, "infil"))
                if "method" in field_name.lower():
                    self.strge_unit_infil_method_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.strge_unit_infil_method_FieldCbo, "method"))
                if "suction" in field_name.lower():
                    self.strge_unit_suction_head_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.strge_unit_suction_head_FieldCbo, "suction"))
                if "conduc" in field_name.lower():
                    self.strge_unit_conductivity_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.strge_unit_conductivity_FieldCbo, "conduc"))
                if "deficit" in field_name.lower():
                    self.strge_unit_initial_deficit_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.strge_unit_initial_deficit_FieldCbo, "deficit"))
                if "curve" in field_name.lower():
                    self.strge_unit_storage_curve_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.strge_unit_storage_curve_FieldCbo, "curve"))
                if "coeff" in field_name.lower():
                    self.strge_unit_coefficient_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.strge_unit_coefficient_FieldCbo, "coeff"))
                if "exponent" in field_name.lower():
                    self.strge_unit_exponent_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.strge_unit_exponent_FieldCbo, "exponent"))
                if "constant" in field_name.lower():
                    self.strge_unit_constant_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.strge_unit_constant_FieldCbo, "constant"))
                if "name" in field_name.lower():
                    self.strge_unit_curve_name_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.strge_unit_curve_name_FieldCbo, "name"))
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_info("ERROR 240524.1216: storage units shapefile " + self.inlets_shapefile_cbo.currentText() + " not found in the layers panel!")  

    def restore_SD_shapefile_conduit_field_names(self):
        # Conduits:
        sf_conduits_layer_name = self.gutils.execute(f"SELECT field FROM sd_fields WHERE name = 'sf_conduits_layer_name'").fetchone()
        layer = "" if sf_conduits_layer_name is None else sf_conduits_layer_name[0]
        if layer != "":
            if layer == self.conduits_shapefile_cbo.currentText():
                lyr = self.lyrs.get_layer_by_name(layer).layer()
                field_names = [field.name() for field in lyr.fields()]

                self.conduit_name_FieldCbo.setField(self.restore_field_name("sf_conduits_name", field_names))
                self.conduit_from_inlet_FieldCbo.setField(self.restore_field_name("sf_conduits_from_inlet", field_names))
                self.conduit_to_outlet_FieldCbo.setField(self.restore_field_name("sf_conduits_to_outlet", field_names))
                self.conduit_inlet_offset_FieldCbo.setField(self.restore_field_name("sf_conduits_inlet_offset", field_names))
                self.conduit_outlet_offset_FieldCbo.setField(self.restore_field_name("sf_conduits_outlet_offset", field_names))
                self.conduit_shape_FieldCbo.setField(self.restore_field_name("sf_conduits_shape", field_names))
                self.conduit_barrels_FieldCbo.setField(self.restore_field_name("sf_conduits_barrels", field_names))
                self.conduit_max_depth_FieldCbo.setField(self.restore_field_name("sf_conduits_max_depth", field_names))
                self.conduit_geom2_FieldCbo.setField(self.restore_field_name("sf_conduits_geom2", field_names))
                self.conduit_geom3_FieldCbo.setField(self.restore_field_name("sf_conduits_geom3", field_names))
                self.conduit_geom4_FieldCbo.setField(self.restore_field_name("sf_conduits_geom4", field_names))
                self.conduit_length_FieldCbo.setField(self.restore_field_name("sf_conduits_length", field_names))
                self.conduit_manning_FieldCbo.setField(self.restore_field_name("sf_conduits_manning", field_names))
                self.conduit_initial_flow_FieldCbo.setField(self.restore_field_name("sf_conduits_initial_flow", field_names))
                self.conduit_max_flow_FieldCbo.setField(self.restore_field_name("sf_conduits_max_flow", field_names))
                self.conduit_entry_loss_FieldCbo.setField(self.restore_field_name("sf_conduits_entry_loss", field_names))
                self.conduit_exit_loss_FieldCbo.setField(self.restore_field_name("sf_conduits_exit_loss", field_names))
                self.conduit_average_loss_FieldCbo.setField(self.restore_field_name("sf_conduits_average_loss", field_names))
                self.conduit_flap_gate_FieldCbo.setField(self.restore_field_name("sf_conduits_flap_gate", field_names))

            else:
                self.assign_smart_conduits()
        elif layer == "":
            if self.conduits_shapefile_cbo.currentText() != "":
                self.assign_smart_conduits()
        else:
            self.clear_all_conduit_attributes()

    def assign_smart_conduits(self):
        try: 
            lyr = self.lyrs.get_layer_by_name(self.conduits_shapefile_cbo.currentText()).layer()
            lyr_fields = lyr.fields()
            for index, field in enumerate(lyr_fields):
                field_name = field.name()
                if "name" in field_name.lower():
                    self.conduit_name_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_name_FieldCbo, "name"))
                if "inlet" in field_name.lower():
                    self.conduit_from_inlet_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_from_inlet_FieldCbo, "inlet"))
                if "outlet" in field_name.lower():
                    self.conduit_to_outlet_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_to_outlet_FieldCbo, "outlet"))
                if "inlet" in field_name.lower() and "offset" in field_name.lower():
                    self.conduit_inlet_offset_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_inlet_offset_FieldCbo, "inlet"))
                if "outlet" in field_name.lower() and "offset" in field_name.lower():
                    self.conduit_outlet_offset_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_outlet_offset_FieldCbo, "outlet"))
                if "shape" in field_name.lower():
                    self.conduit_shape_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_shape_FieldCbo, "shape"))
                if "barrels" in field_name.lower():
                    self.conduit_barrels_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_barrels_FieldCbo, "barrels"))
                if "max" in field_name.lower():
                    self.conduit_max_depth_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_max_depth_FieldCbo, "max"))
                if "geom2" in field_name.lower():
                    self.conduit_geom2_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_geom2_FieldCbo, "geom2"))
                if "geom3" in field_name.lower():
                    self.conduit_geom3_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_geom3_FieldCbo, "geom3"))
                if "geom4" in field_name.lower():
                    self.conduit_geom4_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_geom4_FieldCbo, "geom4"))
                if "length" in field_name.lower():
                    self.conduit_length_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_length_FieldCbo, "length"))
                if "manning" in field_name.lower():
                    self.conduit_manning_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_manning_FieldCbo, "manning"))
                if "init" in field_name.lower() and "flow" in field_name.lower():
                    self.conduit_initial_flow_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_initial_flow_FieldCbo, "init"))
                if "max" in field_name.lower() and "flow" in field_name.lower():
                    self.conduit_max_flow_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_max_flow_FieldCbo, "max"))
                if "loss" in field_name.lower() and "inlet" in field_name.lower():
                    self.conduit_entry_loss_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_entry_loss_FieldCbo, "loss"))
                if "loss" in field_name.lower() and "outlet" in field_name.lower():
                    self.conduit_exit_loss_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_exit_loss_FieldCbo, "loss"))
                if "average" in field_name.lower():
                    self.conduit_average_loss_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_average_loss_FieldCbo, "average"))
                if "flapgate" in field_name.lower():
                    self.conduit_flap_gate_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.conduit_flap_gate_FieldCbo, "flapgate"))        
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_info("ERROR 240524.1209: conduits shapefile " + self.inlets_shapefile_cbo.currentText() + " not found in the layers panel!")  

    def restore_SD_shapefile_pump_field_names(self):
        # Pumps:
        sf_pumps_layer_name = self.gutils.execute(f"SELECT field FROM sd_fields WHERE name = 'sf_pumps_layer_name'").fetchone()
        layer = "" if sf_pumps_layer_name is None else sf_pumps_layer_name[0]
        if layer != "":
            if layer == self.pumps_shapefile_cbo.currentText():
                lyr = self.lyrs.get_layer_by_name(layer).layer()
                field_names = [field.name() for field in lyr.fields()]

                self.pump_name_FieldCbo.setField(self.restore_field_name("sf_pump_name", field_names))
                self.pump_from_inlet_FieldCbo.setField(self.restore_field_name("sf_pump_from_inlet", field_names))
                self.pump_to_outlet_FieldCbo.setField(self.restore_field_name("sf_pump_to_outlet", field_names))
                self.pump_initial_status_FieldCbo.setField( self.restore_field_name("sf_pump_init_status", field_names))
                self.pump_startup_depth_FieldCbo.setField(self.restore_field_name("sf_pump_startup_depth", field_names))
                self.pump_shutoff_depth_FieldCbo.setField(self.restore_field_name("sf_pump_shutoff_depth", field_names))
                self.pump_curve_name_FieldCbo.setField(self.restore_field_name("sf_pump_curve_name", field_names))
                self.pump_curve_type_FieldCbo.setField(self.restore_field_name("sf_pump_curve_type", field_names))
                self.pump_curve_description_FieldCbo.setField(self.restore_field_name("sf_pump_curve_description", field_names))

            else:
                self.assign_smart_pumps()
        elif layer == "":
            if self.pumps_shapefile_cbo.currentText() != "":
                self.assign_smart_pumps()
        else:
            self.clear_all_pump_attributes()

    def assign_smart_pumps(self):
        try:
            lyr = self.lyrs.get_layer_by_name(self.pumps_shapefile_cbo.currentText()).layer()
            lyr_fields = lyr.fields()
            for index, field in enumerate(lyr_fields):
                field_name = field.name()
                if "name" in field_name.lower():
                    self.pump_name_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.pump_name_FieldCbo, "name"))
                if "inlet" in field_name.lower():
                    self.pump_from_inlet_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.pump_from_inlet_FieldCbo, "inlet"))
                if "outlet" in field_name.lower():
                    self.pump_to_outlet_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.pump_to_outlet_FieldCbo, "outlet"))
                if "status" in field_name.lower():
                    self.pump_initial_status_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.pump_initial_status_FieldCbo, "status"))
                if "startup" in field_name.lower():
                    self.pump_startup_depth_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.pump_startup_depth_FieldCbo, "startup"))
                if "shutoff" in field_name.lower():
                    self.pump_shutoff_depth_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.pump_shutoff_depth_FieldCbo, "shutoff"))
                if "curve" in field_name.lower():
                    self.pump_curve_name_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.pump_curve_name_FieldCbo, "curve"))
                if "type" in field_name.lower():
                    self.pump_curve_type_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.pump_curve_type_FieldCbo, "type"))
                if "description" in field_name.lower():
                    self.pump_curve_description_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.pump_curve_description_FieldCbo, "description"))        
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_info("ERROR 240524.1213: pumps shapefile " + self.inlets_shapefile_cbo.currentText() + " not found in the layers panel!")  
            
    def restore_SD_shapefile_orifice_field_names(self):
        # Orifices:
        sf_orifices_layer_name = self.gutils.execute(f"SELECT field FROM sd_fields WHERE name = 'sf_orifices_layer_name'").fetchone()
        layer = "" if sf_orifices_layer_name is None else sf_orifices_layer_name[0]
        if layer != "":
            if layer == self.orifices_shapefile_cbo.currentText():
                lyr = self.lyrs.get_layer_by_name(layer).layer()
                field_names = [field.name() for field in lyr.fields()]

                self.orifice_name_FieldCbo.setField(self.restore_field_name("sf_orifice_name", field_names))
                self.orifice_from_inlet_FieldCbo.setField(self.restore_field_name("sf_orifice_from_inlet", field_names))
                self.orifice_to_outlet_FieldCbo.setField(self.restore_field_name("sf_orifice_to_outlet", field_names))
                self.orifice_type_FieldCbo.setField( self.restore_field_name("sf_orifice_type", field_names))
                self.orifice_crest_height_FieldCbo.setField(self.restore_field_name("sf_orifice_crest_height", field_names))
                self.orifice_discharge_coeff_FieldCbo.setField(self.restore_field_name("sf_orifice_disch_coeff", field_names))
                self.orifice_flap_gate_FieldCbo.setField(self.restore_field_name("sf_orifice_flap_gate", field_names))
                self.orifice_time_open_close_FieldCbo.setField(self.restore_field_name("sf_orifice_open_close_time", field_names))
                self.orifice_shape_FieldCbo.setField(self.restore_field_name("sf_orifice_shape", field_names))
                self.orifice_height_FieldCbo.setField(self.restore_field_name("sf_orifice_height", field_names))
                self.orifice_width_FieldCbo.setField(self.restore_field_name("sf_orifice_width", field_names))

            else:
                self.smart_assign_orifices()
        elif layer == "":
            if self.orifices_shapefile_cbo.currentText() != "":
                self.smart_assign_orifices()
        else:
            self.clear_all_orifice_attributes()

    def smart_assign_orifices(self):
        try:
            lyr = self.lyrs.get_layer_by_name(self.orifices_shapefile_cbo.currentText()).layer()
            lyr_fields = lyr.fields()
            for index, field in enumerate(lyr_fields):
                field_name = field.name()
                if "name" in field_name.lower():
                    self.orifice_name_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.orifice_name_FieldCbo, "name"))
                if "inlet" in field_name.lower():
                    self.orifice_from_inlet_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.orifice_from_inlet_FieldCbo, "inlet"))
                if "outlet" in field_name.lower():
                    self.orifice_to_outlet_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.orifice_to_outlet_FieldCbo, "outlet"))
                if "type" in field_name.lower():
                    self.orifice_type_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.orifice_type_FieldCbo, "type"))
                if "crest" in field_name.lower():
                    self.orifice_crest_height_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.orifice_crest_height_FieldCbo, "crest"))
                if "coeff" in field_name.lower():
                    self.orifice_discharge_coeff_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.orifice_discharge_coeff_FieldCbo, "coeff"))
                if "flap" in field_name.lower():
                    self.orifice_flap_gate_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.orifice_flap_gate_FieldCbo, "flap"))
                if "time" in field_name.lower():
                    self.orifice_time_open_close_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.orifice_time_open_close_FieldCbo, "time"))
                if "shape" in field_name.lower():
                    self.orifice_shape_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.orifice_shape_FieldCbo, "shape"))
                if "height" in field_name.lower():
                    self.orifice_height_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.orifice_height_FieldCbo, "height"))
                if "width" in field_name.lower():
                    self.orifice_width_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.orifice_width_FieldCbo, "width"))
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_info("ERROR 240524.1214: orifices shapefile " + self.inlets_shapefile_cbo.currentText() + " not found in the layers panel!")  
            
    def restore_SD_shapefile_weir_field_names(self):
        # Weirs:
        sf_weirs_layer_name = self.gutils.execute(f"SELECT field FROM sd_fields WHERE name = 'sf_weirs_layer_name'").fetchone()
        layer = "" if sf_weirs_layer_name is None else sf_weirs_layer_name[0]
        if layer != "":
            if layer == self.weirs_shapefile_cbo.currentText():
                lyr = self.lyrs.get_layer_by_name(layer).layer()
                field_names = [field.name() for field in lyr.fields()]

                self.weir_name_FieldCbo.setField(self.restore_field_name("sf_weir_name", field_names))
                self.weir_from_inlet_FieldCbo.setField(self.restore_field_name("sf_weir_from_inlet", field_names))
                self.weir_to_outlet_FieldCbo.setField(self.restore_field_name("sf_weir_to_outlet", field_names))
                self.weir_type_FieldCbo.setField(self.restore_field_name("sf_weir_type", field_names))
                self.weir_crest_height_FieldCbo.setField(self.restore_field_name("sf_weir_crest_height", field_names))
                self.weir_discharge_coeff_FieldCbo.setField(self.restore_field_name("sf_weir_disch_coeff", field_names))
                self.weir_flap_gate_FieldCbo.setField(self.restore_field_name("sf_weir_flap_gate", field_names))
                self.weir_end_contrac_FieldCbo.setField(self.restore_field_name("sf_weir_end_contrac", field_names))
                self.weir_end_coeff_FieldCbo.setField( self.restore_field_name("sf_weir_end_coeff", field_names))
                self.weir_side_slope_FieldCbo.setField(self.restore_field_name("sf_weir_side_slope", field_names))
                self.weir_shape_FieldCbo.setField(self.restore_field_name("sf_weir_shape", field_names))
                self.weir_height_FieldCbo.setField( self.restore_field_name("sf_weir_height", field_names))
                self.weir_length_FieldCbo.setField(self.restore_field_name("sf_weir_length", field_names))
            else:
                self.assign_smart_weirs()
        elif layer == "":
            if self.weirs_shapefile_cbo.currentText() != "":
                self.assign_smart_weirs()
        else:
            self.clear_all_weirs_attributes()

    def assign_smart_weirs(self):
        try:
            lyr = self.lyrs.get_layer_by_name(self.weirs_shapefile_cbo.currentText()).layer()
            lyr_fields = lyr.fields()
            for index, field in enumerate(lyr_fields):
                field_name = field.name()
                if "name" in field_name.lower():
                    self.weir_name_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.weir_name_FieldCbo, "name"))
                if "inlet" in field_name.lower():
                    self.weir_from_inlet_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.weir_from_inlet_FieldCbo, "inlet"))
                if "outlet" in field_name.lower():
                    self.weir_to_outlet_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.weir_to_outlet_FieldCbo, "outlet"))
                if "type" in field_name.lower():
                    self.weir_type_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.weir_type_FieldCbo, "type"))
                if "crest" in field_name.lower():
                    self.weir_crest_height_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.weir_crest_height_FieldCbo, "crest"))
                if "coeff" in field_name.lower() and "disch" in field_name.lower():
                    self.weir_discharge_coeff_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.weir_discharge_coeff_FieldCbo, "coeff"))
                if "flap" in field_name.lower():
                    self.weir_flap_gate_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.weir_flap_gate_FieldCbo, "flap"))
                if "end" in field_name.lower() and "con" in field_name.lower():
                    self.weir_end_contrac_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.weir_end_contrac_FieldCbo, "end"))
                if "end" in field_name.lower() and "coeff" in field_name.lower():
                    self.weir_end_coeff_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.weir_end_coeff_FieldCbo, "end"))
                if "slope" in field_name.lower():
                    self.weir_side_slope_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.weir_side_slope_FieldCbo, "slope"))
                if "shape" in field_name.lower():
                    self.weir_shape_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.weir_shape_FieldCbo, "shape"))
                if "height" in field_name.lower():
                    self.weir_height_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.weir_height_FieldCbo, "height"))
                if "length" in field_name.lower():
                    self.weir_length_FieldCbo.setCurrentIndex(self.find_index_with_substring(self.weir_length_FieldCbo, "length"))    
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_info("ERROR 240524.1215: weirds shapefile " + self.inlets_shapefile_cbo.currentText() + " not found in the layers panel!")  

    def restore_field(self, field, field_names):
        field_name = self.gutils.execute(f"SELECT field FROM sd_fields WHERE name = '{field}'").fetchone()
        val = "" if field_name is None else field_name[0]
        if val != "":
            if val in field_names:
                # Get the index of the desired field name
                field_index = int(field_names.index(val))
                return field_index
            else:
                self.gutils.execute(f"INSERT INTO sd_fields (name, field) VALUES ('{field}', '')")
                return -1
        return -1

    def restore_field_name(self, field, field_names):
        field_name = self.gutils.execute(f"SELECT field FROM sd_fields WHERE name = '{field}'").fetchone()
        val = "" if field_name is None else field_name[0]
        return val

    def find_index_with_substring(self, combo_box, substring):
        for i in range(combo_box.count()):
            if substring in combo_box.itemText(i).lower():
                return i
        return -1