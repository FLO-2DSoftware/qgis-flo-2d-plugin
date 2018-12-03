# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.PyQt.QtWidgets import QDialogButtonBox 
from qgis.core import QgsFeature, QgsGeometry, QgsWkbTypes
from qgis.gui import QgsFieldComboBox
from qgis.PyQt.QtWidgets import QApplication, QComboBox

from .ui_utils import load_ui
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..flo2d_tools.schema2user_tools import remove_features

uiDialog, qtBaseClass = load_ui('stormdrain_shapefile')


class StormDrainShapefile(qtBaseClass, uiDialog):

    def __init__(self, con, iface, layers, tables):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.lyrs = layers
        self.tables = tables
        self.setupUi(self)
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.con = con
        self.gutils = GeoPackageUtils(con, iface)
        self.user_swmm_nodes_lyr = self.lyrs.data['user_swmm_nodes']['qlyr']
        self.user_swmm_conduits_lyr = self.lyrs.data['user_swmm_conduits']['qlyr']
        self.current_lyr = None
        self.saveSelected = None
        self.setup_layers_comboxes()
        self.SDSF_buttonBox.button(QDialogButtonBox.Save).setText("Assign Selected Inlets/Junctions, Outfalls, and Conduits")
        self.inlets_shapefile_cbo.currentIndexChanged.connect(self.populate_inlets_attributes)
        self.outfalls_shapefile_cbo.currentIndexChanged.connect(self.populate_outfalls_attributes)
        self.conduits_shapefile_cbo.currentIndexChanged.connect(self.populate_conduits_attributes)

        # Connections to clear inlets fields.
        self.clear_inlets_name_btn.clicked.connect(self.clear_inlets_name)
        self.clear_inlets_type_btn.clicked.connect(self.clear_inlets_type)
        self.clear_inlets_invert_elev_btn.clicked.connect(self.clear_inlets_invert_elevation)
        self.clear_inlets_max_depth_btn.clicked.connect(self.clear_inlets_max_depth)        
        self.clear_inlets_init_depth_btn.clicked.connect(self.clear_inlets_init_depth)              
        self.clear_inlets_surcharge_depth_btn.clicked.connect(self.clear_inlets_surcharge_dept) 
        self.clear_inlets_ponded_area_btn.clicked.connect(self.clear_inlets_ponded_area)   
        self.clear_inlets_length_perimeter_btn.clicked.connect(self.clear_inlets_length_perimeter)    
        self.clear_inlets_width_area_btn.clicked.connect(self.clear_inlets_width_area)    
        self.clear_inlets_height_sag_surch_btn.clicked.connect(self.clear_inlets_height_sag_surch)
        self.clear_inlets_weir_coeff_btn.clicked.connect(self.clear_inlets_weir_coeff)           
        self.clear_inlets_feature_btn.clicked.connect(self.clear_inlets_feature)           
        self.clear_inlets_curb_height_btn.clicked.connect(self.clear_inlets_curb_height)           
        self.clear_inlets_clogging_factor_btn.clicked.connect(self.clear_inlets_clogging_factor)
        self.clear_inlets_time_for_clogging_btn.clicked.connect(self.clear_inlets_time_for_clogging)                
        
        # Connections to clear outfalls fields.
        self.clear_outfall_name_btn.clicked.connect(self.clear_outfall_name)
        self.clear_outfall_invert_elevation_btn.clicked.connect(self.clear_outfall_invert_elevation)
        self.clear_outfall_flap_gate_btn.clicked.connect(self.clear_outfall_flap_gate)
        self.clear_outfall_allow_discharge_btn.clicked.connect(self.clear_outfall_allow_discharge)
        self.clear_outfall_type_btn.clicked.connect(self.clear_outfall_type)
        self.clear_outfall_water_depth_btn.clicked.connect(self.clear_outfall_water_depth)
        self.clear_outfall_tidal_curve_btn.clicked.connect(self.clear_outfall_tidal_curve)
        self.clear_outfall_time_series_btn.clicked.connect(self.clear_outfall_time_series)                        

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
        
        
        
        self.clear_all_inlets_btn.clicked.connect(self.clear_all_inlets_attributes)
        self.clear_all_outfalls_btn.clicked.connect(self.clear_all_outfalls_attributes)
        self.clear_all_conduits_btn.clicked.connect(self.clear_all_conduits_attributes)
        self.SDSF_buttonBox.accepted.connect(self.assign_components_from_shapefile)
        self.SDSF_buttonBox.rejected.connect(self.cancel_message)


    def setup_layers_comboxes(self):
        try:
            lyrs = self.lyrs.list_group_vlayers()
            for l in lyrs:
                if l.geometryType() == QgsWkbTypes.PointGeometry:
                    if l.featureCount() > 0:
                        self.inlets_shapefile_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
                        self.outfalls_shapefile_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())

                if l.geometryType() == QgsWkbTypes.LineGeometry:
                    if l.featureCount() > 0:
                        self.conduits_shapefile_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
                else:
                    pass

            self.populate_inlets_attributes(self.inlets_shapefile_cbo.currentIndex())
            self.populate_outfalls_attributes(self.outfalls_shapefile_cbo.currentIndex())
            self.populate_conduits_attributes(self.conduits_shapefile_cbo.currentIndex())
        except Exception as e:
            pass

    def populate_inlets_attributes(self, idx):
        uri = self.inlets_shapefile_cbo.itemData(idx)
        lyr_id = self.lyrs.layer_exists_in_group(uri)
        self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()

        for combo_inlets in self.inlets_fields_groupBox.findChildren(QComboBox):
            combo_inlets.clear()
            combo_inlets.setLayer(self.current_lyr)

        nFeatures = self.current_lyr.featureCount()
        self.inlets_fields_groupBox.setTitle("Inlets Fields Selection (from '" + self.inlets_shapefile_cbo.currentText() + "' layer with " + str(nFeatures) + " features (points))")

    def populate_outfalls_attributes(self, idx):
        uri = self.outfalls_shapefile_cbo.itemData(idx)
        lyr_id = self.lyrs.layer_exists_in_group(uri)
        self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()

        for combo_outfalls in self.outfalls_fields_groupBox.findChildren(QComboBox):
            combo_outfalls.clear()
            combo_outfalls.setLayer(self.current_lyr)

        nFeatures = self.current_lyr.featureCount()
        self.outfalls_fields_groupBox.setTitle("Outfalls Fields Selection (from '" + self.outfalls_shapefile_cbo.currentText() + "' layer with " + str(nFeatures) + " features (points))")

    def populate_conduits_attributes(self, idx):
        uri = self.conduits_shapefile_cbo.itemData(idx)
        lyr_id = self.lyrs.layer_exists_in_group(uri)
        self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()

        for combo_conduits in self.conduits_fields_groupBox.findChildren(QComboBox):
            combo_conduits.clear()
            combo_conduits.setLayer(self.current_lyr)

        nFeatures = self.current_lyr.featureCount()
        self.conduits_fields_groupBox.setTitle("Conduits Fields Selection (from '" + self.conduits_shapefile_cbo.currentText() + "' layer with " + str(nFeatures) + " features (lines))")

#     def clear_invert_elev(self):
#         self.inlets_invert_elevation_FieldCbo.setCurrentIndex(-1)

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
    def clear_inlets_ponded_area(self):              
            self.inlets_ponded_area_FieldCbo.setCurrentIndex(-1)             
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

    def clear_all_inlets_attributes(self):
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
        self.inlets_ponded_area_FieldCbo.setCurrentIndex(-1)
        self.inlets_length_perimeter_FieldCbo.setCurrentIndex(-1)
        self.inlets_width_area_FieldCbo.setCurrentIndex(-1)
        self.inlets_height_sag_surch_FieldCbo.setCurrentIndex(-1)

    def clear_all_outfalls_attributes(self):
        self.outfall_name_FieldCbo.setCurrentIndex(-1)
        self.outfall_invert_elevation_FieldCbo.setCurrentIndex(-1)
        self.outfall_flap_gate_FieldCbo.setCurrentIndex(-1)
        self.outfall_allow_discharge_FieldCbo.setCurrentIndex(-1)
        self.outfall_type_FieldCbo.setCurrentIndex(-1)
        self.outfall_water_depth_FieldCbo.setCurrentIndex(-1)
        self.outfall_tidal_curve_FieldCbo.setCurrentIndex(-1)
        self.outfall_time_series_FieldCbo.setCurrentIndex(-1)

    def clear_all_conduits_attributes(self):
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

    def assign_components_from_shapefile(self):
        self.uc.clear_bar_messages()

        if self.gutils.is_table_empty('user_model_boundary'):
            self.uc.bar_warn('There is no computational domain! Please digitize it before running tool.')
            return
        if self.gutils.is_table_empty('grid'):
            self.uc.bar_warn('There is no grid! Please create it before running tool.')
            return

        load_inlets = False
        load_outfalls = False
        load_conduits = False

        for combo_inlet in self.inlets_fields_groupBox.findChildren(QComboBox):
            if combo_inlet.currentIndex() != -1:
                load_inlets = True
                break

        for combo_outfall in self.outfalls_fields_groupBox.findChildren(QComboBox):
            if combo_outfall.currentIndex() != -1:
                load_outfalls = True
                break

        for combo_conduit in self.conduits_fields_groupBox.findChildren(QComboBox):
            if combo_conduit.currentIndex() != -1:
                load_conduits = True
                break

        if not load_inlets and not load_outfalls and not load_conduits:
            self.uc.bar_warn("No data was selected!")

        else:
            # Load inlets from shapefile:
            if load_inlets:
                try:

                    fields = self.user_swmm_nodes_lyr.fields()
                    new_feats = []
                    
                    inlets_shapefile = self.inlets_shapefile_cbo.currentText()
                    group =  self.lyrs.group
#                     lyr = self.lyrs.get_layer_by_name(inlets_shapefile, group).layer() 
                    lyr = self.lyrs.get_layer_by_name(inlets_shapefile, group=self.lyrs.group).layer()
                                                
                    inlets_shapefile_fts = lyr.getFeatures()

                    for f in inlets_shapefile_fts:
                        grid = 0
                        sd_type = "I"
                        name = f[self.inlets_name_FieldCbo.currentText()] if self.inlets_name_FieldCbo.currentText() != "" else ""
                        intype = f[self.inlets_type_FieldCbo.currentText()] if self.inlets_type_FieldCbo.currentText() != "" else 1
                        junction_invert_elev = f[self.inlets_invert_elevation_FieldCbo.currentText()] if self.inlets_invert_elevation_FieldCbo.currentText() != "" else 0
                        max_depth = f[self.inlets_max_depth_FieldCbo.currentText()] if self.inlets_max_depth_FieldCbo.currentText() != "" else 0
                        init_depth = f[self.inlets_init_depth_FieldCbo.currentText()] if self.inlets_init_depth_FieldCbo.currentText() != "" else 0
                        surcharge_depth = f[self.inlets_surcharge_depth_FieldCbo.currentText()] if self.inlets_surcharge_depth_FieldCbo.currentText() != "" else 0
                        ponded_area = f[self.inlets_ponded_area_FieldCbo.currentText()] if self.inlets_ponded_area_FieldCbo.currentText() != "" else 0
                        swmm_length = f[self.inlets_length_perimeter_FieldCbo.currentText()] if self.inlets_length_perimeter_FieldCbo.currentText() != "" else 0
                        swmm_width = f[self.inlets_width_area_FieldCbo.currentText()] if self.inlets_width_area_FieldCbo.currentText() != "" else 0
                        swmm_height = f[self.inlets_height_sag_surch_FieldCbo.currentText()] if self.inlets_height_sag_surch_FieldCbo.currentText() != "" else 0
                        swmm_coeff = f[self.inlets_weir_coeff_FieldCbo.currentText()] if self.inlets_weir_coeff_FieldCbo.currentText() != "" else 0
                        swmm_feature = f[self.inlets_feature_FieldCbo.currentText()] if self.inlets_feature_FieldCbo.currentText() != "" else 0
                        curbheight = f[self.inlets_curb_height_FieldCbo.currentText()] if self.inlets_curb_height_FieldCbo.currentText() != "" else 0
                        swmm_clogging_factor = f[self.inlets_clogging_factor_FieldCbo.currentText()] if self.inlets_clogging_factor_FieldCbo.currentText() != "" else 0
                        swmm_time_for_clogging = f[self.inlets_time_for_clogging_FieldCbo.currentText()] if self.inlets_time_for_clogging_FieldCbo.currentText() != "" else 0

                        feat = QgsFeature()
                        feat.setFields(fields)

                        geom = f.geometry()
                        if geom is None:
                            QApplication.restoreOverrideCursor()
                            self.uc.show_warn("Error processing geometry of inlet/junction '" + name + "' !")
                            continue

                        point = geom.asPoint()
                        if point is None:
                            QApplication.restoreOverrideCursor()
                            self.uc.show_warn("Inlet/junction  " + name + "  is faulty!")
                            continue
                        
                        cell = self.gutils.grid_on_point(point.x(), point.y())
                        if cell is None:
                            QApplication.restoreOverrideCursor()
                            self.uc.show_warn("Inlet/junction  " + name + "  is outside the computational domain!")
                            continue    
                                            
                        new_geom = QgsGeometry.fromPointXY(point)
                        feat.setGeometry(new_geom)

                        feat.setAttribute('grid', cell)
                        feat.setAttribute('sd_type', 'I')
                        feat.setAttribute('name', name)
                        feat.setAttribute('intype', intype)
                        feat.setAttribute('junction_invert_elev', junction_invert_elev)
                        feat.setAttribute('max_depth', max_depth)
                        feat.setAttribute('init_depth', init_depth)
                        feat.setAttribute('surcharge_depth',  surcharge_depth)
                        feat.setAttribute('ponded_area',ponded_area)
                        feat.setAttribute('outfall_invert_elev', 0)
                        feat.setAttribute('outfall_type', 'Normal')
                        feat.setAttribute('tidal_curve', '...')
                        feat.setAttribute('time_series', '...')
                        feat.setAttribute('flapgate', 'False')
                        feat.setAttribute('swmm_length', swmm_length)
                        feat.setAttribute('swmm_width', swmm_width)
                        feat.setAttribute('swmm_height', swmm_height)
                        feat.setAttribute('swmm_coeff', swmm_coeff)
                        feat.setAttribute('swmm_feature', swmm_feature)
                        feat.setAttribute('curbheight', curbheight)
                        feat.setAttribute('swmm_clogging_factor', swmm_clogging_factor)
                        feat.setAttribute('swmm_time_for_clogging', swmm_time_for_clogging)
                        feat.setAttribute('swmm_allow_discharge', 'True')
                        feat.setAttribute('water_depth', 0)
                        feat.setAttribute('rt_fid', 0)
                        feat.setAttribute('outf_flo', 0)
                        feat.setAttribute('invert_elev_inp', 0)
                        feat.setAttribute('max_depth_inp', 0)
                        feat.setAttribute('rim_elev_inp', 0)
                        feat.setAttribute('rim_elev', 0)
                        feat.setAttribute('ge_elev', 0)
                        feat.setAttribute('difference', 0)

                        new_feats.append(feat)

                    if not self.inlets_append_chbox.isChecked():
                        remove_features(self.user_swmm_nodes_lyr)

                    self.user_swmm_nodes_lyr.startEditing()
                    self.user_swmm_nodes_lyr.addFeatures(new_feats)
                    self.user_swmm_nodes_lyr.commitChanges()
                    self.user_swmm_nodes_lyr.updateExtents()
                    self.user_swmm_nodes_lyr.triggerRepaint()
                    self.user_swmm_nodes_lyr.removeSelection()

                    QApplication.restoreOverrideCursor()

                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 070618.0451: creation of Storm Drain Modes (Inlets) layer failed!"
                               +'\n__________________________________________________', e)

            # Load outfalls from shapefile:
            if load_outfalls:
                try:

                    fields = self.user_swmm_nodes_lyr.fields()
                    new_feats = []

                    outfalls_shapefile = self.outfalls_shapefile_cbo.currentText()
                    lyr = self.lyrs.get_layer_by_name(outfalls_shapefile, self.lyrs.group).layer()
                    outfalls_shapefile_fts = lyr.getFeatures()

                    for f in outfalls_shapefile_fts:
                        grid = 0
                        sd_type = "O"
                        name = f[self.outfall_name_FieldCbo.currentText()] if self.outfall_name_FieldCbo.currentText() != "" else ""
                        intype = 1
                        outfall_invert_elev = f[self.outfall_invert_elevation_FieldCbo.currentText()] if self.outfall_invert_elevation_FieldCbo.currentText() != "" else ""
                        flapgate = f[self.outfall_flap_gate_FieldCbo.currentText()] if self.outfall_flap_gate_FieldCbo.currentText() != "" else ""
                        swmm_allow_discharge = f[self.outfall_allow_discharge_FieldCbo.currentText()] if self.outfall_allow_discharge_FieldCbo.currentText() != "" else ""
                        outfall_type = f[self.outfall_type_FieldCbo.currentText()] if self.outfall_type_FieldCbo.currentText() != "" else ""

                        # water_depth = f[self.outfall_water_depth_FieldCbo.currentText()] if self.outfall_water_depth_FieldCbo.currentText() != "" else ""
                        water_depth = self.outfall_water_depth_FieldCbo.currentText()
                        water_depth = f[water_depth] if water_depth != "" and water_depth is not None else ""

                        feat = QgsFeature()
                        feat.setFields(fields)

                        geom = f.geometry()
                        if geom is None:
                            QApplication.restoreOverrideCursor()
                            self.uc.show_warn("Error processing geometry of outfall'" + name + "' !")
                            continue
                        
                        point = geom.asPoint()
                        if point is None:
                            QApplication.restoreOverrideCursor()
                            self.uc.show_warn("Outfall  " + name + "  is faulty!")
                            continue
                        
                        cell = self.gutils.grid_on_point(point.x(), point.y())
                        if cell is None:
                            QApplication.restoreOverrideCursor()
                            self.uc.show_warn("Outfall  " + name + "  is outside the computationsl domain!")
                            continue                        
                        
                        new_geom = QgsGeometry.fromPointXY(point)
                        feat.setGeometry(new_geom)

                        feat.setAttribute('grid', cell)
                        feat.setAttribute('sd_type', 'O')
                        feat.setAttribute('name', name)
                        feat.setAttribute('intype', 1)
                        feat.setAttribute('junction_invert_elev', 0)
                        feat.setAttribute('max_depth', 0)
                        feat.setAttribute('init_depth', 0)
                        feat.setAttribute('surcharge_depth',  0)
                        feat.setAttribute('ponded_area',0)
                        feat.setAttribute('outfall_invert_elev', outfall_invert_elev)
                        feat.setAttribute('outfall_type', outfall_type)
                        feat.setAttribute('tidal_curve', '...')
                        feat.setAttribute('time_series', '...')
                        feat.setAttribute('flapgate', flapgate)
                        feat.setAttribute('swmm_length', 0)
                        feat.setAttribute('swmm_width', 0)
                        feat.setAttribute('swmm_height', 0)
                        feat.setAttribute('swmm_coeff', 0)
                        feat.setAttribute('swmm_feature', 0)
                        feat.setAttribute('curbheight', 0)
                        feat.setAttribute('swmm_clogging_factor', 0)
                        feat.setAttribute('swmm_time_for_clogging', 0)
                        feat.setAttribute('swmm_allow_discharge', swmm_allow_discharge)
                        feat.setAttribute('water_depth', 0)
                        feat.setAttribute('rt_fid', 0)
                        feat.setAttribute('outf_flo', 0)
                        feat.setAttribute('invert_elev_inp', 0)
                        feat.setAttribute('max_depth_inp', 0)
                        feat.setAttribute('rim_elev_inp', 0)
                        feat.setAttribute('rim_elev', 0)
                        feat.setAttribute('ge_elev', 0)
                        feat.setAttribute('difference', 0)

                        new_feats.append(feat)

                    if not self.inlets_append_chbox.isChecked() and not load_inlets:
                        remove_features(self.user_swmm_nodes_lyr)
                    # remove_features(self.user_swmm_nodes_lyr)
                    self.user_swmm_nodes_lyr.startEditing()
                    self.user_swmm_nodes_lyr.addFeatures(new_feats)
                    self.user_swmm_nodes_lyr.commitChanges()
                    self.user_swmm_nodes_lyr.updateExtents()
                    self.user_swmm_nodes_lyr.triggerRepaint()
                    self.user_swmm_nodes_lyr.removeSelection()

                    QApplication.restoreOverrideCursor()

                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 070618.0454: creation of Storm Drain Modes (Outfalls) layer failed!", e)

            if load_conduits:
                try:
                    fields = self.user_swmm_conduits_lyr.fields()
                    new_feats = []

                    conduits_shapefile = self.conduits_shapefile_cbo.currentText()
                    lyr = self.lyrs.get_layer_by_name(conduits_shapefile, self.lyrs.group).layer()
                    conduits_shapefile_fts = lyr.getFeatures()
                    no_in_out = 0
                    
                    for f in conduits_shapefile_fts:

                        conduit_name = f[self.conduit_name_FieldCbo.currentText()] if self.conduit_name_FieldCbo.currentText() != "" else ""
                        conduit_inlet = f[self.conduit_from_inlet_FieldCbo.currentText()] if self.conduit_from_inlet_FieldCbo.currentText() != "" else "?"
                        conduit_outlet = f[self.conduit_to_outlet_FieldCbo.currentText()] if self.conduit_to_outlet_FieldCbo.currentText() != "" else "?"
                        conduit_inlet_offset = f[self.conduit_inlet_offset_FieldCbo.currentText()] if self.conduit_inlet_offset_FieldCbo.currentText() != "" else 0
                        conduit_outlet_offset = f[self.conduit_outlet_offset_FieldCbo.currentText()] if self.conduit_outlet_offset_FieldCbo.currentText() != "" else 0
                        conduit_shape = f[self.conduit_shape_FieldCbo.currentText()] if self.conduit_shape_FieldCbo.currentText() != "" else 0
                        conduit_max_depth = f[self.conduit_max_depth_FieldCbo.currentText()] if self.conduit_max_depth_FieldCbo.currentText() != "" else 0
                        conduit_geom2 = f[self.conduit_geom2_FieldCbo.currentText()] if self.conduit_geom2_FieldCbo.currentText() != "" else 0
                        conduit_geom3 = f[self.conduit_geom3_FieldCbo.currentText()] if self.conduit_geom3_FieldCbo.currentText() != "" else 0
                        conduit_geom4 = f[self.conduit_geom4_FieldCbo.currentText()] if self.conduit_geom4_FieldCbo.currentText() != "" else 0
                        conduit_barrels = f[self.conduit_barrels_FieldCbo.currentText()] if self.conduit_barrels_FieldCbo.currentText() != "" else 0
                        conduit_length  = f[self.conduit_length_FieldCbo.currentText()] if self.conduit_length_FieldCbo.currentText() != "" else 0
                        conduit_manning  = f[self.conduit_manning_FieldCbo.currentText()] if self.conduit_manning_FieldCbo.currentText() != "" else 0
                        conduit_init_flow = f[self.conduit_initial_flow_FieldCbo.currentText()] if self.conduit_initial_flow_FieldCbo.currentText() != "" else 0
                        conduit_max_flow = f[self.conduit_max_flow_FieldCbo.currentText()] if self.conduit_max_flow_FieldCbo.currentText() != "" else 0
                        conduit_entry_loss = f[self.conduit_entry_loss_FieldCbo.currentText()] if self.conduit_entry_loss_FieldCbo.currentText() != "" else 0
                        conduit_exit_loss = f[self.conduit_exit_loss_FieldCbo.currentText()] if self.conduit_exit_loss_FieldCbo.currentText() != "" else 0
                        conduit_loss_average = f[self.conduit_average_loss_FieldCbo.currentText()] if self.conduit_average_loss_FieldCbo.currentText() != "" else 0
                        conduits_flap_gate = f[self.conduit_flap_gate_FieldCbo.currentText()] if self.conduit_flap_gate_FieldCbo.currentText() != "" else 0

                        # xsections_shape  = f[self.conduits_manning_FieldCbo.currentText()] if self.conduits_manning_FieldCbo.currentText() != "" else 0
                        # xsections_barrels = f[self.conduits_initial_flow_FieldCbo.currentText()] if self.conduits_initial_flow_FieldCbo.currentText() != "" else 0
                        # xsections_max_depth = f[self.conduits_max_flow_FieldCbo.currentText()] if self.conduits_max_flow_FieldCbo.currentText() != "" else 0
                        # xsections_geom2 = f[self.conduits_inlet_losses_FieldCbo.currentText()] if self.conduits_inlet_losses_FieldCbo.currentText() != "" else 0
                        # xsections_geom2 = f[self.conduits_outlet_losses_FieldCbo.currentText()] if self.conduits_outlet_losses_FieldCbo.currentText() != "" else 0
                        # xsections_geom2 = f[self.conduits_average_losses_FieldCbo.currentText()] if self.conduits_average_losses_FieldCbo.currentText() != "" else 0

                        if conduit_inlet == "?" or conduit_outlet == "?":
                            no_in_out += 1
                            
                        feat = QgsFeature()
                        feat.setFields(fields)

                        geom = f.geometry()
                        if geom is None:
                            QApplication.restoreOverrideCursor()
                            self.uc.show_warn("Error processing geometry of conduit '" + conduit_name +"' !")
                            continue
                        
                        line = geom.asPolyline()
                        if line is None:
                            QApplication.restoreOverrideCursor()
                            self.uc.show_warn("Conduit " + name + " is faulty!")
                            continue
                                                
                        new_geom = QgsGeometry.fromPolylineXY(line)
                        feat.setGeometry(new_geom)

                        feat.setAttribute('conduit_name', conduit_name)
                        feat.setAttribute('conduit_inlet',conduit_inlet )
                        feat.setAttribute('conduit_outlet',conduit_outlet )
                        feat.setAttribute('conduit_inlet_offset', conduit_inlet_offset)
                        feat.setAttribute('conduit_outlet_offset', conduit_outlet_offset)
                        feat.setAttribute('conduit_length', conduit_length)
                        feat.setAttribute('conduit_manning', conduit_manning)
                        feat.setAttribute('conduit_init_flow', conduit_init_flow)
                        feat.setAttribute('conduit_max_flow', conduit_max_flow)
                        feat.setAttribute('losses_inlet', conduit_entry_loss)
                        feat.setAttribute('losses_outlet', conduit_exit_loss)
                        feat.setAttribute('losses_average', conduit_loss_average)
                        feat.setAttribute('losses_flapgate', conduits_flap_gate)
                        feat.setAttribute('xsections_shape', 'CIRCULAR')
                        feat.setAttribute('xsections_barrels', conduit_barrels)
                        feat.setAttribute('xsections_max_depth', conduit_max_depth)
                        feat.setAttribute('xsections_geom2', conduit_geom2)
                        feat.setAttribute('xsections_geom3', conduit_geom3)
                        feat.setAttribute('xsections_geom4', conduit_geom4)

                        new_feats.append(feat)

                    if not self.conduits_append_chbox.isChecked():
                        remove_features(self.user_swmm_conduits_lyr)

                    self.user_swmm_conduits_lyr.startEditing()
                    self.user_swmm_conduits_lyr.addFeatures(new_feats)
                    self.user_swmm_conduits_lyr.commitChanges()
                    self.user_swmm_conduits_lyr.updateExtents()
                    self.user_swmm_conduits_lyr.triggerRepaint()
                    self.user_swmm_conduits_lyr.removeSelection()

                    QApplication.restoreOverrideCursor()

                    if no_in_out != 0:
                        self.uc.show_warn(str(no_in_out) + " conduits have no inlet and/or outlet!\n" +
                                                           "The value '?' was assigned to them. It will cause errors during their processing.\n" +
                                                           "Did you select the 'From Inlet' and 'To Oulet' fields in the shapefile?" )                     
                        
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    self.uc.show_error("ERROR 070618.0500: creation of Storm Drain Modes (Conduits) layer failed!", e)

            if (load_inlets or load_outfalls) and load_conduits:
                self.uc.show_info("Importing SWMM input data finished!\n\n" +
                                  "The 'Storm Drain Nodes' and 'Storm Drain Conduits' layers were created in the 'User Layers' group.\n\n"
                                  "Use the 'Inlets', 'Outlets', and 'Conduits' buttons in the Storm Drain Editor widget to see/edit their attributes.\n\n"
                                  "NOTE: the 'Schematize Storm Drain Components' button will update the 'Storm Drain' layer group.")
            elif not (load_inlets or load_outfalls) and load_conduits:
                self.uc.show_info("Importing SWMM input data finished!\n\n" +
                                  "The 'Storm Drain Conduits' layer was created in the 'User Layers' group.\n\n"
                                  "Use the 'Inlets', 'Outlets', and 'Conduits' buttons in the Storm Drain Editor widget to see/edit their attributes.\n\n"
                                  "NOTE: the 'Schematize Storm Drain Components' button will update the 'Storm Drain' layer group.")   
            elif (load_inlets or load_outfalls) and not load_conduits:
                self.uc.show_info("Importing SWMM input data finished!\n\n" +
                                  "The 'Storm Drain Nodes' layer was created in the 'User Layers' group.\n\n"
                                  "Use the 'Inlets', 'Outlets', and 'Conduits' buttons in the Storm Drain Editor widget to see/edit their attributes.\n\n"
                                  "NOTE: the 'Schematize Storm Drain Components' button will update the 'Storm Drain' layer group.")
    def cancel_message(self):
        self.uc.bar_info("No data was selected!")
