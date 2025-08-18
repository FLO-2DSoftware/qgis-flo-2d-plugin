# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import datetime, timedelta
import os
from math import ceil
from pathlib import Path

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QFileDialog
from qgis._core import QgsWkbTypes

from ..flo2d_tools.grid_tools import poly2grid
# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version


from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from .ui_utils import load_ui

uiDialog, qtBaseClass = load_ui("raincellraw")


class SamplingRaincellRawDialog(qtBaseClass, uiDialog):
    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.con = con
        self.iface = iface
        self.gutils = GeoPackageUtils(con, iface)
        self.lyrs = lyrs
        self.setupUi(self)
        self.uc = UserCommunication(iface, "FLO-2D")
        self.setup_src_layer_cbo()
        self.grid_lyr = self.lyrs.data["grid"]["qlyr"]
        self.current_lyr = None
        self.srcData = None

        # Connections
        self.srcLayerCbo.currentIndexChanged.connect(self.populate_src_field_cbo)
        self.browseSrcBtn.clicked.connect(self.browse_src_data)

        self.start_date_dte.setDate(datetime.now().date())
        self.end_date_dte.setDate(datetime.now().date())

    def setup_src_layer_cbo(self):
        """
        Filter src layer combo for polygons and connect field cbo.
        """
        self.srcLayerCbo.addItem("", None)
        poly_lyrs = self.lyrs.list_group_vlayers()
        for l in poly_lyrs:
            if l.geometryType() == QgsWkbTypes.PolygonGeometry:
                l.reload()  # force layer reload because sometimes featureCount does not work
                if l.featureCount() > 0:
                    self.srcLayerCbo.addItem(l.name(), l.dataProvider().dataSourceUri())
            else:
                pass

    def populate_src_field_cbo(self, idx):
        """
        Function to populate source field combo based on selected layer.
        """
        if idx == 0:
            return
        uri = self.srcLayerCbo.itemData(idx)
        lyr_id = self.lyrs.layer_exists_in_group(uri)
        self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()
        self.srcFieldCbo.setLayer(self.current_lyr)

    def browse_src_data(self):
        """
        Function to browse source data file.
        """
        s = QSettings()
        last_dir = s.value("FLO-2D/lasGdsDir", "")
        self.srcData, __ = QFileDialog.getOpenFileName(
            None,
            "Choose NEXRAD data...",
            directory=last_dir,
            filter="CSV files (*.csv)")
        if not self.srcData:
            return

        self.srcDataLe.setText(self.srcData)

    def process_raincellraw(self):
        """
        Function to process raincellraw data.
        """
        if not self.current_lyr:
            self.uc.bar_error("Please select a valid source layer.")
            self.uc.log_info("Please select a valid source layer.")
            return False

        if not self.srcData:
            self.uc.bar_error("Please select a valid source data file.")
            self.uc.log_info("Please select a valid source layer.")
            return False

        src_field = self.srcFieldCbo.currentField()
        if not src_field:
            self.uc.bar_error("Please select a valid source field.")
            self.uc.log_info("Please select a valid source layer.")
            return False

        self.gutils.clear_tables("raincell", "raincellraw", "flo2d_raincell")

        # Convert grid layer to correct CRS
        current_lyr_crs = self.current_lyr.crs()
        grid_lyr_crs = self.grid_lyr.crs()
        if current_lyr_crs.authid() != grid_lyr_crs.authid():
            reprojected = self.lyrs.reproject_simple(self.current_lyr, grid_lyr_crs, sink="memory:")
            if not reprojected:
                self.uc.bar_error("Error reprojecting source layer.")
                self.uc.log_info("Error reprojecting source layer.")
                return False
            self.current_lyr = reprojected

        # Intersect the grid and save to flo2d_raincell table
        qry = """INSERT INTO flo2d_raincell (nxrdgd, iraindum) VALUES (?, ?);"""

        # Centroids
        cellSize = float(self.gutils.get_cont_par("CELLSIZE"))

        self.gutils.con.executemany(
            qry,
            poly2grid(cellSize, self.grid_lyr, self.current_lyr, None, True, False, False, 1, src_field),
        )
        self.gutils.con.commit()

        # Parse the nexrad data and insert into raincellraw table - Check for the zeros
        # format_string = "%Y-%m-%d %H:%M:%S"
        data_min = self.start_date_dte.dateTime().toPyDateTime()
        data_max = self.end_date_dte.dateTime().toPyDateTime()


        fill_zeros = self.fill_zeros_chbox.isChecked()

        # Fill the raincellraw table
        raincellraw_data, rainintime = self.process_nexrad_data(
            self.srcData,
            fill_zeros=fill_zeros,
            agg="sum",
            data_min=data_min,
            data_max=data_max)

        intersected_nexrad_grids = self.gutils.execute("""SELECT DISTINCT nxrdgd FROM flo2d_raincell;""").fetchall()
        for row in intersected_nexrad_grids:
            nxrdgd = row[0]
            self.uc.log_info(f"Processing NEXRAD grid {nxrdgd}...")
            filtered_data = [r for r in raincellraw_data if r["POLYGON"] == nxrdgd]
            insert_qry = """INSERT INTO raincellraw (nxrdgd, r_time, rrgrid) VALUES (?, ?, ?);"""
            to_insert = [(r["POLYGON"], r["TIME_HOURS"], r["VALUE"]) for r in filtered_data]
            self.gutils.con.executemany(insert_qry, to_insert)
            self.gutils.con.commit()

        self.uc.show_warn("Complete.")

        # Fill the raincell table
        duration_minutes = (data_max - data_min).total_seconds() / 60
        iriters = ceil(duration_minutes / rainintime) + 1
        insert_qry = """INSERT INTO raincell (rainintime, irinters) VALUES (?, ?);"""
        self.gutils.con.execute(insert_qry, (rainintime, iriters))

    def process_nexrad_data(self, file_path, data_min=None, data_max=None,
                            fill_zeros=False, agg="sum"):
        """
        Returns (rows, interval_minutes)
          rows: list of dicts with keys POLYGON, TIME_HOURS, VALUE
        """

        file_path = Path(file_path)
        text = file_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        header_idx = None
        interval_minutes = None

        # 1) find header (FIRST occurrence)
        for i, line in enumerate(lines):
            up = line.upper()
            if "POLYGON" in up and "DATE" in up and "TIME" in up:
                header_idx = i
                break
        if header_idx is None:
            return False

        data_start = header_idx + 2

        #    data_map: poly -> { dt -> [values] }
        data_map = {}
        polygons = set()
        parsed_min = None
        parsed_max = None

        for raw in lines[data_start:]:
            s = raw.strip()
            if not s or s.startswith("..."):
                continue
            parts = [p.strip() for p in raw.split(",")]
            if len(parts) < 4:
                continue

            # POLYGON must be integer
            try:
                poly = int(parts[0])
            except Exception:
                continue

            ds = parts[1]
            ts = parts[2].strip("'").strip('"')
            vs = parts[3]

            # capture interval once if present
            if len(parts) > 4:
                try:
                    freq = int(parts[4])
                    if interval_minutes is None:
                        interval_minutes = freq
                except Exception:
                    pass

            try:
                ddt = datetime.strptime(ds, "%m/%d/%Y")
                ts = ts.zfill(4)
                hh, mm = int(ts[:2]), int(ts[2:])
                ddt = ddt.replace(hour=hh, minute=mm, second=0, microsecond=0)
                val = float(vs)
            except Exception:
                continue

            polygons.add(poly)
            data_map.setdefault(poly, {}).setdefault(ddt, []).append(val)

            parsed_min = ddt if parsed_min is None or ddt < parsed_min else parsed_min
            parsed_max = ddt if parsed_max is None or ddt > parsed_max else parsed_max

        if interval_minutes is None:
            interval_minutes = 15  # sensible default

        start_dt = data_min if data_min is not None else parsed_min
        end_dt = data_max if data_max is not None else parsed_max

        def aggregate(vals, mode):
            if not vals: return 0.0
            if mode == "sum":  return float(sum(vals))
            if mode == "max":  return float(max(vals))
            if mode == "last": return float(vals[-1])
            return float(sum(vals))  # default

        rows = []
        for poly in sorted(polygons):
            series = data_map.get(poly, {})  # {dt: [vals]}
            if not series:
                continue

            origin_dt = start_dt

            # Map observed datetimes to a slot index (pure integers -> no float drift)
            slot_vals = {}  # idx -> aggregated value
            if fill_zeros:
                for dt, vals in series.items():
                    total_min = int((dt - origin_dt).total_seconds() // 60)
                    # nearest slot index (no banker's rounding)
                    idx = (total_min * 2 + interval_minutes) // (2 * interval_minutes)
                    slot_vals[idx] = slot_vals.get(idx, 0.0) + aggregate(vals, agg)
            else:
                # no-fill path (your current behavior, but keep the snapping for ORDER only)
                pass

            if fill_zeros:
                # Build complete grid of slot indices across the requested window
                end_min = int((end_dt - origin_dt).total_seconds() // 60)
                max_idx = ceil(end_min / interval_minutes)  # inclusive ceiling
                for idx in range(0, max_idx + 1):
                    time_hours = idx * (interval_minutes / 60.0)  # e.g., 0.25 for 15-min
                    value = slot_vals.get(idx, 0.0)
                    rows.append({
                        "POLYGON": poly,
                        "TIME_HOURS": f"{time_hours:.2f}",
                        "VALUE": float(value),
                    })
            else:
                # non-fill path
                out_by_idx = defaultdict(list)  # idx -> list of values that snap to this slot

                for dt, vals in series.items():
                    total_min = int((dt - origin_dt).total_seconds() // 60)
                    # snap to nearest slot (integer math; no banker's rounding)
                    idx = (total_min * 2 + interval_minutes) // (2 * interval_minutes)
                    out_by_idx[idx].extend(vals)  # keep all values that hit this slot

                # emit one aggregated row per slot, ordered
                for idx in sorted(out_by_idx.keys()):
                    time_hours = idx * (interval_minutes / 60.0)  # 0, 0.25, 0.50, 0.75, ...
                    rows.append({
                        "POLYGON": poly,
                        "TIME_HOURS": f"{time_hours:.2f}",
                        "VALUE": aggregate(out_by_idx[idx], agg),  # "sum" | "max" | "last"
                    })

        return rows, interval_minutes
