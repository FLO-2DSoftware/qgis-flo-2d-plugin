# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QMenu
from qgis._core import QgsVectorLayerJoinInfo
# FLO-2D Preprocessor tools for QGIS
# Copyright Â© 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.core import QgsFeatureRequest
from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtGui import QColor, QIntValidator, QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QApplication

from ..flo2d_tools.grid_tools import number_of_elements, render_grid_elevations2, render_grid_subdomains, \
    clear_grid_render, render_grid_mannings, render_grid
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from ..utils import (
    is_number,
    m_fdata,
    second_smallest,
    set_min_max_elevs, set_min_max_n_values,
)
from .ui_utils import center_canvas, load_ui, set_icon, zoom

uiDialog, qtBaseClass = load_ui("grid_info_widget")


class GridInfoWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, plot, table, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.uc = UserCommunication(iface, "FLO-2D")
        self.canvas = iface.mapCanvas()
        self.plot = plot
        self.plot_item_name = None
        self.table = table
        self.tview = table.tview
        self.data_model = QStandardItemModel()
        self.lyrs = lyrs
        self.setupUi(self)
        self.setEnabled(True)
        self.gutils = None
        self.grid = None
        self.mann_default = None
        self.cell_Edit = None
        self.n_cells = 0
        self.d1 = []
        self.d2 = []

        self.control_lyr = self.lyrs.data["cont"]["qlyr"]

        self.setup_connection()
        validator = QIntValidator()
        self.idEdit.setValidator(validator)

        self.find_cell_btn.clicked.connect(self.find_cell)
        set_icon(self.find_cell_btn, "eye-svgrepo-com.svg")

        self.populate_render()

        self.render_tb.clicked.connect(self.clear_render)

    def populate_render(self):
        # Create the QMenu (dropdown)
        menu = QMenu()
        # Create the grid menu
        group_grid_menu = QMenu("Grid", self)
        group_grid_menu.addAction("Elevation", self.render_elevations)
        group_grid_menu.addAction("Mannings", self.render_mannings)
        menu.addMenu(group_grid_menu)

        # Create the infiltration menu
        group_infil_menu = QMenu("Infiltration", self)
        menu.addMenu(group_infil_menu)

        group_infil_ga_menu = QMenu("Green Ampt", self)
        group_infil_ga_menu.addAction("Hydraulic Conductivity", lambda: self.render_infiltration_ga("hydc"))
        group_infil_ga_menu.addAction("Soil Suction", lambda: self.render_infiltration_ga("soils"))
        group_infil_ga_menu.addAction("Soil Moisture Deficit", lambda: self.render_infiltration_ga("dtheta"))
        group_infil_ga_menu.addAction("Initial Abstraction", lambda: self.render_infiltration_ga("abstrinf"))
        group_infil_ga_menu.addAction("Impervious Percentage", lambda: self.render_infiltration_ga("rtimpf"))
        group_infil_ga_menu.addAction("Soil Depth", lambda: self.render_infiltration_ga("soil_depth"))
        group_infil_menu.addMenu(group_infil_ga_menu)

        group_infil_scs_menu = QMenu("SCS", self)
        group_infil_scs_menu.addAction("Curve Number", lambda: self.render_infiltration_scs("scsn"))
        group_infil_menu.addMenu(group_infil_scs_menu)

        group_infil_hor_menu = QMenu("Horton", self)
        group_infil_hor_menu.addAction("Initial Infiltration Rate", lambda: self.render_infiltration_horton("fhorti"))
        group_infil_hor_menu.addAction("Final Infiltration Rate", lambda: self.render_infiltration_horton("fhortf"))
        group_infil_hor_menu.addAction("Decay Coefficient", lambda: self.render_infiltration_horton("deca"))
        group_infil_menu.addMenu(group_infil_hor_menu)

        group_areas_menu = QMenu("Areas", self)
        group_areas_menu.addAction("Tolerance", lambda: self.render_areas("tolspatial_cells", "tol"))
        group_areas_menu.addAction("Froude", lambda: self.render_areas("fpfroude_cells", "froudefp"))
        group_areas_menu.addAction("Shallow-n", lambda: self.render_areas("spatialshallow_cells", "shallow_n"))
        group_areas_menu.addAction("Steep Slope-n", lambda: self.render_areas("steep_slope_n_cells", None))
        group_areas_menu.addAction("LID Volume", lambda: self.render_areas("lid_volume_cells", "volume"))
        menu.addMenu(group_areas_menu)

        menu.addAction("Rain ARF", self.render_rainfall)

        menu.addAction("Subdomains", self.render_subdomains)

        self.render_tb.setMenu(menu)

    def setup_connection(self):
        con = self.iface.f2d["con"]
        if con is None:
            return
        else:
            self.con = con
            self.gutils = GeoPackageUtils(self.con, self.iface)

    def setSizeHint(self, width, height):
        self._sizehint = QSize(width, height)

    def sizeHint(self):
        if self._sizehint is not None:
            return self._sizehint
        return super(GridInfoWidget, self).sizeHint()

    def set_info_layer(self, lyr):
        self.grid = lyr
        self.n_cells = number_of_elements(self.gutils, self.grid)
        self.n_cells_lbl.setText("Number of cells: " + "{:,}".format(self.n_cells) + "   ")

    def update_fields(self, fid):
        try:
            if not fid == -1:
                feat = next(self.grid.getFeatures(QgsFeatureRequest(fid)))
                # cell_size = sqrt(feat.geometry().area())
                gid = str(fid)
                if feat["elevation"]:
                    elev = "{:10.4f}".format(feat["elevation"]).strip()
                    elev = elev if float(elev) > -9999 else "-9999"
                    n = feat["n_value"]
                    if not n:
                        n = "{} (default)".format(self.mann_default)
                    else:
                        pass
                    self.idEdit.setText(gid)
                    self.elevEdit.setText(elev)
                    self.mannEdit.setText(str(n))
                    self.cellEdit.setText(str(self.gutils.get_cont_par("CELLSIZE")))
                    self.grid = self.lyrs.data["grid"]["qlyr"]
                    self.n_cells = number_of_elements(self.gutils, self.grid)
                    self.n_cells_lbl.setText("Number of cells: " + "{:,}".format(self.n_cells) + "   ")

                    self.lyrs.show_feat_rubber(self.grid.id(), int(gid), QColor(Qt.yellow))
                else:
                    self.idEdit.setText("")
                    self.elevEdit.setText("")
                    self.mannEdit.setText("")
                    self.cellEdit.setText("")
                    self.n_cells_lbl.setText("Number of cells:       ")
                    self.lyrs.clear_rubber()
            else:
                self.idEdit.setText("")
                self.elevEdit.setText("")
                self.mannEdit.setText("")
                self.cellEdit.setText("")
                self.n_cells_lbl.setText("Number of cells:       ")
                self.lyrs.clear_rubber()

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error(
                "ERROR 290718.1934: error while displaying elevation of cell "
                + str(fid)
                + "\n____________________________________________",
                e,
            )

    def check_render_elevations(self):
        qry = """SELECT value FROM cont WHERE name = 'IBACKUP';"""
        row = self.gutils.execute(qry).fetchone()
        if is_number(row[0]):
            if row[0] == "0":
                self.render_cbo.setCurrentIndex(0)
            else:
                self.render_cbo.setCurrentIndex(2)

    def render(self):
        """
        Function to render different types of features
        """
        if self.render_cbo.currentIndex() == 0:
            self.clear_render()
        if self.render_cbo.currentIndex() == 2:
            self.render_elevations()
        if self.render_cbo.currentIndex() == 3:
            self.render_mannings()
        if self.render_cbo.currentIndex() == 4:
            self.render_subdomains()

    def clear_render(self):
        """
        Call the function to clear the renders on grid_tools
        """
        try:
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                self.uc.log_info("There is no grid! Please create it before running tool.")
                return
            clear_grid_render(self.grid)
            for j in self.grid.vectorJoins():
                self.grid.removeJoin(j.joinLayerId())
            self.lyrs.lyrs_to_repaint = [self.grid]
            self.lyrs.repaint_layers()
            self.render_tb.setText("")
        except Exception as e:
            self.uc.bar_error("ERROR: Clear render failed!")
            self.uc.log_info("ERROR: Clear render failed!")
            self.lyrs.clear_rubber()

    def render_elevations(self):
        try:
            if self.gutils.is_table_empty("user_model_boundary"):
                self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
                self.uc.log_info("There is no computational domain! Please digitize it before running tool.")
                self.render_tb.setText("")
                return
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                self.uc.log_info("There is no grid! Please create it before running tool.")
                self.render_tb.setText("")
                return
            elevs = [x[0] for x in self.gutils.execute("SELECT elevation FROM grid").fetchall()]
            elevs = [x if x is not None else -9999 for x in elevs]
            if elevs:
                mini = min(elevs)
                mini2 = second_smallest(elevs)
                maxi = max(elevs)
                render_grid_elevations2(
                    self.grid,
                    True,
                    mini,
                    mini2,
                    maxi,
                )
                set_min_max_elevs(mini, maxi)
                self.lyrs.lyrs_to_repaint = [self.grid]
                self.lyrs.repaint_layers()
                self.render_tb.setText("Elevation")
        except Exception as e:
            self.uc.show_error("ERROR 110721.0545: render of elevations failed!.\n", e)
            # self.uc.bar_error("ERROR 100721.1759: is the grid defined?")
            self.lyrs.clear_rubber()
            self.render_cbo.setCurrentIndex(0)

    def render_mannings(self):
        try:
            if self.gutils.is_table_empty("user_model_boundary"):
                self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
                self.uc.log_info("There is no computational domain! Please digitize it before running tool.")
                self.render_tb.setText("")
                return
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                self.uc.log_info("There is no grid! Please create it before running tool.")
                self.render_tb.setText("")
                return
            n_values = [x[0] for x in self.gutils.execute("SELECT n_value FROM grid").fetchall()]
            n_values = [x if x is not None else 0.04 for x in n_values]
            if n_values:
                mini = min(n_values)
                mini2 = second_smallest(n_values)
                maxi = max(n_values)
                render_grid_mannings(
                    self.grid,
                    True,
                    mini,
                    mini2,
                    maxi,
                )
                set_min_max_n_values(mini, maxi)
                self.lyrs.lyrs_to_repaint = [self.grid]
                self.lyrs.repaint_layers()
                self.render_tb.setText("Mannings")
        except Exception as e:
            self.uc.show_error("ERROR 110721.0545: render of mannings failed!.\n", e)
            self.render_cbo.setCurrentIndex(0)
            self.lyrs.clear_rubber()

    def render_subdomains(self):
        try:
            # Check if required data exists
            if self.gutils.is_table_empty("user_model_boundary"):
                self.uc.bar_warn("There is no computational domain! Please digitize it before running the tool.")
                self.uc.log_info("There is no computational domain! Please digitize it before running the tool.")
                self.render_tb.setText("")
                return
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running the tool.")
                self.uc.log_info("There is no grid! Please create it before running the tool.")
                self.render_tb.setText("")
                return
            if self.gutils.is_table_empty("schema_md_cells"):
                self.uc.bar_warn("There are no subdomains! Please digitize and assign them before running the tool.")
                self.uc.log_info("There are no subdomains! Please digitize and assign them before running the tool.")
                self.render_tb.setText("")
                return

            self.schema_md_cells = self.lyrs.data["schema_md_cells"]["qlyr"]

            # Remove any pre-existing joins on the grid layer
            for join in self.grid.vectorJoins():
                self.grid.removeJoin(join.joinLayerId())

            # Add a join between the 'grid' layer and 'schema_md_cells' layer
            join_object = QgsVectorLayerJoinInfo()
            join_object.setJoinLayer(self.schema_md_cells)
            join_object.setTargetFieldName("fid")  # Field in 'grid'
            join_object.setJoinFieldName("grid_fid")  # Field in 'schema_md_cells'
            join_object.setUsingMemoryCache(True)  # Use memory cache for efficiency
            join_object.setPrefix("")  # No prefix to keep field names clean

            # Add the join to the grid layer
            self.grid.addJoin(join_object)

            # Extract unique subdomains from the 'subdomain' field in the joined layer
            values = self.schema_md_cells.uniqueValues(
                self.schema_md_cells.fields().lookupField("domain_fid")
            )
            if not values:
                self.uc.bar_warn("No subdomains found to render.")
                self.uc.log_info("No subdomains found to render.")
                return

            # Render the grid layer with categorized symbology
            render_grid_subdomains(self.grid, True, values)

            # Repaint layers
            self.lyrs.lyrs_to_repaint = [self.grid]
            self.lyrs.repaint_layers()
            self.render_tb.setText("Subdomains")
        except Exception as e:
            self.render_cbo.setCurrentIndex(0)
            self.uc.bar_error("ERROR: Rendering subdomains failed!")
            self.uc.log_info("ERROR: Rendering subdomains failed!")

    def render_areas(self, layer_name, field_name):
        try:
            if self.gutils.is_table_empty("user_model_boundary"):
                self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
                self.uc.log_info("There is no computational domain! Please digitize it before running tool.")
                self.render_tb.setText("")
                return
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                self.uc.log_info("There is no grid! Please create it before running tool.")
                self.render_tb.setText("")
                return
            if self.gutils.is_table_empty(layer_name):
                self.uc.bar_warn("Area data is missing. Please schematize it before rendering.")
                self.uc.log_info("Area data is missing. Please schematize it before rendering.")
                self.render_tb.setText("")
                return

            for j in self.grid.vectorJoins():
                self.grid.removeJoin(j.joinLayerId())

            area_layer = self.lyrs.data[layer_name]["qlyr"]

            join_info = QgsVectorLayerJoinInfo()
            join_info.setJoinFieldName("grid_fid")
            join_info.setTargetFieldName("fid")
            join_info.setJoinLayerId(area_layer.id())
            join_info.setUsingMemoryCache(True)
            join_info.setPrefix("area_")
            join_info.setJoinLayer(area_layer)

            # Apply the join to the grid layer
            self.grid.addJoin(join_info)
            if not field_name:
                areas = [0, 1]
                field_name = "global"
            else:
                areas = [x[0] for x in self.gutils.execute(f"""
                SELECT 
                    {field_name} 
                FROM 
                    {layer_name} AS area
                JOIN
                    grid G ON area.grid_fid = G.fid
                """).fetchall()]
            areas = [x if x is not None else -9999 for x in areas]
            if areas:
                mini = min(areas)
                mini2 = second_smallest(areas)
                maxi = max(areas)
                render_grid(
                    self.grid,
                    True,
                    mini,
                    mini2,
                    maxi,
                    f"area_{field_name}"
                )
                set_min_max_elevs(mini, maxi)
                self.lyrs.lyrs_to_repaint = [self.grid]
                self.lyrs.repaint_layers()
                self.render_tb.setText(f"Areas - {field_name}")
        except Exception as e:
            self.uc.show_error("Render of infiltration failed!\n", e)
            self.uc.log_info("Render of infiltration failed!")
            self.lyrs.clear_rubber()
            self.render_tb.setText("")

    def render_infiltration_ga(self, infil_type):
        try:
            if self.gutils.is_table_empty("user_model_boundary"):
                self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
                self.uc.log_info("There is no computational domain! Please digitize it before running tool.")
                self.render_tb.setText("")
                return
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                self.uc.log_info("There is no grid! Please create it before running tool.")
                self.render_tb.setText("")
                return
            if self.gutils.is_table_empty("infil_cells_green"):
                self.uc.bar_warn("Green & Ampt infiltration data is missing. Please schematize it before rendering.")
                self.uc.log_info("Green & Ampt infiltration data is missing. Please schematize it before rendering.")
                self.render_tb.setText("")
                return

            for j in self.grid.vectorJoins():
                self.grid.removeJoin(j.joinLayerId())

            infiltration_ga = self.lyrs.data["infil_cells_green"]["qlyr"]

            join_info = QgsVectorLayerJoinInfo()
            join_info.setJoinFieldName("grid_fid")
            join_info.setTargetFieldName("fid")
            join_info.setJoinLayerId(infiltration_ga.id())
            join_info.setUsingMemoryCache(True)
            join_info.setPrefix("infil_")
            join_info.setJoinLayer(infiltration_ga)

            # Apply the join to the grid layer
            self.grid.addJoin(join_info)

            infils = [x[0] for x in self.gutils.execute(f"""
            SELECT 
                {infil_type} 
            FROM 
                infil_cells_green AS icg
            JOIN
                grid G ON icg.grid_fid = G.fid
            """).fetchall()]
            infils = [x if x is not None else -9999 for x in infils]
            if infils:
                mini = min(infils)
                mini2 = second_smallest(infils)
                maxi = max(infils)
                render_grid(
                    self.grid,
                    True,
                    mini,
                    mini2,
                    maxi,
                    f"infil_{infil_type}"
                )
                set_min_max_elevs(mini, maxi)
                self.lyrs.lyrs_to_repaint = [self.grid]
                self.lyrs.repaint_layers()
                self.render_tb.setText(f"Infiltration - {infil_type}")
        except Exception as e:
            self.uc.show_error("Render of infiltration failed!\n", e)
            self.uc.log_info("Render of infiltration failed!")
            self.lyrs.clear_rubber()
            self.render_tb.setText("")

    def render_infiltration_scs(self, infil_type):
        try:
            if self.gutils.is_table_empty("user_model_boundary"):
                self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
                self.uc.log_info("There is no computational domain! Please digitize it before running tool.")
                self.render_tb.setText("")
                return
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                self.uc.log_info("There is no grid! Please create it before running tool.")
                self.render_tb.setText("")
                return
            if self.gutils.is_table_empty("infil_cells_scs"):
                self.uc.bar_warn("SCS infiltration data is missing. Please schematize it before rendering.")
                self.uc.log_info("SCS infiltration data is missing. Please schematize it before rendering.")
                self.render_tb.setText("")
                return

            infiltration_scs = self.lyrs.data["infil_cells_scs"]["qlyr"]

            join_info = QgsVectorLayerJoinInfo()
            join_info.setJoinFieldName("grid_fid")
            join_info.setTargetFieldName("fid")
            join_info.setJoinLayerId(infiltration_scs.id())
            join_info.setUsingMemoryCache(True)
            join_info.setPrefix("infil_")
            join_info.setJoinLayer(infiltration_scs)

            # Apply the join to the grid layer
            self.grid.addJoin(join_info)

            infils = [x[0] for x in self.gutils.execute(f"""
            SELECT 
                {infil_type} 
            FROM 
                infil_cells_scs AS ics
            JOIN
                grid G ON ics.grid_fid = G.fid
            """).fetchall()]
            infils = [x if x is not None else -9999 for x in infils]
            if infils:
                mini = min(infils)
                mini2 = second_smallest(infils)
                maxi = max(infils)
                render_grid(
                    self.grid,
                    True,
                    mini,
                    mini2,
                    maxi,
                    f"infil_{infil_type}"
                )
                set_min_max_elevs(mini, maxi)
                self.lyrs.lyrs_to_repaint = [self.grid]
                self.lyrs.repaint_layers()
                self.render_tb.setText(f"Infiltration - {infil_type}")
        except Exception as e:
            self.uc.show_error("Render of infiltration failed!\n", e)
            self.uc.log_info("Render of infiltration failed!")
            self.lyrs.clear_rubber()
            self.render_tb.setText("")

    def render_infiltration_horton(self, infil_type):
        try:
            if self.gutils.is_table_empty("user_model_boundary"):
                self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
                self.uc.log_info("There is no computational domain! Please digitize it before running tool.")
                self.render_tb.setText("")
                return
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                self.uc.log_info("There is no grid! Please create it before running tool.")
                self.render_tb.setText("")
                return
            if self.gutils.is_table_empty("infil_cells_horton"):
                self.uc.bar_warn("Horton infiltration data is missing. Please schematize it before rendering.")
                self.uc.log_info("Horton infiltration data is missing. Please schematize it before rendering.")
                self.render_tb.setText("")
                return

            infiltration_horton = self.lyrs.data["infil_cells_horton"]["qlyr"]

            join_info = QgsVectorLayerJoinInfo()
            join_info.setJoinFieldName("grid_fid")
            join_info.setTargetFieldName("fid")
            join_info.setJoinLayerId(infiltration_horton.id())
            join_info.setUsingMemoryCache(True)
            join_info.setPrefix("infil_")
            join_info.setJoinLayer(infiltration_horton)

            # Apply the join to the grid layer
            self.grid.addJoin(join_info)

            infils = [x[0] for x in self.gutils.execute(f"""
            SELECT 
                {infil_type} 
            FROM 
                infil_cells_horton AS ich
            JOIN
                grid G ON ich.grid_fid = G.fid
            """).fetchall()]
            infils = [x if x is not None else -9999 for x in infils]
            if infils:
                mini = min(infils)
                mini2 = second_smallest(infils)
                maxi = max(infils)
                render_grid(
                    self.grid,
                    True,
                    mini,
                    mini2,
                    maxi,
                    f"infil_{infil_type}"
                )
                set_min_max_elevs(mini, maxi)
                self.lyrs.lyrs_to_repaint = [self.grid]
                self.lyrs.repaint_layers()
                self.render_tb.setText(f"Infiltration - {infil_type}")
        except Exception as e:
            self.uc.show_error("Render of infiltration failed!\n", e)
            self.uc.log_info("Render of infiltration failed!")
            self.lyrs.clear_rubber()
            self.render_tb.setText("")

    def render_rainfall(self):
        try:
            if self.gutils.is_table_empty("user_model_boundary"):
                self.uc.bar_warn("There is no computational domain! Please digitize it before running tool.")
                self.uc.log_info("There is no computational domain! Please digitize it before running tool.")
                self.render_tb.setText("")
                return
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                self.uc.log_info("There is no grid! Please create it before running tool.")
                self.render_tb.setText("")
                return
            if self.gutils.is_table_empty("rain_arf_cells"):
                self.uc.bar_warn("Rain ARF data is missing. Please schematize it before rendering.")
                self.uc.log_info("Rain ARF data is missing. Please schematize it before rendering.")
                self.render_tb.setText("")
                return

            rain_arf = self.lyrs.data["rain_arf_cells"]["qlyr"]

            join_info = QgsVectorLayerJoinInfo()
            join_info.setJoinFieldName("grid_fid")
            join_info.setTargetFieldName("fid")
            join_info.setJoinLayerId(rain_arf.id())
            join_info.setUsingMemoryCache(True)
            join_info.setPrefix("rain_")
            join_info.setJoinLayer(rain_arf)

            # Apply the join to the grid layer
            self.grid.addJoin(join_info)

            rains = [x[0] for x in self.gutils.execute(f"""
            SELECT 
                arf
            FROM 
                rain_arf_cells AS rac
            JOIN
                grid G ON rac.grid_fid = G.fid
            """).fetchall()]
            rains = [x if x is not None else -9999 for x in rains]
            if rains:
                mini = min(rains)
                mini2 = second_smallest(rains)
                maxi = max(rains)
                render_grid(
                    self.grid,
                    True,
                    mini,
                    mini2,
                    maxi,
                    f"rain_arf"
                )
                set_min_max_elevs(mini, maxi)
                self.lyrs.lyrs_to_repaint = [self.grid]
                self.lyrs.repaint_layers()
                self.render_tb.setText(f"Rain ARF")
        except Exception as e:
            self.uc.show_error("Render of Rain ARF failed!\n", e)
            self.uc.log_info("Render of Rain ARF failed!")
            self.lyrs.clear_rubber()
            self.render_tb.setText("")

    def plot_grid_rainfall(self, feat):
        si = "inches" if self.gutils.get_cont_par("METRIC") == "0" else "mm"
        qry = "SELECT time_interval, iraindum FROM raincell_data WHERE rrgrid=? ORDER BY time_interval;"
        fid = feat["fid"]
        rainfall = self.gutils.execute(qry, (fid,))
        self.create_plot()
        self.tview.setModel(self.data_model)
        self.data_model.clear()
        self.data_model.setHorizontalHeaderLabels(["Time", "Cumulative rainfall"])
        self.d1, self.d2 = [[], []]
        for row in rainfall:
            items = [QStandardItem("{:.4f}".format(x)) if x is not None else QStandardItem("") for x in row]
            self.data_model.appendRow(items)
            self.d1.append(row[0] if not row[0] is None else float("NaN"))
            self.d2.append(row[1] if not row[1] is None else float("NaN"))
        rc = self.data_model.rowCount()
        if rc < 500:
            for row in range(rc, 500 + 1):
                items = [QStandardItem(x) for x in ("",) * 2]
                self.data_model.appendRow(items)
        self.tview.horizontalHeader().setStretchLastSection(True)
        for col in range(2):
            self.tview.setColumnWidth(col, 100)
        for i in range(self.data_model.rowCount()):
            self.tview.setRowHeight(i, 20)
        self.plot.plot.setTitle("GRID FID: {}".format(fid))
        self.plot.plot.setLabel("bottom", text="Time (minutes)")
        self.plot.plot.setLabel("left", text="Rainfall ({})".format(si))
        self.update_plot()

    def create_plot(self):
        self.plot.clear()
        if self.plot.plot.legend is not None:
            plot_scene = self.plot.plot.legend.scene()
            if plot_scene is not None:
                plot_scene.removeItem(self.plot.plot.legend)
        self.plot.plot.addLegend()

        self.plot_item_name = "Grid realtime rainfall"
        self.plot.add_item(self.plot_item_name, [self.d1, self.d2], col=QColor("#0018d4"))

    def update_plot(self):
        if not self.plot_item_name:
            return
        self.d1, self.d2 = [[], []]
        for i in range(self.data_model.rowCount()):
            self.d1.append(m_fdata(self.data_model, i, 0))
            self.d2.append(m_fdata(self.data_model, i, 1))
        self.plot.update_item(self.plot_item_name, [self.d1, self.d2])

    def find_cell(self, cell=None):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.gutils.is_table_empty("grid"):
                self.uc.bar_warn("There is no grid! Please create it before running tool.")
                return
            grid = self.lyrs.data["grid"]["qlyr"]
            if grid is not None:
                if grid:
                    if not cell:
                        cell = self.idEdit.text()
                    else:
                        cell = cell
                        self.idEdit.setText(str(cell))
                    if cell != "":
                        cell = int(cell)
                        n_cells = number_of_elements(self.gutils, grid)
                        if n_cells > 0 and cell > 0:
                            if cell <= n_cells:
                                self.lyrs.show_feat_rubber(grid.id(), cell, QColor(Qt.yellow))
                                feat = next(grid.getFeatures(QgsFeatureRequest(cell)))
                                x, y = feat.geometry().centroid().asPoint()
                                center_canvas(self.iface, x, y)
                                zoom(self.iface, 0.4)
                                self.mannEdit.setText(str(feat["n_value"]))
                                self.elevEdit.setText(str(feat["elevation"]).strip())
                                self.cellEdit.setText(str(self.gutils.get_cont_par("CELLSIZE")))
                                self.n_cells = n_cells
                                self.n_cells_lbl.setText("Number of cells: " + "{:,}".format(n_cells) + "   ")
                            else:
                                self.uc.bar_warn("Cell " + str(cell) + " not found.")
                                self.lyrs.clear_rubber()
                        else:
                            self.uc.bar_warn("Cell " + str(cell) + " not found.")
                            self.lyrs.clear_rubber()
                    else:
                        self.uc.bar_warn("Cell " + str(cell) + " not found.")
                        self.lyrs.clear_rubber()

        except Exception:
            self.uc.bar_warn("Cell is not valid.")
            self.lyrs.clear_rubber()
            pass

        # except ValueError:
        #     self.uc.bar_warn("Cell " + str(cell) + " is not valid.")
        #     self.lyrs.clear_rubber()
        #     pass
        finally:
            QApplication.restoreOverrideCursor()
