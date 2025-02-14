# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import os
import time
from collections import OrderedDict
from os.path import normpath

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QProgressDialog
from qgis.core import (
    QgsDefaultValue,
    QgsEditorWidgetSetup,
    QgsFeatureRequest,
    QgsLayerTreeGroup,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsRubberBand
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QApplication

from .errors import Flo2dError, Flo2dLayerInvalid, Flo2dLayerNotFound, Flo2dNotString
from .misc.invisible_lyrs_grps import InvisibleLayersAndGroups
from .user_communication import UserCommunication
from .utils import get_file_path, is_number


class Layers(object):
    """
    Class for managing project layers: load, add to layers tree.
    """

    def __init__(self, iface):
        self.iface = iface
        if iface is not None:
            self.canvas = iface.mapCanvas()
            self.ilg = InvisibleLayersAndGroups(self.iface)
        else:
            self.canvas = None
        self.root = QgsProject.instance().layerTreeRoot()
        self.rb = None
        self.uc = UserCommunication(iface, "FLO-2D")
        self.gutils = None
        self.lyrs_to_repaint = []
        self.data = OrderedDict(
            [
                (
                    "user_model_boundary",
                    {
                        "name": "Computational Domain",
                        "sgroup": "User Layers",
                        "styles": ["model_boundary.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_bc_points",
                    {
                        "name": "Boundary Condition Points",
                        "sgroup": "User Layers",
                        "ssgroup": "Boundary Conditions",
                        "styles": ["user_bc_points.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_bc_lines",
                    {
                        "name": "Boundary Condition Lines",
                        "sgroup": "User Layers",
                        "ssgroup": "Boundary Conditions",
                        "styles": ["user_bc_lines.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_bc_polygons",
                    {
                        "name": "Boundary Condition Polygons",
                        "sgroup": "User Layers",
                        "ssgroup": "Boundary Conditions",
                        "styles": ["user_bc_polygons.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_left_bank",
                    {
                        "name": "Left Bank Lines",
                        "sgroup": "User Layers",
                        "ssgroup": "Channels",
                        "styles": ["user_lbank.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["chan"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_right_bank",
                    {
                        "name": "Right Bank Lines",
                        "sgroup": "User Layers",
                        "ssgroup": "Channels",
                        "styles": ["user_rbank.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["chan"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_xsections",
                    {
                        "name": "Cross Sections",
                        "sgroup": "User Layers",
                        "ssgroup": "Channels",
                        "styles": ["user_xs.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["chan"],
                        "readonly": True,
                        "attrs_defaults": {"type": "'R'"},
                        "advanced": False
                    },
                ),
                (
                    "user_noexchange_chan_areas",
                    {
                        "name": "No-Exchange Channel Areas",
                        "sgroup": "User Layers",
                        "ssgroup": "Areas",
                        "styles": ["user_noexchange_chan_areas.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_swmm_conduits",
                    {
                        "name": "Storm Drain Conduits",
                        "sgroup": "User Layers",
                        "ssgroup": "Storm Drain",
                        "styles": ["user_swmm_conduits.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_swmm_pumps",
                    {
                        "name": "Storm Drain Pumps",
                        "sgroup": "User Layers",
                        "ssgroup": "Storm Drain",
                        "styles": ["user_swmm_pumps.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_swmm_orifices",
                    {
                        "name": "Storm Drain Orifices",
                        "sgroup": "User Layers",
                        "ssgroup": "Storm Drain",
                        "styles": ["user_swmm_orifices.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_swmm_weirs",
                    {
                        "name": "Storm Drain Weirs",
                        "sgroup": "User Layers",
                        "ssgroup": "Storm Drain",
                        "styles": ["user_swmm_weirs.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_swmm_inlets_junctions",
                    {
                        "name": "Storm Drain Inlets/Junctions",
                        "sgroup": "User Layers",
                        "ssgroup": "Storm Drain",
                        "styles": ["user_swmm_inlets_junctions.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_swmm_outlets",
                    {
                        "name": "Storm Drain Outfalls",
                        "sgroup": "User Layers",
                        "ssgroup": "Storm Drain",
                        "styles": ["user_swmm_outlets.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_swmm_storage_units",
                    {
                        "name": "Storm Drain Storage Units",
                        "sgroup": "User Layers",
                        "ssgroup": "Storm Drain",
                        "styles": ["user_swmm_storage_units.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),                
                (
                    "buildings_areas",
                    {
                        "name": "Building Areas",
                        "sgroup": "User Layers",
                        "ssgroup": "Areas",
                        "styles": ["user_buildings.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "gutter_areas",
                    {
                        "name": "Gutter Areas",
                        "sgroup": "User Layers",
                        "ssgroup": "Gutters",
                        "styles": ["user_spatial_gutter.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "spatialshallow",
                    {
                        "name": "Shallow-n Areas",
                        "sgroup": "User Layers",
                        "ssgroup": "Areas",
                        "styles": ["user_spatial_shallow_n.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "fpfroude",
                    {
                        "name": "Froude Areas",
                        "sgroup": "User Layers",
                        "ssgroup": "Areas",
                        "styles": ["user_spatial_froude.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "tolspatial",
                    {
                        "name": "Tolerance Areas",
                        "sgroup": "User Layers",
                        "ssgroup": "Areas",
                        "styles": ["tolspatial.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_blocked_areas",
                    {
                        "name": "Blocked Areas",
                        "sgroup": "User Layers",
                        "ssgroup": "Areas",
                        "styles": ["blocked_areas.qml"],
                        "attrs_edit_widgets": {
                            "collapse": {
                                "name": "CheckBox",
                                "config": {"CheckedState": 1, "UncheckedState": 0},
                            },
                            "calc_arf": {
                                "name": "CheckBox",
                                "config": {"CheckedState": 1, "UncheckedState": 0},
                            },
                            "calc_wrf": {
                                "name": "CheckBox",
                                "config": {"CheckedState": 1, "UncheckedState": 0},
                            },
                        },
                        "module": ["redfac"],
                        "readonly": False,
                        "attrs_defaults": {"calc_arf": "1", "calc_wrf": "1"},  #
                        "advanced": False
                    },
                ),
                (
                    "user_roughness",
                    {
                        "name": "Roughness",
                        "sgroup": "User Layers",
                        "ssgroup": "Areas",
                        "styles": ["user_roughness.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "mult_areas",
                    {
                        "name": "Multiple Channel Areas",
                        "sgroup": "User Layers",
                        "ssgroup": "Multiple Channels",
                        "styles": ["mult_areas.qml"],
                        "attrs_edit_widgets": {},
                        "visible": True,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "mult_lines",
                    {
                        "name": "Multiple Channel Lines",
                        "sgroup": "User Layers",
                        "ssgroup": "Multiple Channels",
                        "styles": ["mult_lines.qml"],
                        "attrs_edit_widgets": {},
                        "visible": True,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "simple_mult_lines",
                    {
                        "name": "Simple Mult. Channel Lines",
                        "sgroup": "User Layers",
                        "ssgroup": "Multiple Channels",
                        "styles": ["mult_lines.qml"],
                        "attrs_edit_widgets": {},
                        "visible": True,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "user_fpxsec",
                    {
                        "name": "Floodplain Cross Sections",
                        "sgroup": "User Layers",
                        "ssgroup": "Floodplain",
                        "styles": ["user_fpxsec.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["chan"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_struct",
                    {
                        "name": "Structure Lines",
                        "sgroup": "User Layers",
                        "ssgroup": "Hydraulic Structures",
                        "styles": ["user_struct.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["structures"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_streets",
                    {
                        "name": "Street Lines",
                        "sgroup": "User Layers",
                        "ssgroup": "Streets",
                        "styles": ["user_line.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["streets"],
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "user_levee_lines",
                    {
                        "name": "Levee Lines",
                        "sgroup": "User Layers",
                        "ssgroup": "Levees",
                        "styles": ["user_levee_lines.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["levees"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_elevation_points",
                    {
                        "name": "Elevation Points",
                        "sgroup": "User Layers",
                        "ssgroup": "Elevations",
                        "styles": ["user_elevation_points.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_elevation_polygons",
                    {
                        "name": "Elevation Polygons",
                        "sgroup": "User Layers",
                        "ssgroup": "Elevations",
                        "styles": ["user_elevation_polygons.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_reservoirs",
                    {
                        "name": "Reservoirs",
                        "sgroup": "User Layers",
                        "ssgroup": "Boundary Conditions",
                        "styles": ["user_reservoirs.qml"],
                        "attrs_edit_widgets": {
                            "use_n_value": {
                                "name": "CheckBox",
                                "config": {"CheckedState": 1, "UncheckedState": 0},
                            }
                        },
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_tailing_reservoirs",
                    {
                        "name": "Tailing Reservoirs",
                        "sgroup": "User Layers",
                        "ssgroup": "Boundary Conditions",
                        "styles": ["user_tailing_reservoirs.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_tailings",
                    {
                        "name": "Tailing Stacks",
                        "sgroup": "User Layers",
                        "ssgroup": "Boundary Conditions",
                        "styles": ["user_tailings.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_infiltration",
                    {
                        "name": "Infiltration Areas",
                        "sgroup": "User Layers",
                        "ssgroup": "Infiltration",
                        "styles": ["user_infiltration.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "user_effective_impervious_area",
                    {
                        "name": "Effective Impervious Areas",
                        "sgroup": "User Layers",
                        "ssgroup": "Infiltration",
                        "styles": ["user_effective_impervious_area.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["all"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "gutter_lines",
                    {
                        "name": "Gutter Lines",
                        "sgroup": "User Layers",
                        "ssgroup": "Gutters",
                        "styles": ["gutter_lines4.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "user_md_connect_lines",
                    {
                        "name": "Connectivity Lines",
                        "sgroup": "User Layers",
                        "ssgroup": "Multiple Domains",
                        "styles": ["connect_lines.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                "mult_domains",
                {
                    "name": "Domains",
                    "sgroup": "User Layers",
                    "ssgroup": "Multiple Domains",
                    "styles": ["domains.qml"],
                    "attrs_edit_widgets": {},
                    "readonly": False,
                    "advanced": False
                    },
                ),
                # Schematic layers:
                (
                    "grid",
                    {
                        "name": "Grid",
                        "sgroup": "Schematic Layers",
                        "styles": ["grid.qml", "grid_nodata.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": False
                    },
                ),
                (
                    "chan",
                    {
                        "name": "Channel Segments (Left Banks)",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Channels",
                        "styles": ["chan.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["chan"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "chan_elems",
                    {
                        "name": "Channel Cross Sections",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Channels",
                        "styles": ["chan_elems.qml"],
                        "attrs_edit_widgets": {},
                        "visible": True,
                        "module": ["chan"],
                        "readonly": True,
                        "advanced": False
                    },
                ),
                (
                    "rbank",
                    {
                        "name": "Right Banks",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Channels",
                        "styles": ["rbank.qml"],
                        "attrs_edit_widgets": {},
                        "visible": True,
                        "module": ["chan"],
                        "readonly": True,
                        "advanced": False
                    },
                ),
                (
                    "chan_confluences",
                    {
                        "name": "Channel Confluences",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Channels",
                        "styles": ["chan_confluences.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": False
                    },
                ),
                (
                    "fpxsec",
                    {
                        "name": "Floodplain Cross Sections",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Floodplain",
                        "styles": ["fpxsec.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": False
                    },
                ),
                (
                    "fpxsec_cells",
                    {
                        "name": "Floodplain Cross Sections Cells",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Floodplain",
                        "styles": ["fpxsec_cells.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": False
                    },
                ),
                (
                    "breach",
                    {
                        "name": "Breach Locations",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Levees",
                        "styles": ["breach.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["breach"],
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "levee_data",
                    {
                        "name": "Levees",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Levees",
                        "styles": ["levee.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["levees"],
                        "readonly": True,
                        "advanced": False
                    },
                ),
                (
                    "struct",
                    {
                        "name": "Structures",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Hydraulic Structures",
                        "styles": ["struc.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["struct"],
                        "readonly": True,
                        "advanced": False
                    },
                ),
                (
                    "street_seg",
                    {
                        "name": "Streets",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Streets",
                        "styles": ["street.qml"],
                        "attrs_edit_widgets": {},
                        "module": ["struct"],
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "all_schem_bc",
                    {
                        "name": "BC Cells",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Boundary Conditions",
                        "styles": ["all_schem_bc.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": False
                    },
                ),
                (
                    "blocked_cells",
                    {
                        "name": "ARF_WRF",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Areas",
                        "styles": ["arfwrf.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": False
                    },
                ),
                (
                    "reservoirs",
                    {
                        "name": "Reservoirs",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Boundary Conditions",
                        "styles": ["reservoirs.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "tailing_reservoirs",
                    {
                        "name": "Tailing Reservoirs",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Boundary Conditions",
                        "styles": ["tailing_reservoirs.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "gutter_cells",
                    {
                        "name": "Gutter Cells",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Gutters",
                        "styles": ["gutter_cells.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": True
                    },
                ),
                # Storm Drain layers:
                (
                    "swmmflo",
                    {
                        "name": "SD Inlets",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Storm Drain",
                        "styles": ["swmmflo.qml"],
                        "attrs_edit_widgets": {},
                        "visible": True,
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "swmmoutf",
                    {
                        "name": "SD Outfalls",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Storm Drain",
                        "styles": ["swmmoutf.qml"],
                        "attrs_edit_widgets": {},
                        "visible": True,
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "swmmflort",
                    {
                        "name": "Rating Tables",
                        "sgroup": "Storm Drain Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "swmmflort_data",
                    {
                        "name": "Rating Tables Data",
                        "sgroup": "Storm Drain Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "swmmflo_culvert",
                    {
                        "name": "Culvert Equations",
                        "sgroup": "Storm Drain Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "swmm_control",
                    {
                        "name": "Storm Drain Control",
                        "sgroup": "Storm Drain Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "swmm_inflows",
                    {
                        "name": "Storm Drain Inflows",
                        "sgroup": "Storm Drain Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "swmm_inflow_patterns",
                    {
                        "name": "Storm Drain Inflow Patterns",
                        "sgroup": "Storm Drain Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "swmm_time_series",
                    {
                        "name": "Storm Drain Time Series",
                        "sgroup": "Storm Drain Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "swmm_time_series_data",
                    {
                        "name": "Storm Drain Time Series Data",
                        "sgroup": "Storm Drain Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "swmm_tidal_curve",
                    {
                        "name": "Storm Drain Tidal Curve",
                        "sgroup": "Storm Drain Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "swmm_tidal_curve_data",
                    {
                        "name": "Storm Drain Tidal Curve Data",
                        "sgroup": "Storm Drain Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "swmm_pumps_curve_data",
                    {
                        "name": "Storm Drain Pumps Curve Data",
                        "sgroup": "Storm Drain Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "swmm_other_curves",
                    {
                        "name": "Storm Drain Other Curves",
                        "sgroup": "Storm Drain Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                # Multiple Domains Layers
                (
                    "schema_md_connect_cells",
                    {
                        "name": "Connectivity Cells",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Multiple Domains",
                        "styles": ["connect_cells.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": False
                    },
                ),
                # Infiltration Layers
                (
                    "infil",
                    {
                        "name": "Infil Globals",
                        "sgroup": "Infiltration Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "infil_cells_green",
                    {
                        "name": "Cells Green Ampt",
                        "sgroup": "Infiltration Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "infil_cells_scs",
                    {
                        "name": "Cells SCS",
                        "sgroup": "Infiltration Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "infil_cells_horton",
                    {
                        "name": "Cells Horton",
                        "sgroup": "Infiltration Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "infil_chan_elems",
                    {
                        "name": "Channel elements",
                        "sgroup": "Infiltration Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": True
                    },
                ),
                # Tables:
                (
                    "cont",
                    {
                        "name": "Control",
                        "sgroup": "Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "tolspatial_cells",
                    {
                        "name": "Tolerance Cells",
                        "sgroup": "Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "outrc",
                    {
                        "name": "Surface Water Rating Tables",
                        "sgroup": "Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "fpfroude_cells",
                    {
                        "name": "Froude Cells",
                        "sgroup": "Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "spatialshallow_cells",
                    {
                        "name": "Shallow-n Cells",
                        "sgroup": "Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "gutter_globals",
                    {
                        "name": "Gutter Globals",
                        "sgroup": "Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "attrs_defaults": {
                            "height": "0.88",
                            "width": "0.99",
                            "n_value": "0.77",
                        },
                        "advanced": True
                    },
                ),
                (
                    "tailing_cells",
                    {
                        "name": "Tailing Cells",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Boundary Conditions",
                        "styles": ["tailing_cells.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": False
                    },
                ),
                (
                    "inflow",
                    {
                        "name": "Inflow",
                        "sgroup": "Boundary Conditions Tables",
                        "styles": ["inflow.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "outflow",
                    {
                        "name": "Outflow",
                        "sgroup": "Boundary Conditions Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "inflow_cells",
                    {
                        "name": "Inflow Cells",
                        "sgroup": "Boundary Conditions Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "outflow_cells",
                    {
                        "name": "Outflow Cells",
                        "sgroup": "Boundary Conditions Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "qh_params",
                    {
                        "name": "QH Parameters",
                        "sgroup": "Boundary Conditions Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "qh_params_data",
                    {
                        "name": "QH Parameters Data",
                        "sgroup": "Boundary Conditions Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "qh_table",
                    {
                        "name": "QH Tables",
                        "sgroup": "Boundary Conditions Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "qh_table_data",
                    {
                        "name": "QH Tables Data",
                        "sgroup": "Boundary Conditions Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "inflow_time_series",
                    {
                        "name": "Inflow Time Series",
                        "sgroup": "Boundary Conditions Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "inflow_time_series_data",
                    {
                        "name": "Inflow Time Series Data",
                        "sgroup": "Boundary Conditions Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "outflow_time_series",
                    {
                        "name": "Outflow Time Series",
                        "sgroup": "Boundary Conditions Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "outflow_time_series_data",
                    {
                        "name": "Outflow Time Series Data",
                        "sgroup": "Boundary Conditions Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "buildings_stats",
                    {
                        "name": "Buildings Statistics",
                        "sgroup": "Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                # Rain Tables:
                (
                    "rain",
                    {
                        "name": "Rain",
                        "sgroup": "Rain Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "rain_time_series",
                    {
                        "name": "Rain Time Series",
                        "sgroup": "Rain Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "rain_time_series_data",
                    {
                        "name": "Rain Time Series Data",
                        "sgroup": "Rain Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "rain_arf_cells",
                    {
                        "name": "Rain ARF Cells",
                        "sgroup": "Rain Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "raincell",
                    {
                        "name": "Realtime Rainfall",
                        "sgroup": "Rain Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "raincell_data",
                    {
                        "name": "Realtime Rainfall Data",
                        "sgroup": "Rain Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": True
                    },
                ),
                # Calibration Data:
                (
                    "wstime",
                    {
                        "name": "Water Surface in Time",
                        "sgroup": "Calibration Data",
                        "styles": ["wstime.qml"],
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "wsurf",
                    {
                        "name": "Water Surface",
                        "sgroup": "Calibration Data",
                        "styles": ["wsurf.qml"],
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                # Evaporation Tables:
                (
                    "evapor",
                    {
                        "name": "Evaporation",
                        "sgroup": "Evaporation Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "evapor_hourly",
                    {
                        "name": "Hourly data",
                        "sgroup": "Evaporation Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "evapor_monthly",
                    {
                        "name": "Monthly data",
                        "sgroup": "Evaporation Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                # Levee and Breach Tables:
                (
                    "levee_general",
                    {
                        "name": "Levee General",
                        "sgroup": "Levee and Breach Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "levee_failure",
                    {
                        "name": "Levee Failure",
                        "sgroup": "Levee and Breach Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "breach_global",
                    {
                        "name": "Breach Global Data",
                        "sgroup": "Levee and Breach Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "breach_cells",
                    {
                        "name": "Breach Cells",
                        "sgroup": "Levee and Breach Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "levee_fragility",
                    {
                        "name": "Levee Fragility",
                        "sgroup": "Levee and Breach Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "breach_fragility_curves",
                    {
                        "name": "Breach Fragility Curves",
                        "sgroup": "Levee and Breach Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                # Multiple Domain Tables
                (
                    "mult_domains_methods",
                    {
                        "name": "Multiple Domains",
                        "sgroup": "Multiple Domains Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "md_method_1",
                    {
                        "name": "Import Method 1",
                        "sgroup": "Multiple Domains Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "md_method_2",
                    {
                        "name": "Import Method 2",
                        "sgroup": "Multiple Domains Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                # Sediment Transport areas (with polygon geometry (square)):
                (
                    "sed_supply_areas",
                    {
                        "name": "Supply Areas",
                        "sgroup": "Sediment Transport",
                        "styles": ["sed_supply_areas.qml"],
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "sed_group_areas",
                    {
                        "name": "Group Areas",
                        "sgroup": "Sediment Transport",
                        "styles": ["sed_group_areas.qml"],
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "sed_rigid_areas",
                    {
                        "name": "Rigid Bed Areas",
                        "sgroup": "Sediment Transport",
                        "styles": ["sed_rigid_areas.qml"],
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                # (
                #     "mud_areas",
                #     {
                #         "name": "Mud Areas",
                #         "sgroup": "Sediment Transport",
                #         "styles": ["mud_areas.qml"],
                #         "attrs_edit_widgets": {},
                #         "visible": False,
                #         "readonly": False,
                #     },
                # ),
                # Other sediment transport tables:
                (
                    "sed",
                    {
                        "name": "Sediment General Parameters",
                        "sgroup": "Sediment Transport Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "sed_groups",
                    {
                        "name": "Sediment Size Fraction Groups",
                        "sgroup": "Sediment Transport Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "sed_group_frac_data",
                    {
                        "name": "Sediment Size Fraction Groups Data",
                        "sgroup": "Sediment Transport Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "sed_group_cells",
                    {
                        "name": "Sediment Size Fraction Group Cells",
                        "sgroup": "Sediment Transport Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "sed_supply_cells",
                    {
                        "name": "Supply Rating Curve Nodes",
                        "sgroup": "Sediment Transport Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "sed_supply_frac_data",
                    {
                        "name": "Supply Rating Curve Data",
                        "sgroup": "Sediment Transport Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "sed_rigid_cells",
                    {
                        "name": "Rigid Bed Cells",
                        "sgroup": "Sediment Transport Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "mud",
                    {
                        "name": "Mud Parameters",
                        "sgroup": "Sediment Transport Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "mud_cells",
                    {
                        "name": "Mud Cell",
                        "sgroup": "Sediment Transport Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": True,
                        "advanced": True
                    },
                ),
                # Channel  Tables:
                (
                    "user_chan_r",
                    {
                        "name": "User Cross Sections (user_chan_r)",
                        "sgroup": "Channel Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "user_chan_v",
                    {
                        "name": "User Cross Sections (user_chan_v)",
                        "sgroup": "Channel Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "user_chan_t",
                    {
                        "name": "User Cross Sections (user_chan_t)",
                        "sgroup": "Channel Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "user_chan_n",
                    {
                        "name": "User Cross Sections (user_chan_n)",
                        "sgroup": "Channel Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "user_xsec_n_data",
                    {
                        "name": "User Cross Sections Data (user_xsec_n_data)",
                        "sgroup": "Channel Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "chan_r",
                    {
                        "name": " Cross Sections (chan-r) Schematized",
                        "sgroup": "Channel Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "chan_v",
                    {
                        "name": " Cross Sections (chan_v) Schematized",
                        "sgroup": "Channel Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "chan_t",
                    {
                        "name": " Cross Sections (chan_t) Schematized",
                        "sgroup": "Channel Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "chan_n",
                    {
                        "name": " Cross Sections (chan_n) Schematized",
                        "sgroup": "Channel Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "xsec_n_data",
                    {
                        "name": "Schematized Cross Sections Data (xsec_n_data)",
                        "sgroup": "Channel Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "chan_wsel",
                    {
                        "name": "Channel Initial Flow Depths (chan_wsel)",
                        "sgroup": "Channel Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "noexchange_chan_cells",
                    {
                        "name": "No-Exchange Channel Cells",
                        "sgroup": "Channel Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": True
                    },
                ),
                (
                    "chan_elems_interp",
                    {
                        "name": "chan_elems_interp",
                        "sgroup": "Channel Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": True,
                        "advanced": True
                    },
                ),
                # Multiple Channel  Tables:
                (
                    "mult",
                    {
                        "name": "Multiple Channels Global Parameters (mult)",
                        "sgroup": "Multiple Channels Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "mult_cells",
                    {
                        "name": "Multiple Channels Cells (mult_cells)",
                        "sgroup": "Multiple Channels Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "simple_mult_cells",
                    {
                        "name": "Simple Mult. Chann. Cells (simple_mult_cells)",
                        "sgroup": "Multiple Channels Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "visible": False,
                        "readonly": False,
                        "advanced": True
                    },
                ),
                # Hydraulic Structures Tables:
                (
                    "struct",
                    {
                        "name": "Hydraulic Structures",
                        "sgroup": "Schematic Layers",
                        "ssgroup": "Hydraulic Structures",
                        "styles": ["struc.qml"],
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": False
                    },
                ),
                (
                    "rat_curves",
                    {
                        "name": "Rating Curves",
                        "sgroup": "Hydraulic Structures Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "repl_rat_curves",
                    {
                        "name": "Replacement Rating Curves",
                        "sgroup": "Hydraulic Structures Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "rat_table",
                    {
                        "name": "Rating Tables",
                        "sgroup": "Hydraulic Structures Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "culvert_equations",
                    {
                        "name": "Culvert Equations",
                        "sgroup": "Hydraulic Structures Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "storm_drains",
                    {
                        "name": "Hystruc Storm Drains",
                        "sgroup": "Hydraulic Structures Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "bridge_variables",
                    {
                        "name": "Bridge Data",
                        "sgroup": "Hydraulic Structures Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
                (
                    "bridge_xs",
                    {
                        "name": "Bridge Cross Sections",
                        "sgroup": "Hydraulic Structures Tables",
                        "styles": None,
                        "attrs_edit_widgets": {},
                        "readonly": False,
                        "advanced": True
                    },
                ),
            ]
        )
        # set QGIS layer (qlyr) to None for each table
        for lyr in self.data:
            self.data[lyr]["qlyr"] = None

        self.layer_names = [layer_info["name"] for layer_info in self.data.values()]

    def load_layer(
        self,
        table,
        uri,
        group,
        name,
        subgroup=None,
        subsubgroup=None,
        style=None,
        visible=True,
        readonly=False,
        advanced=False,
        provider="ogr",
    ):
        # try:
        # check if the layer is already loaded
        lyr_exists = self.layer_exists_in_group(uri, group)
        if not lyr_exists:
            start_time = time.time()
            vlayer = QgsVectorLayer(uri, name, provider)
            self.uc.log_info(
                "\t{0:.3f} seconds => loading {1} - create QgsVectorLayer".format(time.time() - start_time, name)
            )
            if not vlayer.isValid():
                QApplication.restoreOverrideCursor()
                msg = "WARNING 060319.1821: Unable to load layer {}".format(name)
                self.uc.show_warn(
                    msg + "\n\nAre you loading an old project?\nTry using the 'Import from GeoPackage' tool."
                )
                self.uc.log_info(
                    msg + "\n\nAre you loading an old project?\nTry using the 'Import from GeoPackage' tool."
                )
                raise Flo2dLayerInvalid(msg)

            start_time = time.time()
            QgsProject.instance().addMapLayer(vlayer, False)
            self.uc.log_info(
                "\t{0:.3f} seconds => loading {1} - add to registry".format(time.time() - start_time, name)
            )
            # get target tree group
            start_time = time.time()
            if subgroup:
                grp = self.get_subgroup(group, subgroup)
                if not subgroup == "User Layers" and not subgroup == "Schematic Layers":
                    grp.setExpanded(False)
                    if self.ilg is not None:
                        self.ilg.hideGroup(subgroup)
                else:
                    pass
                if subsubgroup:
                    grp = self.get_subgroup(subgroup, subsubgroup)
                    grp.setExpanded(False)
                else:
                    pass
            else:
                grp = self.get_group(group)
            # add layer to the tree group
            tree_lyr = grp.addLayer(vlayer)
            self.uc.log_info(
                "\t{0:.3f} seconds => loading {1} - add to layer group".format(time.time() - start_time, name)
            )
        else:
            start_time = time.time()
            if subgroup:
                grp = self.get_subgroup(group, subgroup)
                if not subgroup == "User Layers" and not subgroup == "Schematic Layers":
                    grp.setExpanded(False)
                    if self.ilg is not None:
                        self.ilg.hideGroup(subgroup)
                else:
                    pass
            tree_lyr = self.get_layer_tree_item(lyr_exists)
            self.update_layer_extents(tree_lyr.layer())
            self.uc.log_info(
                "\t{0:.3f} seconds => loading {1} - only update extents".format(time.time() - start_time, name)
            )
        self.data[table]["qlyr"] = tree_lyr.layer()

        # set visibility
        if not lyr_exists:
            if visible:
                vis = Qt.Checked
            else:
                vis = Qt.Unchecked
            tree_lyr.setItemVisibilityChecked(vis)
            tree_lyr.setExpanded(False)
        # preserve layer visibility for existing layers

        # set style
        if style:
            start_time = time.time()
            style_path = get_file_path("styles", style)
            if os.path.isfile(style_path):
                err_msg, res = self.data[table]["qlyr"].loadNamedStyle(style_path)
                if not res:
                    QApplication.restoreOverrideCursor()
                    msg = "Unable to load style for layer {}.\n{}".format(name, err_msg)
                    raise Flo2dError(msg)
            else:
                QApplication.restoreOverrideCursor()
                raise Flo2dError("Unable to load style file {}".format(style_path))
            self.uc.log_info("\t{0:.3f} seconds => loading {1} - set style".format(time.time() - start_time, name))

        # check if the layer should be 'readonly'

        if readonly:
            start_time = time.time()
            try:
                # check if the signal is already connected
                self.data[table]["qlyr"].beforeEditingStarted.disconnect(self.warn_readonly)
            except TypeError:
                pass
            self.data[table]["qlyr"].beforeEditingStarted.connect(self.warn_readonly)
            self.uc.log_info(
                "\t{0:.3f} seconds => loading {1} - set readonly".format(time.time() - start_time, name)
            )
        else:
            pass

        # Check if it is an advanced layer
        if advanced:
            if self.ilg is not None:
                if subsubgroup == "Gutters" or subsubgroup == "Multiple Channels" or subsubgroup == "Streets":
                    self.ilg.hideGroup(subsubgroup, subgroup)

        return self.data[table]["qlyr"].id()

        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     msg = "ERROR 270123.1142 Unable to load  layer {}.".format(table)
        #     self.uc.bar_error(msg)

    def warn_readonly(self):
        # self.uc.bar_warn("All changes to this layer can be overwritten by changes in the User Layer.")
        pass

    def enter_edit_mode(self, table_name, default_attr_exp=None):
        if not self.group:
            msg = "Connect to a GeoPackage!"
            self.uc.bar_warn(msg)
            return None
        # try:
        lyr = self.data[table_name]["qlyr"]
        self.iface.setActiveLayer(lyr)
        lyr_fields = lyr.fields()
        if not default_attr_exp:
            for idx in lyr_fields.allAttributesList():
                field = lyr_fields.field(idx)
                field.setDefaultValueDefinition(QgsDefaultValue(""))
        else:
            for attr, exp in default_attr_exp.items():
                idx = lyr_fields.lookupField(attr)
                default_value = QgsDefaultValue()
                default_value.setExpression(f"'{exp}'")
                lyr.setDefaultValueDefinition(idx, default_value)
        lyr.startEditing()
        self.iface.actionAddFeature().trigger()
        return True
        # except Exception as e:
        #     msg = "Could'n start edit mode for table {}. Is it loaded into QGIS project?".format(table_name)
        #     self.uc.bar_warn(msg)
        #     return None

    def any_lyr_in_edit(self, *table_name_list):
        """
        Return True if any layer from the table list is in edit mode.
        """
        in_edit_mode = False
        if not table_name_list:
            return None
        for t in table_name_list:
            if self.data[t]["qlyr"].isEditable():
                in_edit_mode = True
        return in_edit_mode

    def save_lyrs_edits(self, *table_name_list):
        """
        Save changes to each layer if it is in edit mode.
        """
        in_edit_mode = False
        if not table_name_list:
            return None
        for t in table_name_list:
            if self.data[t]["qlyr"].isEditable():
                in_edit_mode = True
                try:
                    lyr = self.data[t]["qlyr"]
                    lyr.commitChanges()
                except Exception as e:
                    msg = "Could'n save changes for table {}.".format(t)
                    self.uc.bar_warn(msg)
        return in_edit_mode

    def rollback_lyrs_edits(self, *table_name_list):
        """
        Save changes to each layer if it is in edit mode.
        """
        in_edit_mode = False
        if not table_name_list:
            return None
        for t in table_name_list:
            if self.data[t]["qlyr"].isEditable():
                in_edit_mode = True
                try:
                    lyr = self.data[t]["qlyr"]
                    lyr.rollBack()
                except Exception as e:
                    msg = "Could'n rollback changes for table {}.".format(t)
                    self.uc.bar_warn(msg)
        return in_edit_mode

    def get_layer_tree_item(self, layer_id):
        if layer_id:
            layeritem = self.root.findLayer(layer_id)
            if not layeritem:
                msg = "Layer {} doesn't exist in the layers tree.".format(layer_id)
                raise Flo2dLayerNotFound(msg)
            return layeritem
        else:
            raise Flo2dLayerNotFound("Layer id not specified")

    def get_layer_by_name(self, name, group=None):
        try:
            if group:
                gr = self.get_group(group, create=False)
            else:
                gr = self.root
            layeritem = None
            if gr and name:
                layers = QgsProject.instance().mapLayersByName(name)

                for layer in layers:
                    layeritem = gr.findLayer(layer.id())
                    if not layeritem:
                        continue
                    else:
                        return layeritem
            else:
                pass
            return layeritem
        except TypeError:
            self.uc.bar_warn("ERROR 12117.0602")

    def list_group_vlayers(self, group=None, only_visible=True, skip_views=False):
        if not group:
            grp = self.root
        else:
            grp = self.get_group(group, create=False)
        views_list = []
        l = []
        if grp:
            for lyr in grp.findLayers():
                if lyr.layer().type() == 0 and lyr.layer().geometryType() < 3:
                    if skip_views and lyr.layer().name() in views_list:
                        continue
                    else:
                        if only_visible and not lyr.isVisible():
                            continue
                        else:
                            l.append(lyr.layer())
        else:
            pass
        return l

    def list_group_rlayers(self, group=None):
        if not group:
            grp = self.root
        else:
            grp = self.get_group(group, create=False)
        l = []
        if grp:
            for lyr in grp.findLayers():
                if lyr.layer() is not None:
                    if lyr.layer().type() == 1:
                        l.append(lyr.layer())
        else:
            pass
        return l

    def repaint_layers(self):
        for lyr in self.lyrs_to_repaint:
            lyr.triggerRepaint()
        self.lyrs_to_repaint = []

    def refresh_layers(self):
        for layer in self.iface.mapCanvas().layers():
            layer.triggerRepaint()

    def connect_lyrs_reload(self, layer1, layer2):
        """
        Reload layer1 and update its extent when layer2 modifications are saved.
        """
        layer2.editingStopped.connect(layer1.reload)

    def new_group(self, name):
        if isinstance(name, str):
            self.root.addGroup(name)
        else:
            raise Flo2dNotString("{} is not a string or unicode".format(repr(name)))

    def new_subgroup(self, group, subgroup):
        grp = self.root.findGroup(group)
        grp.addGroup(subgroup)

    def remove_group_by_name(self, name):
        grp = self.root.findGroup(name)
        if grp:
            self.root.removeChildNode(grp)

    def get_group(self, name, create=True):
        grp = self.root.findGroup(name)
        if not grp and create:
            grp = self.root.addGroup(name)
        return grp

    def get_subgroup(self, group, subgroup, create=True):
        grp = self.get_group(group, create=create)
        subgrp = grp.findGroup(subgroup)
        if not subgrp and create:
            subgrp = grp.addGroup(subgroup)
        return subgrp

    def get_flo2d_groups(self):
        all_groups = [c.name() for c in self.root.children() if isinstance(c, QgsLayerTreeGroup)]
        f2d_groups = []
        for g in all_groups:
            if g.startswith("FLO-2D_"):
                tg = self.get_group(g, create=False)
                f2d_groups.append(tg)
        return f2d_groups

    def get_group_subgroups(self, group_name):
        children = self.get_group(group_name, create=False).children()
        sgroups = []
        for ch in children:
            if type(ch) == QgsLayerTreeGroup:
                sgroups.append(ch)
        return sgroups

    def expand_all_flo2d_groups(self):
        f2d_groups = self.get_flo2d_groups()
        for gr in f2d_groups:
            gr.setExpanded(True)

    def collapse_all_flo2d_groups(self):
        f2d_groups = self.get_flo2d_groups()
        for gr in f2d_groups:
            gr.setExpanded(False)

    def expand_flo2d_group(self, group_name):
        group = self.get_group(group_name, create=False)
        if group:
            group.setExpanded(True)
            first_lyr = self.get_layer_by_name("Computational Domain", group=group_name).layer()
            if first_lyr:
                self.iface.layerTreeView().setCurrentLayer(first_lyr)
        else:
            pass

    def collapse_all_flo2d_subgroups(self, group):
        for sgr in self.get_group_subgroups(group):
            sgr.setExpanded(False)

    def collapse_flo2d_subgroup(self, group_name, subgroup_name):
        sg = self.get_subgroup(group_name, subgroup_name, create=False)
        if sg:
            sg.setExpanded(False)

    def expand_flo2d_subgroup(self, group_name, subgroup_name):
        sg = self.get_subgroup(group_name, subgroup_name, create=False)
        if sg:
            sg.setExpanded(True)

    def collapse_group_layers(self, group_name):
        group = self.get_group(group_name, create=False)

    def clear_legend_selection(self):
        sel_lyrs = self.iface.layerTreeView().selectedLayers()
        if sel_lyrs:
            self.iface.layerTreeView().setCurrentLayer(sel_lyrs[0])

    def layer_exists_in_group(self, uri, group=None):
        grp = self.root.findGroup(group) if group is not None else self.root
        if grp:
            for lyr in grp.findLayers():
                if normpath(lyr.layer().dataProvider().dataSourceUri()) == normpath(uri):
                    return lyr.layer().id()
        return None

    @staticmethod
    def get_layer_table_name(layer):
        t = layer.dataProvider().dataSourceUri().split("=")[1]
        if t:
            return t
        else:
            return None

    def update_layer_extents(self, layer):
        # check if it is a spatial table
        t = self.get_layer_table_name(layer)
        sql = """SELECT table_name FROM gpkg_contents WHERE table_name=? AND data_type = 'features'; """
        try:
            is_spatial = self.gutils.execute(sql, (t,)).fetchone()[0]
        except Exception as e:
            return
        if is_spatial:
            self.gutils.update_layer_extents(t)
            sql = """SELECT min_x, min_y, max_x, max_y FROM gpkg_contents WHERE table_name=?;"""
            min_x, min_y, max_x, max_y = self.gutils.execute(sql, (t,)).fetchone()
            try:
                # works if min & max not null
                layer.setExtent(QgsRectangle(min_x, min_y, max_x, max_y))
            except Exception as e:
                return
        else:
            pass

    @staticmethod
    def remove_layer_by_name(name):
        layers = QgsProject.instance().mapLayersByName(name)
        for layer in layers:
            QgsProject.instance().removeMapLayer(layer.id())

    @staticmethod
    def remove_layer(layer_id):
        # do nothing if layer id does not exists
        QgsProject.instance().removeMapLayer(layer_id)

    @staticmethod
    def is_str(name):
        if isinstance(name, str):
            return True
        else:
            msg = "{} is of type {}, not a string or unicode".format(repr(name), type(name))
            raise Flo2dNotString(msg)

    def load_all_layers(self, gutils):
        self.gutils = gutils
        self.clear_legend_selection()
        group = "FLO-2D_{}".format(os.path.basename(self.gutils.path).replace(".gpkg", ""))
        self.collapse_all_flo2d_groups()
        self.group = group

        pd = QProgressDialog("Loading layers...", None, 0, len(self.data))
        pd.setWindowTitle("Loading layers")
        pd.setModal(True)
        pd.forceShow()
        pd.setValue(0)
        i = 0

        for lyr in self.data:
            pd.setLabelText(f"Loading {lyr}...")
        # try:
            start_time = time.time()
            data = self.data[lyr]
            if data["styles"]:
                lstyle = data["styles"][0]
            else:
                lstyle = None
            uri = self.gutils.path + "|layername={}".format(lyr)
            try:
                lyr_is_on = data["visible"]
            except Exception as e:
                lyr_is_on = True
            try:
                subsubgroup = data["ssgroup"]
            except Exception as e:
                subsubgroup = None
            lyr_id = self.load_layer(
                lyr,
                uri,
                group,
                data["name"],
                style=lstyle,
                subgroup=data["sgroup"],
                subsubgroup=subsubgroup,
                visible=lyr_is_on,
                readonly=data["readonly"],
                advanced=data["advanced"]
            )
            l = self.get_layer_tree_item(lyr_id).layer()
            if lyr == "blocked_cells":
                self.update_style_blocked(lyr_id)
            if data["attrs_edit_widgets"]:
                for attr, widget_data in data["attrs_edit_widgets"].items():
                    attr_idx = l.fields().lookupField(attr)
                    l.setEditorWidgetSetup(
                        attr_idx,
                        QgsEditorWidgetSetup(widget_data["name"], widget_data["config"]),
                    )
            else:
                pass  # no attributes edit widgets config
            # set attributes default value, if any
            try:
                dvs = data["attrs_defaults"]
            except Exception as e:
                dvs = None
            if dvs:
                for attr, val in dvs.items():
                    field = l.fields().field(attr)
                    field.setDefaultValueDefinition(QgsDefaultValue(val))
            else:
                pass
            self.uc.log_info("{0:.3f} seconds => total loading {1} ".format(time.time() - start_time, data["name"]))

            # except Exception as e:
            #     QApplication.restoreOverrideCursor()
            #     msg = "ERROR 270123.1137: Unable to load  layer {}.".format(lyr)
            #     self.uc.bar_error(msg)

            i += 1
            QApplication.processEvents()
            pd.setValue(i)

        s = QSettings()
        s.setValue("FLO-2D/advanced_layers", False)

        grp = self.get_group(self.group)
        grp.setExpanded(True)

        # >>>>>>>>>>>>>>>>>111111111

        # <<<<<<<<<<<<<<<<111111111

        # #>>>>>>>>>>>>>>>>>2222222222222222222
        #
        #         # 0. Remove Boundary group if exists from previous project.
        #         root = QgsProject.instance().layerTreeRoot()
        #         for grp in root.findGroups():
        #             for subgroup in grp.findGroups():
        #                 for subsubgroup in subgroup.findGroups():
        #                     if subsubgroup.name() == "XXXX":
        #                         subsubgroup.removeAllChildren()
        #                         subgroup.removeChildNode(subsubgroup)
        #
        #
        #         # 1. Get group names and list of layer ids
        #         root = QgsProject.instance().layerTreeRoot()
        #         dictGroups={}
        #         prefix="Boundary Condition"
        #         for layer in self.root.findLayers():
        #           if QgsLayerTree.isLayer(layer):
        #             if prefix in layer.name():
        #                 if not prefix in dictGroups:
        #                   dictGroups[prefix]=[]
        #                 if layer.layerId() not in dictGroups[prefix]:
        #                     dictGroups[prefix].append(layer.layerId())
        #
        #
        #         # # 1.1 Rename layers
        #         # root = QgsProject.instance().layerTreeRoot()
        #         # prefix="Boundary Condition"
        #         # to_be_deleted = []
        #         # for layer in self.root.findLayers():
        #         #   if QgsLayerTree.isLayer(layer):
        #         #     if prefix in layer.name():
        #         #         # layer.setName("Delete")
        #         #         to_be_deleted.append(layer)
        #
        #
        #
        #
        #         # # 2.1 Move "Boundaries" group to top of "User Layers"
        #         # cloned_group1 = myNewGroup.clone()
        #         # myOriginalGroup.insertChildNode(0, cloned_group1)
        #         # myOriginalGroup.removeChildNode(myNewGroup)
        #
        #
        #
        #         # 2. Create Boundaries group
        #         myOriginalGroup = self.root.findGroup("User Layers")
        #         myNewGroup = myOriginalGroup.addGroup("XXXX")
        #         for key in reversed(dictGroups):
        #             for id in dictGroups[key]:
        #                 layer = self.root.findLayer(id)
        #                 clone = layer.clone()
        #                 myNewGroup.insertChildNode(0, clone)
        #
        #         # # 3. Remove "Boundary Condition..." layers
        #         # if to_be_deleted:
        #         #     for tbd in to_be_deleted:
        #         #         qinst = QgsProject.instance()
        #         #         qinst.removeMapLayer(qinst.mapLayersByName(tbd.name())[0].id())
        #
        #         # grp = self.root.findGroup("User Layers")
        #         # for lyr in grp.findLayers():
        #         #     if "Boundary Condition" in lyr.name():
        #         #         self.remove_layer(id)
        #
        #
        # #<<<<<<<<<<<<<<<<2222222222222222222222222

        # lyr = QgsProject.instance().mapLayersByName("Boundary Condition Polygons")[0]
        # root = QgsProject.instance().layerTreeRoot()
        # mylayer = root.findLayer(lyr.id())
        # myClone = mylayer.clone()
        # parent = mylayer.parent()
        # grp = root.findGroup("User Layers")
        # grp.insertChildNode(0, myClone)
        # parent.removeChildNode(mylayer)

        # root = QgsProject.instance().layerTreeRoot()
        # lyr = QgsProject.instance().mapLayersByName("Boundary Condition Polygons")[0]
        # myClone= lyr.clone()
        # grp = root.children()[index] # index: group layer index
        # grp.insertChildNode(0, QgsLayerTreeLayer(myClone))
        # root.removeLayer(lyr)

        # self.expand_flo2d_group(group)
        # self.collapse_all_flo2d_subgroups(group)
        # self.expand_flo2d_subgroup(group, "User Layers")

        # root = QgsProject.instance().layerTreeRoot()
        # grp = root.findGroup("User Layers")
        # sub_group = grp.addGroup("Boundary Conditions")
        #
        # sgrp = self.get_subgroup(self.group, "Boundary Condition Points")
        # # sgrp = self.get_group("Boundary Condition Points", create=False)
        # # ly = self.get_layer_by_name("Boundary Condition Points", group=self.group).layer()
        # if sgrp:
        #     mylayer = root.findLayer(sgrp.id())
        #     myClone = mylayer.clone()
        #
        #     sub_group.insertChildNode(0, myClone)
        #     QgsProject.instance().removeMapLayers( [ly.id()] )
        #
        # ly = self.get_layer_by_name("Boundary Condition Lines", group=self.group).layer()
        # if ly:
        #     mylayer = root.findLayer(ly.id())
        #     myClone = mylayer.clone()
        #     sub_group.insertChildNode(0, myClone)
        #     QgsProject.instance().removeMapLayers( [ly.id()] )
        #
        # ly = self.get_layer_by_name("Boundary Condition Polygons", group=self.group).layer()
        # if ly:
        #     mylayer = root.findLayer(ly.id())
        #     myClone = mylayer.clone()
        #     sub_group.insertChildNode(0, myClone)
        #     QgsProject.instance().removeMapLayers( [ly.id()] )

    def update_style_blocked(self, lyr_id):
        cst = self.gutils.get_cont_par("CELLSIZE")
        if is_number(cst) and not cst == "":
            cs = float(cst)
        else:
            return
        # update geometry gen definitions for WRFs
        s = cs * 0.35
        dir_lines = {
            1: (-s / 2.414, s, s / 2.414, s),
            2: (s, s / 2.414, s, -s / 2.414),
            3: (s / 2.414, -s, -s / 2.414, -s),
            4: (-s, -s / 2.414, -s, s / 2.414),
            5: (s / 2.414, s, s, s / 2.414),
            6: (s, -s / 2.414, s / 2.414, -s),
            7: (-s / 2.414, -s, -s, -s / 2.414),
            8: (-s, s / 2.414, -s / 2.414, s),
        }
        lyr = self.get_layer_tree_item(lyr_id).layer()
        sym = lyr.renderer().symbol()
        for nr in range(1, sym.symbolLayerCount()):
            exp = "make_line(translate(centroid($geometry), {}, {}), translate(centroid($geometry), {}, {}))"
            sym.symbolLayer(nr).setGeometryExpression(exp.format(*dir_lines[nr]))
        # ARF
        exp_arf = """make_polygon( make_line(translate( $geometry , -{0}, {0}),
                                             translate($geometry, {0}, {0}),
                                             translate($geometry, {0}, -{0}),
                                             translate($geometry, -{0}, -{0}),
                                             translate($geometry, -{0}, {0})))""".format(
            cs * 0.5
        )
        sym.symbolLayer(0).setGeometryExpression(exp_arf)

    def show_feat_rubber(self, lyr_id, fid, color=QColor(255, 0, 0), clear=True):
        lyr = self.get_layer_tree_item(lyr_id).layer()
        gt = lyr.geometryType()
        if clear:
            self.clear_rubber()
        self.rb = QgsRubberBand(self.canvas, gt)
        color.setAlpha(255)
        self.rb.setColor(color)
        self.rb.setFillColor(color)
        fill_color = color
        if gt == 2:
            fill_color.setAlpha(100)
            self.rb.setFillColor(fill_color)
        self.rb.setWidth(3)
        try:
            feat = next(lyr.getFeatures(QgsFeatureRequest(fid)))
        except StopIteration:
            return
        self.rb.setToGeometry(feat.geometry(), lyr)

    def clear_rubber(self):
        if self.rb:
            for i in range(3):
                if i == 0:
                    self.rb.reset(QgsWkbTypes.PointGeometry)
                elif i == 1:
                    self.rb.reset(QgsWkbTypes.LineGeometry)
                elif i == 2:
                    self.rb.reset(QgsWkbTypes.PolygonGeometry)

    def zoom_to_all(self):
        if self.gutils.is_table_empty("grid"):
            return
        else:
            self.gutils.update_layer_extents("grid")
            grid = self.get_layer_by_name("Grid", self.group)
            extent = grid.layer().extent()
            self.iface.mapCanvas().setExtent(extent)
            self.iface.mapCanvas().refresh()

    def save_edits_and_proceed(self, layer_name):
        """
        If the layer is in edit mode, ask users for saving changes and proceeding.
        """
        try:
            l = self.get_layer_by_name(layer_name, group=None).layer()
            if l.isEditable():
                # ask user for saving changes
                q = "{} layer is in edit mode. Save changes and proceed?".format(layer_name)
                if self.uc.question(q):
                    l.commitChanges()
                    return True
                else:
                    self.uc.bar_info("Action cancelled!", dur=3)
                    self.uc.log_info("Action cancelled!")
                    return False
            else:
                return True
        except TypeError:
            self.uc.bar_warn("ERROR 121117.0544")
