# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
from collections import OrderedDict
from math import isnan, sqrt

from qgis.core import (
    QgsCsException,
    QgsFeatureRequest,
    QgsPointXY,
    QgsRaster,
    QgsRectangle,
)

from .errors import Flo2dError
from .geopackage_utils import GeoPackageUtils
from .utils import is_number


class CrossSection(GeoPackageUtils):
    """
    Cross section object representation.
    """

    columns = [
        "id",
        "fid",
        "seg_fid",
        "nr_in_seg",
        "rbankgrid",
        "fcn",
        "xlen",
        "type",
        "notes",
        "user_xs_fid",
        "interpolated",
        "geom",
    ]

    def __init__(self, fid, con, iface):
        super(CrossSection, self).__init__(con, iface)
        self.fid = fid
        self.row = None
        self.type = None
        self.chan = None
        self.chan_tab = None
        self.xsec = None
        self.chan_x_tabs = {"N": "chan_n", "R": "chan_r", "T": "chan_t", "V": "chan_v"}

    def get_row(self, by_id=False):
        ident = "id" if by_id else "fid"
        qry = "SELECT * FROM chan_elems WHERE {} = ?;".format(ident)
        values = [x if x is not None else "" for x in self.execute(qry, (self.fid,)).fetchone()]
        self.row = OrderedDict(list(zip(self.columns, values)))
        self.fid = self.row["fid"]
        self.xlen = self.row["xlen"]
        self.type = self.row["type"]
        return self.row

    def get_profile_data(self):
        self.profile_data = {}
        self.get_row()  # Gets values of 'fid', 'xlen', and 'type' of
        self.get_chan_table()
        if not self.type == "N":
            par_to_check = ["bankell", "bankelr", "fcd"]
            for par in par_to_check:
                if not is_number(self.chan_tab[par]):
                    msg = "WARNING 060319.1820: Missing {} data in user cross section {}".format(
                        par, self.row["user_xs_fid"]
                    )
                    self.uc.show_warn(msg)
                    raise Flo2dError
            self.profile_data["lbank_elev"] = self.chan_tab["bankell"]
            self.profile_data["rbank_elev"] = self.chan_tab["bankelr"]
            self.profile_data["fcd"] = self.chan_tab["fcd"]
            self.profile_data["bed_elev"] = (
                min(self.chan_tab["bankell"], self.chan_tab["bankelr"]) - self.chan_tab["fcd"]
            )
        else:
            self.get_xsec_data()
            if not self.xsec:
                return {}
            self.profile_data["lbank_elev"] = self.xsec[0][1]
            self.profile_data["rbank_elev"] = self.xsec[-1][1]
            min_bed_elev = 9999999
            for row in self.xsec:
                min_bed_elev = min(min_bed_elev, row[1])
            self.profile_data["bed_elev"] = min_bed_elev
            self.profile_data["fcd"] = min(self.xsec[0][1], self.xsec[-1][1]) - min_bed_elev
        return self.profile_data

    def set_profile_data(self):
        if not self.profile_data:
            return
        if not self.type == "N":
            tab = self.chan_x_tabs[self.type]
            qry = """UPDATE {0} SET
                    bankell = ?,
                    bankelr = ?,
                    fcd = ?
                WHERE elem_fid = ?;""".format(
                tab
            )
            data = (
                self.profile_data["lbank_elev"],
                self.profile_data["rbank_elev"],
                self.profile_data["fcd"],
                self.fid,
            )
            self.execute(qry, data)

    def get_chan_segment(self):
        if self.row is not None:
            pass
        else:
            return
        seg_fid = self.row["seg_fid"]
        args = self.table_info("chan", only_columns=True)
        qry = "SELECT * FROM chan WHERE fid = ?;"
        values = [x if x is not None else "" for x in self.execute(qry, (seg_fid,)).fetchone()]
        self.chan = OrderedDict(list(zip(args, values)))
        return self.chan

    def get_chan_table(self):
        if self.row is not None:
            pass
        else:
            return
        tab = self.chan_x_tabs[self.type]
        args = self.table_info(tab, only_columns=True)
        qry = "SELECT * FROM {0} WHERE elem_fid = ?;".format(tab)
        values = [x if x is not None else "" for x in self.execute(qry, (self.fid,)).fetchone()]
        self.chan_tab = OrderedDict(list(zip(args, values)))
        return self.chan_tab

    def get_xsec_data(self):
        if self.row is not None and self.type == "N":
            pass
        else:
            return None
        fid = self.chan_tab["fid"]
        qry = "SELECT xi, yi FROM xsec_n_data WHERE chan_n_nxsecnum = ? ORDER BY fid;"
        self.xsec = self.execute(qry, (fid,)).fetchall()
        return self.xsec

    def shift_nxsec(self, dh):
        if self.row is not None and self.type == "N":
            pass
        else:
            return None
        fid = self.chan_tab["fid"]
        qry = "UPDATE xsec_n_data SET yi = yi + ? WHERE chan_n_nxsecnum = ?;"
        self.execute(
            qry,
            (
                dh,
                fid,
            ),
        )


class UserCrossSection(GeoPackageUtils):
    """
    Cross section object representation.
    """

    columns = ["fid", "fcn", "type", "name", "notes"]

    def __init__(self, fid, con, iface):
        super(UserCrossSection, self).__init__(con, iface)
        self.row = None
        self.fid = fid
        self.fcn = None
        self.type = None
        self.name = None
        self.chan_x_row = None
        self.xsec = None
        self.chan_x_tabs = {
            "N": "user_chan_n",
            "R": "user_chan_r",
            "T": "user_chan_t",
            "V": "user_chan_v",
        }

    def get_row(self):
        qry = "SELECT * FROM user_xsections WHERE fid = ?;"
        values = [x if x is not None else "" for x in self.execute(qry, (self.fid,)).fetchone()]
        self.row = OrderedDict(list(zip(self.columns, values)))
        self.type = self.row["type"]
        self.name = self.row["name"]
        return self.row

    def get_chan_x_row(self):
        if self.row is not None:
            pass
        else:
            return
        tab = self.chan_x_tabs[self.type]
        qry = "SELECT * FROM {0} WHERE user_xs_fid = ?;".format(tab)
        chan_row = self.execute(qry, (self.fid,)).fetchone()
        if not chan_row:
            # create new row
            chan_row = self.add_chan_x_row(fetch=True)
        values = [x if x is not None else "" for x in chan_row]
        args = self.table_info(tab, only_columns=True)
        self.chan_x_row = OrderedDict(list(zip(args, values)))
        return self.chan_x_row

    def add_chan_x_row(self, fetch=False):
        # add a new row in user_chan_(x) tables
        tab = self.chan_x_tabs[self.type]
        qry = "INSERT INTO {0} (user_xs_fid) VALUES (?);".format(tab)
        self.execute(qry, (self.fid,))
        if fetch:
            qry = "SELECT * FROM {0} WHERE user_xs_fid = ?;".format(tab)
            return self.execute(qry, (self.fid,)).fetchone()

    def get_nxsecnum(self):
        nxsecnum = self.execute("SELECT nxsecnum FROM user_chan_n WHERE user_xs_fid = ?", (self.fid,)).fetchone()[0]
        return nxsecnum

    def get_chan_natural_data(self):
        if self.row is not None and self.type == "N":
            pass
        else:
            return None
        qry = "SELECT xi, yi FROM user_xsec_n_data WHERE chan_n_nxsecnum = ? ORDER BY xi;"
        self.xiyi = self.execute(qry, (self.fid,)).fetchall()
        if not self.xiyi:
            self.xiyi = self.add_chan_natural_data(fetch=True)
        return self.xiyi

    def add_chan_natural_data(self, fetch=False):
        self.set_nxsecnum()
        qry = """INSERT INTO user_xsec_n_data (chan_n_nxsecnum, xi, yi)
                VALUES ({0}, 0, 1), ({0}, 1, 0), ({0}, 2, 1)""".format(
            self.fid
        )
        self.execute(qry)
        if fetch:
            qry = "SELECT xi, yi FROM user_xsec_n_data WHERE chan_n_nxsecnum = ? ORDER BY xi;"
            self.xiyi = self.execute(qry, (self.fid,)).fetchall()
            return self.xiyi

    def set_chan_data(self, data):
        table = self.chan_x_tabs[self.type]
        qry = """DELETE FROM {0} WHERE user_xs_fid = ?""".format(table)
        self.execute(qry, (self.fid,))
        cols = list(self.table_info(table, only_columns=True))[1:]
        cols_t = ", ".join([c for c in cols])
        vals = []
        for v in data:
            if not isnan(v):
                vals.append(v)
            else:
                vals.append("NULL")
        vals_t = ", ".join([str(v) for v in vals])
        qry = """INSERT INTO {0} ({1}) VALUES ({2}, {3});""".format(table, cols_t, self.fid, vals_t)
        self.execute(qry)

    def clear_unused_user_nxsec_data(self):
        qry = """DELETE FROM user_xsec_n_data WHERE chan_n_nxsecnum NOT IN
            (SELECT nxsecnum FROM user_chan_n);"""
        self.execute(qry)

    def set_chan_natural_data(self, data):
        self.get_chan_x_row()
        qry = """DELETE FROM user_xsec_n_data WHERE chan_n_nxsecnum = ?;"""
        self.execute(qry, (self.fid,))
        qry = """INSERT INTO user_xsec_n_data (chan_n_nxsecnum, xi, yi) VALUES (?, ?, ?);"""
        self.execute_many(qry, data)
        self.set_nxsecnum()
        self.clear_unused_user_nxsec_data()

    def set_type(self, typ):
        qry = """UPDATE user_xsections SET type = ? WHERE fid = ?;"""
        self.execute(
            qry,
            (
                typ,
                self.fid,
            ),
        )
        self.clear_unused_user_chan_x_rows()

    def set_nxsecnum(self):
        # qry_xsecnum = '''UPDATE user_chan_n SET nxsecnum = fid, xsecname = 'Cross section ' || cast(fid as text);'''
        qry_xsecnum = """UPDATE user_chan_n SET nxsecnum=?, xsecname=? WHERE user_xs_fid=?;"""
        self.execute(qry_xsecnum, (self.fid, self.name, self.fid))

    def set_n(self, n):
        qry = """UPDATE user_xsections SET fcn = ? WHERE fid = ?;"""
        self.execute(
            qry,
            (
                n,
                self.fid,
            ),
        )

    def set_name(self, name=None):
        if not name:
            name = self.name
        qry = """UPDATE user_xsections SET name = ? WHERE fid = ?;"""
        self.execute(
            qry,
            (
                name,
                self.fid,
            ),
        )

    def clear_unused_user_chan_x_rows(self):
        qry_r = "DELETE FROM user_chan_r WHERE user_xs_fid NOT IN (SELECT fid FROM user_xsections WHERE type = 'R');"
        qry_t = "DELETE FROM user_chan_t WHERE user_xs_fid NOT IN (SELECT fid FROM user_xsections WHERE type = 'T');"
        qry_v = "DELETE FROM user_chan_v WHERE user_xs_fid NOT IN (SELECT fid FROM user_xsections WHERE type = 'V');"
        qry_n = "DELETE FROM user_chan_n WHERE user_xs_fid NOT IN (SELECT fid FROM user_xsections WHERE type = 'N');"
        self.execute(qry_r)
        self.execute(qry_t)
        self.execute(qry_v)
        self.execute(qry_n)

    def sample_elevation_from_raster_layer(self, raster_layer, cross_section_line, transform):
        if raster_layer is None:
            return
        self.get_row()
        if self.type == "N":
            xiyi = []
            distance = 0
            for i in range(len(cross_section_line) - 1):
                source_point_1 = cross_section_line[i]
                source_point_2 = cross_section_line[i + 1]
                try:
                    layer_point1 = transform.transform(source_point_1)
                    layer_point2 = transform.transform(source_point_2)
                except QgsCsException:
                    layer_point1 = source_point_1
                    layer_point2 = source_point_2

                x1 = layer_point1.x()
                y1 = layer_point1.y()
                x2 = layer_point2.x()
                y2 = layer_point2.y()

                length_segment = sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                # calculate points count on this segment
                if abs(x2 - x1) >= abs(y2 - y1):
                    point_count = int(abs(x2 - x1) / raster_layer.rasterUnitsPerPixelX()) - 1
                else:
                    point_count = int(abs(y2 - y1) / raster_layer.rasterUnitsPerPixelY()) - 1

                if point_count < 0:
                    point_count = 0

                step_x = (x2 - x1) / (point_count + 1)
                step_y = (y2 - y1) / (point_count + 1)

                result = raster_layer.dataProvider().identify(layer_point1, QgsRaster.IdentifyFormatValue)

                if result.isValid():
                    value = result.results()
                    xiyi.append((self.fid, round(distance, 2), round(value[1], 2)))

                for step in range(1, point_count + 1):
                    x = x1 + step_x * step
                    y = y1 + step_y * step

                    result = raster_layer.dataProvider().identify(QgsPointXY(x, y), QgsRaster.IdentifyFormatValue)

                    if result.isValid():
                        value = result.results()
                        xiyi.append(
                            (
                                self.fid,
                                round(distance + sqrt((x - x1) ** 2 + (y - y1) ** 2), 2),
                                round(value[1], 2),
                            )
                        )

                distance = distance + length_segment

            self.set_chan_natural_data(xiyi)

    def sample_bank_elevation_from_raster_layer(self, raster_layer, cross_section_line, transform):
        if raster_layer is None:
            return
        self.get_row()
        if self.type == "N":
            return

        source_point_1 = cross_section_line[0]
        source_point_2 = cross_section_line[-1]
        try:
            layer_point1 = transform.transform(source_point_1)
            layer_point2 = transform.transform(source_point_2)
        except QgsCsException:
            layer_point1 = source_point_1
            layer_point2 = source_point_2

        result1 = raster_layer.dataProvider().identify(layer_point1, QgsRaster.IdentifyFormatValue)
        result2 = raster_layer.dataProvider().identify(layer_point2, QgsRaster.IdentifyFormatValue)

        tab = self.chan_x_tabs[self.type]
        if result1.isValid():
            value = result1.results()
            qry = """UPDATE {} SET bankell = ? WHERE user_xs_fid = ?;""".format(tab)
            self.execute(
                qry,
                (
                    round(value[1], 2),
                    self.fid,
                ),
            )

        if result2.isValid():
            value = result2.results()
            qry = """UPDATE {} SET bankelr = ? WHERE user_xs_fid = ?;""".format(tab)
            self.execute(
                qry,
                (
                    round(value[1], 2),
                    self.fid,
                ),
            )

    def sample_bank_elevation_from_grid(self, cross_section_line, grid_layer):
        self.get_row()
        if self.type == "N":
            return

        point_1 = cross_section_line[0]
        point_2 = cross_section_line[-1]

        request = QgsFeatureRequest()
        rect = QgsRectangle(point_1, point_1)
        request.setFilterRect(rect)
        request.setFlags(QgsFeatureRequest.ExactIntersect)
        fit1 = grid_layer.getFeatures(request)

        rect = QgsRectangle(point_2, point_2)
        request.setFilterRect(rect)
        fit2 = grid_layer.getFeatures(request)

        tab = self.chan_x_tabs[self.type]

        try:
            elem1 = next(fit1)
            qry = """UPDATE {} SET bankell = ? WHERE user_xs_fid = ?;""".format(tab)
            roundedValue = round(elem1.attribute("elevation"), 2)
            self.execute(
                qry,
                (
                    roundedValue,
                    self.fid,
                ),
            )
        except StopIteration:
            pass
        try:
            elem2 = next(fit2)
            qry = """UPDATE {} SET bankelr = ? WHERE user_xs_fid = ?;""".format(tab)
            roundedValue = round(elem2.attribute("elevation"), 2)
            self.execute(
                qry,
                (
                    roundedValue,
                    self.fid,
                ),
            )
        except StopIteration:
            pass


class ChannelSegment(GeoPackageUtils):
    """
    Channel segment object representation.
    """

    columns = [
        "fid",
        "name",
        "depinitial",
        "froudc",
        "roughadj",
        "isedn",
        "notes",
        "user_lbank_fid",
        "rank",
        "geom",
    ]

    def __init__(self, fid, con, iface):
        super(ChannelSegment, self).__init__(con, iface)
        self.con = con
        self.iface = iface
        self.row = None
        self.fid = fid
        self.name = None
        self.depinitial = None
        self.froudc = None
        self.roughadj = None
        self.isedn = None
        self.notes = None
        self.user_lbank_fid = None
        self.rank = None

    def get_row(self):
        qry = "SELECT * FROM chan WHERE fid = ?;"
        values = [x if x is not None else "" for x in self.execute(qry, (self.fid,)).fetchone()]
        self.row = OrderedDict(list(zip(self.columns, values)))
        self.name = self.row["name"]
        self.depinitial = self.row["depinitial"]
        self.froudc = self.row["froudc"]
        self.roughadj = self.row["roughadj"]
        self.isedn = self.row["isedn"]
        self.notes = self.row["notes"]
        self.user_lbank_fid = self.row["user_lbank_fid"]
        self.rank = self.row["rank"]
        return self.row

    def get_profiles(self, sta_start=0):
        # Gets all features of cross sections associated with the selected channel segment,
        # identified in chan_elems by ´seg_fid'.
        self.profiles = OrderedDict()
        qry = "SELECT * FROM chan_elems WHERE seg_fid = ? ORDER BY nr_in_seg;"
        rows = self.execute(qry, (self.fid,)).fetchall()  # self.fid is the channel segment fid.
        # 'rows' stores a list of all chan_elems features values of
        # the selected channel segment.
        self.profiles = OrderedDict()  # Dictionary of dictionaries keyed by ´lbank_grid'. Example value:
        # (1067, {'bed_elev': 4711.2, 'station': 0, 'fcd': 4.800000000000182, 'lbank_elev': 4717.1, 'rbank_elev': 4716.0})
        sta = sta_start
        for row in rows:
            lbank_grid = row[1]
            xs = CrossSection(lbank_grid, self.con, self.iface)
            try:
                self.profiles[lbank_grid] = xs.get_profile_data()
            except Flo2dError:
                return False
            self.profiles[lbank_grid]["station"] = sta
            self.profiles[lbank_grid]["water"] = row[11]
            self.profiles[lbank_grid]["peak"] = row[12]
            sta += xs.xlen
            del xs
        return True

    def interpolate_bed(self):
        cols = [
            "id",
            "fid",
            "seg_fid",
            "up_fid",
            "lo_fid",
            "up_lo_dist_left",
            "up_lo_dist_right",
            "up_dist_left",
            "up_dist_right",
        ]
        qry = "SELECT * FROM chan_elems_interp ORDER BY seg_fid, up_fid, up_dist_left;"
        rows = self.execute(qry).fetchall()
        if not rows:
            return False, "Interpolation failed! 'chan_elems_interp' table is empty."
        for row in rows:
            values = [x if x is not None else "" for x in row]
            ipars = OrderedDict(list(zip(cols, values)))

            if not ipars["lo_fid"]:
                # no lower base xsection
                continue

            base_len = 0.5 * (ipars["up_lo_dist_left"] + ipars["up_lo_dist_right"])
            dist_left = ipars["up_dist_left"]
            dist_right = ipars["up_dist_right"]
            if dist_right < 0:  # case where there is no user defined right bank
                dist_right = dist_left
            dist = 0.5 * (dist_left + dist_right)
            icoef = dist / base_len
            xsi = CrossSection(ipars["fid"], self.con, self.iface)
            xsi.get_row()

            xsup = CrossSection(ipars["up_fid"], self.con, self.iface)
            xsup.get_row()

            xslo = CrossSection(ipars["lo_fid"], self.con, self.iface)
            xslo.get_row()

            if not xsup.type == "N":
                # parametric cross-section - adjust banks elev and depth
                try:
                    xsi.get_profile_data()
                    xsup.get_profile_data()
                    xslo.get_profile_data()
                    d_lbank_elev = xslo.profile_data["lbank_elev"] - xsup.profile_data["lbank_elev"]
                    d_rbank_elev = xslo.profile_data["rbank_elev"] - xsup.profile_data["rbank_elev"]
                    d_fcd = xslo.profile_data["fcd"] - xsup.profile_data["fcd"]
                    xsi.profile_data["lbank_elev"] = round(xsup.profile_data["lbank_elev"] + icoef * d_lbank_elev, 3)
                    xsi.profile_data["rbank_elev"] = round(xsup.profile_data["rbank_elev"] + icoef * d_rbank_elev, 3)
                    xsi.profile_data["fcd"] = xsup.profile_data["fcd"] + icoef * d_fcd
                    xsi.set_profile_data()
                except Flo2dError as e:
                    return False, repr(e)
            else:
                # this is natural cross-section
                try:
                    xsi.get_profile_data()
                    xsup.get_profile_data()
                    xslo.get_profile_data()
                    d_bed = xslo.profile_data["bed_elev"] - xsup.profile_data["bed_elev"]
                    dh = icoef * d_bed
                    xsi.shift_nxsec(round(dh, 3))
                except Flo2dError as e:
                    return False, repr(e)
                except KeyError:
                    msg = "Interpolation failed on cross sections with 'fid': {}!".format(xsi.row["user_xs_fid"])
                    return False, msg

        return True, "Interpolation successful!"


class Inflow(GeoPackageUtils):
    """
    Inflow object representation.
    """

    columns = [
        "fid",
        "name",
        "time_series_fid",
        "ident",
        "inoutfc",
        "note",
        "geom_type",
        "bc_fid",
    ]

    def __init__(self, fid, con, iface):
        super(Inflow, self).__init__(con, iface)
        self.row = None
        self.fid = fid
        self.name = None
        self.time_series_fid = None
        self.ident = None
        self.inoutfc = None
        self.geom_type = None
        self.bc_fid = None
        self.time_series_data = None

    def add_row(self):
        data = (self.name, self.time_series_fid, self.ident, self.inoutfc)
        qry = "INSERT INTO inflow (name, time_series_fid, ident, inoutfc) VALUES (?, ?, ?, ?);"
        self.fid = self.execute(qry, data, get_rowid=True)

    def get_row(self):
        qry = "SELECT * FROM inflow WHERE fid = ?;"
        values = [x if x is not None else "" for x in self.execute(qry, (self.fid,)).fetchone()]
        self.row = OrderedDict(list(zip(self.columns, values)))
        self.name = self.row["name"]
        self.time_series_fid = self.row["time_series_fid"]
        self.ident = self.row["ident"]
        self.inoutfc = self.row["inoutfc"]
        self.geom_type = self.row["geom_type"]
        self.bc_fid = self.row["bc_fid"]
        return self.row

    def set_row(self):
        data = (self.name, self.time_series_fid, self.ident, self.inoutfc, self.fid)
        qry = "UPDATE inflow SET name=?, time_series_fid=?, ident=?, inoutfc=? WHERE fid=?"
        self.execute(qry, data)

    def del_row(self):
        # first try to delete the bc from user layer
        if self.geom_type and self.bc_fid:
            qry = """DELETE FROM user_bc_{}s WHERE fid=? AND type='inflow';""".format(self.geom_type)
            self.execute(qry, (self.bc_fid,))
            # there is a trigger updating inflow table when the user bc layer is changed
            # this is for inflow rows without geometry
        qry = "DELETE FROM inflow WHERE fid=?"
        self.execute(qry, (self.fid,))
        qry = "DELETE FROM inflow_cells WHERE inflow_fid=?"
        self.execute(qry, (self.fid,))

    def add_time_series(self, name=None, fetch=False):
        qry = "INSERT INTO inflow_time_series (name) VALUES (?);"
        rowid = self.execute(qry, (name,), get_rowid=True)
        qry = """UPDATE inflow SET time_series_fid = ? WHERE fid = ?"""
        self.execute(qry, (rowid, self.fid))
        self.time_series_fid = rowid
        if fetch:
            return self.get_time_series()

    def get_time_series(self):
        qry = "SELECT fid, name FROM inflow_time_series ORDER BY fid;"
        self.time_series = self.execute(qry).fetchall()
        if not self.time_series:
            self.time_series = self.add_time_series(fetch=True)
        return self.time_series

    def get_data_name(self, fid=None):
        qry = "SELECT name FROM inflow_time_series WHERE fid = ?;"
        if not fid and self.time_series_fid:
            fid = self.time_series_fid
        elif fid:
            return self.execute(qry, (fid,))
        else:
            return None

    def add_time_series_data(self, ts_fid, rows=5, fetch=False):
        """
        Add new rows to inflow_time_series_data for a given ts_fid.
        """
        qry = "INSERT INTO inflow_time_series_data (series_fid, time, value) VALUES (?, 0, 0);"
        self.execute_many(qry, ([ts_fid],) * rows)
        if fetch:
            return self.get_time_series_data()

    def get_time_series_data(self):
        if not self.time_series_fid:
            return
        qry = "SELECT time, value, value2 FROM inflow_time_series_data WHERE series_fid = ? ORDER BY time;"
        self.time_series_data = self.execute(qry, (self.time_series_fid,)).fetchall()
        if not self.time_series_data:
            # add a new time series
            self.time_series_data = self.add_time_series_data(self.time_series_fid, fetch=True)
        return self.time_series_data

    def set_time_series_data_name(self, name):
        qry = "UPDATE inflow_time_series SET name=? WHERE fid=?;"
        self.execute(
            qry,
            (
                name,
                self.time_series_fid,
            ),
        )

    def set_time_series_data(self, name, data):
        qry = "UPDATE inflow_time_series SET name=? WHERE fid=?;"
        self.execute(
            qry,
            (
                name,
                self.time_series_fid,
            ),
        )
        qry = "DELETE FROM inflow_time_series_data WHERE series_fid = ?;"
        self.execute(qry, (self.time_series_fid,))
        qry = "INSERT INTO inflow_time_series_data (series_fid, time, value, value2) VALUES (?, ?, ?, ?);"
        self.execute_many(qry, data)

    def remove_time_series(self):
        qry = "DELETE FROM inflow_time_series_data WHERE series_fid = ?;"
        self.execute(qry, (self.time_series_fid,))
        qry = "DELETE FROM inflow_time_series WHERE fid = ?;"
        self.execute(qry, (self.time_series_fid,))


class Outflow(GeoPackageUtils):
    """
    Outflow object representation.
    """

    columns = [
        "fid",
        "name",
        "chan_out",
        "fp_out",
        "hydro_out",
        "chan_tser_fid",
        "chan_qhpar_fid",
        "chan_qhtab_fid",
        "fp_tser_fid",
        "type",
        "geom_type",
        "bc_fid",
    ]

    def __init__(self, fid, con, iface):
        super(Outflow, self).__init__(con, iface)
        self.fid = fid
        self.name = None
        self.row = None
        self.chan_out = None
        self.fp_out = None
        self.hydro_out = None
        self.chan_tser_fid = None
        self.chan_qhpar_fid = None
        self.chan_qhtab_fid = None
        self.fp_tser_fid = None
        self.time_series_data = None
        self.qh_params_data = None
        self.qh_table_data = None
        self.typ = None

    def add_row(self):
        data = (
            self.name,
            self.chan_out,
            self.fp_out,
            self.hydro_out,
            self.chan_tser_fid,
            self.chan_qhpar_fid,
            self.chan_qhtab_fid,
            self.fp_tser_fid,
            self.typ,
        )
        qry = """INSERT INTO outflow (
            name,
            chan_out,
            fp_out,
            hydro_out,
            chan_tser_fid,
            chan_qhpar_fid,
            chan_qhtab_fid,
            fp_tser_fid,
            type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);"""
        self.fid = self.execute(qry, data, get_rowid=True)

    def get_row(self):
        qry = "SELECT * FROM outflow WHERE fid = ?;"
        values = [x if x is not None else "" for x in self.execute(qry, (self.fid,)).fetchone()]
        self.row = OrderedDict(list(zip(self.columns, values)))
        self.name = self.row["name"]
        self.chan_out = self.row["chan_out"]
        self.fp_out = self.row["fp_out"]
        self.hydro_out = self.row["hydro_out"]
        self.chan_tser_fid = self.row["chan_tser_fid"]
        self.chan_qhpar_fid = self.row["chan_qhpar_fid"]
        self.chan_qhtab_fid = self.row["chan_qhtab_fid"]
        self.fp_tser_fid = self.row["fp_tser_fid"]
        self.typ = self.row["type"]
        self.geom_type = self.row["geom_type"]
        self.bc_fid = self.row["bc_fid"]
        return self.row

    def set_row(self):
        data = (
            self.name,
            self.chan_out,
            self.fp_out,
            self.hydro_out,
            self.chan_tser_fid,
            self.chan_qhpar_fid,
            self.chan_qhtab_fid,
            self.fp_tser_fid,
            self.typ,
            self.fid,
        )
        qry = """UPDATE outflow
                    SET name=?,
                    chan_out=?,
                    fp_out=?,
                    hydro_out=?,
                    chan_tser_fid=?,
                    chan_qhpar_fid=?,
                    chan_qhtab_fid=?,
                    fp_tser_fid=?,
                    type=?
                WHERE fid=?;"""
        self.execute(qry, data)

    def del_row(self):
        # first try to delete the bc from user layer
        if self.geom_type and self.bc_fid:
            qry = """DELETE FROM user_bc_{}s WHERE fid=? AND type='outflow';""".format(self.geom_type)
            self.execute(qry, (self.bc_fid,))
        # there is a trigger updating outflow table when the user bc layer is changed
        # this is for outflow rows without geometry
        qry = "DELETE FROM outflow WHERE fid=?"
        self.execute(qry, (self.fid,))

    def clear_type_data(self):
        self.typ = 0
        self.chan_out = 0
        self.fp_out = 0
        self.hydro_out = 0

    def set_type_data(self, typ):
        if typ == 4:
            # keep nr of outflow hydrograph to set it later
            old_hydro_out = self.hydro_out
        else:
            old_hydro_out = None
        self.clear_type_data()
        # self.clear_data_fids()
        self.typ = typ
        if typ in (2, 8, 9, 11):
            self.chan_out = 1
        elif typ in (1, 7):
            self.fp_out = 1
        elif typ == 3:
            self.chan_out = 1
            self.fp_out = 1
        elif typ == 4:
            self.hydro_out = old_hydro_out
        elif typ == 0:
            self.clear_data_fids()
        else:
            pass

        # if typ == 4:
        # # keep nr of outflow hydrograph to set it later
        # old_hydro_out = self.hydro_out
        # else:
        # old_hydro_out = None
        # self.clear_type_data()
        # self.typ = typ
        # if typ in (2, 8):
        # self.chan_out = 1
        # elif typ in (1, 7):
        # self.fp_out = 1
        # elif typ == 3:
        # self.chan_out = 1
        # self.fp_out = 1
        # elif typ == 4:
        # self.clear_data_fids()
        # self.hydro_out = old_hydro_out
        # elif typ == 0:
        # self.clear_data_fids()
        # else:
        # pass

    def get_time_series(self, order_by="name"):
        if order_by == "name":
            ts = self.execute("SELECT fid, name FROM outflow_time_series ORDER BY name COLLATE NOCASE;").fetchall()
        else:
            ts = self.execute("SELECT fid, name FROM outflow_time_series ORDER BY fid;").fetchall()
        if not ts:
            ts = self.add_time_series(fetch=True)
        return ts

    def add_time_series(self, name=None, fetch=False):
        qry = """INSERT INTO outflow_time_series (name) VALUES (?);"""
        rowid = self.execute(qry, (name,), get_rowid=True)
        name_qry = """UPDATE outflow_time_series SET name =  'Time Series ' || cast(fid as text) WHERE fid = ?;"""
        self.execute(name_qry, (rowid,))
        self.set_new_data_fid(rowid)
        if fetch:
            return self.get_time_series()

    def get_qh_params(self, order_by="name"):
        if order_by == "name":
            p = self.execute("SELECT fid, name FROM qh_params ORDER BY name COLLATE NOCASE;").fetchall()
        else:
            p = self.execute("SELECT fid, name FROM qh_params ORDER BY fid;").fetchall()
        if not p:
            p = self.add_qh_params(fetch=True)
        return p

    def add_qh_params(self, name=None, fetch=False):
        qry = """INSERT INTO qh_params (name) VALUES (?);"""
        rowid = self.execute(qry, (name,), get_rowid=True)
        name_qry = """UPDATE qh_params SET name =  'Q(h) parameters ' || cast(fid as text) WHERE fid = ?;"""
        self.execute(name_qry, (rowid,))
        self.set_new_data_fid(rowid)
        if fetch:
            return self.get_qh_params()

    def get_qh_tables(self, order_by="name"):
        if order_by == "name":
            t = self.execute("SELECT fid, name FROM qh_table ORDER BY name COLLATE NOCASE;").fetchall()
        else:
            t = self.execute("SELECT fid, name FROM qh_table ORDER BY fid;").fetchall()
        if not t:
            t = self.add_qh_table(fetch=True)
        return t

    def add_qh_table(self, name=None, fetch=False):
        qry = """INSERT INTO qh_table (name) VALUES (?);"""
        rowid = self.execute(qry, (name,), get_rowid=True)
        name_qry = """UPDATE qh_table SET name = 'Q(h) table ' || cast(fid as text) WHERE fid = ?;"""
        self.execute(name_qry, (rowid,))
        self.set_new_data_fid(rowid)
        if fetch:
            return self.get_qh_tables()

    def get_data_fid_name(self):
        """
        Return a list of [fid, name] pairs for each data set of a kind appropriate for the current outflow.
        This could be time series, Qh Table or Qh Parameters.
        """
        if self.typ in [5, 6, 7, 8]:
            return self.get_time_series()
        elif self.typ in [9, 10]:
            return self.get_qh_params()
        elif self.typ == 11:
            return self.get_qh_tables()
        else:
            pass

    def add_data(self, name=None):
        """
        Add a new data to current outflow type data table (time series, qh params or qh table).
        """
        data = None
        if self.typ in [5, 6, 7, 8]:
            data = self.add_time_series(name)
        elif self.typ in [9, 10]:
            data = self.add_qh_params(name)
        elif self.typ == 11:
            data = self.add_qh_table(name)
        else:
            pass
        return data

    def set_data_name(self, name):
        """
        Save new data name.
        """
        self.data_fid = self.get_cur_data_fid()
        if self.typ in [5, 6, 7, 8]:
            self.set_time_series_data_name(name)
        elif self.typ in [9, 10]:
            self.set_qh_params_data_name(name)
        elif self.typ == 11:
            self.set_qh_table_data_name(name)
        else:
            pass

    def set_data(self, name, data):
        """
        Save current model data to the right outflow data table.
        """
        self.data_fid = self.get_cur_data_fid()
        if self.typ in [5, 6, 7, 8]:
            self.set_time_series_data(name, data)
        elif self.typ in [9, 10]:
            self.set_qh_params_data(name, data)
        elif self.typ == 11:
            self.set_qh_table_data(name, data)
        else:
            pass

    def set_time_series_data_name(self, name):
        qry = "UPDATE outflow_time_series SET name=? WHERE fid=?;"
        self.execute(
            qry,
            (
                name,
                self.data_fid,
            ),
        )

    def set_time_series_data(self, name, data):
        qry = "UPDATE outflow_time_series SET name=? WHERE fid=?;"
        self.execute(
            qry,
            (
                name,
                self.data_fid,
            ),
        )
        qry = "DELETE FROM outflow_time_series_data WHERE series_fid = ?;"
        self.execute(qry, (self.data_fid,))
        qry = "INSERT INTO outflow_time_series_data (series_fid, time, value) VALUES ({}, ?, ?);"
        self.execute_many(qry.format(self.data_fid), data)

    def set_qh_params_data_name(self, name):
        qry = "UPDATE qh_params SET name=? WHERE fid=?;"
        self.execute(
            qry,
            (
                name,
                self.data_fid,
            ),
        )

    def set_qh_params_data(self, name, data):
        qry = "UPDATE qh_params SET name=? WHERE fid=?;"
        self.execute(
            qry,
            (
                name,
                self.data_fid,
            ),
        )
        qry = "DELETE FROM qh_params_data WHERE params_fid = ?;"
        self.execute(qry, (self.data_fid,))
        qry = "INSERT INTO qh_params_data (params_fid, hmax, coef, exponent) VALUES ({}, ?, ?, ?);"
        self.execute_many(qry.format(self.data_fid), data)

    def set_qh_table_data_name(self, name):
        qry = "UPDATE qh_table SET name=? WHERE fid=?;"
        self.execute(
            qry,
            (
                name,
                self.data_fid,
            ),
        )

    def set_qh_table_data(self, name, data):
        qry = "UPDATE qh_table SET name=? WHERE fid=?;"
        self.execute(
            qry,
            (
                name,
                self.data_fid,
            ),
        )
        qry = "DELETE FROM qh_table_data WHERE table_fid = ?;"
        self.execute(qry, (self.data_fid,))
        qry = "INSERT INTO qh_table_data (table_fid, depth, q) VALUES ({}, ?, ?);"
        self.execute_many(qry.format(self.data_fid), data)

    def get_cur_data_fid(self):
        """
        Get first non-zero outflow data fid (i.e. ch_tser_fid, fp_tser_fid, chan_qhpar_fid or ch_qhtab_fid).
        """
        data_fid_vals = [
            self.chan_tser_fid,
            self.chan_qhpar_fid,
            self.chan_qhtab_fid,
            self.fp_tser_fid,
        ]
        return next((val for val in data_fid_vals if val), None)

    def clear_data_fids(self):
        self.chan_tser_fid = 0
        self.fp_tser_fid = 0
        self.chan_qhpar_fid = 0
        self.chan_qhtab_fid = 0

    def set_new_data_fid(self, fid):
        """
        Set new data fid for current outflow type.
        """
        self.clear_data_fids()
        if self.typ in [5, 7]:
            self.fp_tser_fid = fid
        elif self.typ in [6, 8]:
            self.chan_tser_fid = fid
        elif self.typ in [9, 10]:
            self.chan_qhpar_fid = fid
        elif self.typ == 11:
            self.chan_qhtab_fid = fid
        else:
            pass

    def get_time_series_data(self):
        """
        Get time, value pairs for the current outflow.
        """
        qry = "SELECT time, value FROM outflow_time_series_data WHERE series_fid = ? ORDER BY time;"
        data_fid = self.get_cur_data_fid()
        if not data_fid:
            self.uc.bar_warn("No time series fid for current outflow is defined.")
            return
        self.time_series_data = self.execute(qry, (data_fid,)).fetchall()
        if not self.time_series_data:
            # add a new time series
            self.time_series_data = self.add_time_series_data(data_fid, fetch=True)
        return self.time_series_data

    def add_time_series_data(self, ts_fid, rows=5, fetch=False):
        """
        Add new rows to outflow_time_series_data for a given ts_fid.
        """
        qry = "INSERT INTO outflow_time_series_data (series_fid, time, value) VALUES (?, 0, 0);"
        self.execute_many(qry, ([ts_fid],) * rows)
        if fetch:
            return self.get_time_series_data()

    def get_qh_params_data(self):
        qry = "SELECT hmax, coef, exponent FROM qh_params_data WHERE params_fid = ?;"
        params_fid = self.get_cur_data_fid()
        self.qh_params_data = self.execute(qry, (params_fid,)).fetchall()
        if not self.qh_params_data:
            self.qh_params_data = self.add_qh_params_data(params_fid, fetch=True)
        return self.qh_params_data

    def add_qh_params_data(self, params_fid, rows=1, fetch=False):
        """
        Add new rows to qh_params_data for a given params_fid.
        """
        qry = "INSERT INTO qh_params_data (params_fid, hmax, coef, exponent) VALUES (?, NULL, NULL, NULL);"
        self.execute_many(qry, ([params_fid],) * rows)
        if fetch:
            return self.get_qh_params_data()

    def get_qh_table_data(self):
        qry = "SELECT depth, q FROM qh_table_data WHERE table_fid = ? ORDER BY depth;"
        table_fid = self.get_cur_data_fid()
        self.qh_table_data = self.execute(qry, (table_fid,)).fetchall()
        if not self.qh_table_data:
            self.qh_table_data = self.add_qh_table_data(table_fid, fetch=True)
        return self.qh_table_data

    def add_qh_table_data(self, table_fid, rows=5, fetch=False):
        """
        Add new rows to qh_table_data for a given table_fid.
        """
        qry = "INSERT INTO qh_table_data (table_fid, depth, q) VALUES (?, NULL, NULL);"
        self.execute_many(qry, ([table_fid],) * rows)
        if fetch:
            return self.get_qh_table_data()

    def get_data(self):
        """
        Get data for current type and data_fid of the outflow.
        """
        if self.typ in [5, 6, 7, 8]:
            return self.get_time_series_data()
        elif self.typ in [9, 10]:
            return self.get_qh_params_data()
        elif self.typ == 11:
            return self.get_qh_table_data()
        else:
            pass

    def get_new_data_name(self, fid):
        if self.typ in [5, 6, 7, 8]:
            return "OutTimeSeries {}".format(fid)
        elif self.typ in [9, 10]:
            return "Q(h) parameters {}".format(fid)
        elif self.typ == 11:
            return "Q(h) table {}".format(fid)
        else:
            return None


class Rain(GeoPackageUtils):
    """
    Rain data representation.
    """

    columns = [
        "fid",
        "name",
        "irainreal",
        "irainbuilding",
        "time_series_fid",
        "tot_rainfall",
        "rainabs",
        "irainarf",
        "movingstorm",
        "rainspeed",
        "iraindir",
        "notes",
    ]

    def __init__(self, con, iface):
        super(Rain, self).__init__(con, iface)
        self.row = None
        self.series_fid = None
        self.time_series = None
        self.time_series_data = None
        self.name = None
        self.irainreal = None
        self.irainbuilding = None
        self.series_fid = None
        self.tot_rainfall = None
        self.rainabs = None
        self.irainarf = None
        self.movingstorm = None
        self.rainspeed = None
        self.iraindir = None
        self.notes = None

    def get_row(self):
        qry = "SELECT * FROM rain;"
        data = self.execute(qry).fetchone()
        if not data:
            values = [0] * len(self.columns)
            values[0] = 1
            values[1] = ""
            values[-1] = ""
        else:
            values = [x if x is not None else "" for x in data]
        self.row = OrderedDict(list(zip(self.columns, values)))
        self.name = self.row["name"]
        self.irainreal = self.row["irainreal"]
        self.irainbuilding = self.row["irainbuilding"]
        self.series_fid = self.row["time_series_fid"]
        self.tot_rainfall = self.row["tot_rainfall"]
        self.rainabs = self.row["rainabs"]
        self.irainarf = self.row["irainarf"]
        self.movingstorm = self.row["movingstorm"]
        self.rainspeed = self.row["rainspeed"]
        self.iraindir = self.row["iraindir"]
        self.notes = self.row["notes"]
        return self.row

    def set_row(self):
        qry = """INSERT OR REPLACE INTO rain (
            fid, name, irainreal, irainbuilding, time_series_fid, tot_rainfall, rainabs, irainarf,
            movingstorm, rainspeed, iraindir, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?);"""
        data = (
            1,
            self.name,
            self.irainreal,
            self.irainbuilding,
            self.series_fid,
            self.tot_rainfall,
            self.rainabs,
            self.irainarf,
            self.movingstorm,
            self.rainspeed,
            self.iraindir,
            self.notes,
        )
        self.execute(qry, data)

    def get_time_series(self, order_by="name"):
        if order_by == "name":
            ts = self.execute("SELECT fid, name FROM rain_time_series ORDER BY name COLLATE NOCASE;").fetchall()
        else:
            ts = self.execute("SELECT fid, name FROM rain_time_series ORDER BY fid;").fetchall()
        if not ts:
            ts = self.add_time_series(fetch=True)
        return ts

    def add_time_series(self, name=None, fetch=False):
        qry = """INSERT INTO rain_time_series (name) VALUES (?);"""
        rowid = self.execute(qry, (name,), get_rowid=True)
        if not name:
            name_qry = """UPDATE rain_time_series SET name =  'Time series ' || cast(fid as text) WHERE fid = ?;"""
            self.execute(name_qry, (rowid,))
        else:
            name_qry = """UPDATE rain_time_series SET name = ? WHERE fid = ?;"""
            self.execute(
                name_qry,
                (
                    name,
                    rowid,
                ),
            )

        self.series_fid = rowid
        if not name:
            self.name = "Time series {}".format(rowid)
        else:
            self.name = name.format(rowid)

        if fetch:
            return self.get_time_series()
        else:
            return self.name

    def del_time_series(self):
        qry = "DELETE FROM rain_time_series_data WHERE series_fid = ?;"
        self.execute(qry, (self.series_fid,))
        qry = "DELETE FROM rain_time_series WHERE fid = ?;"
        self.execute(qry, (self.series_fid,))

    def get_time_series_data(self):
        if not self.series_fid:
            # self.uc.bar_warn('No time series fid for rain defined.')
            return
        qry = "SELECT time, value FROM rain_time_series_data WHERE series_fid = ? ORDER BY time;"
        self.time_series_data = self.execute(qry, (self.series_fid,)).fetchall()
        if not self.time_series_data:
            # add a new time series
            self.time_series_data = self.add_time_series_data(self.series_fid, fetch=True)
        return self.time_series_data

    def add_time_series_data(self, ts_fid, rows=5, fetch=False):
        """
        Add new rows to rain_time_series_data for a given ts_fid.
        """
        qry = "INSERT INTO rain_time_series_data (series_fid, time, value) VALUES (?, 0, 0);"
        self.execute_many(qry, ([ts_fid],) * rows)
        if fetch:
            return self.get_time_series_data()

    def set_time_series_data(self, name, data):
        qry = "UPDATE rain_time_series SET name=? WHERE fid=?;"
        self.execute(
            qry,
            (
                name,
                self.series_fid,
            ),
        )
        qry = "DELETE FROM rain_time_series_data WHERE series_fid = ?;"
        self.execute(qry, (self.series_fid,))
        qry = "INSERT INTO rain_time_series_data (series_fid, time, value) VALUES (?, ?, ?);"
        self.execute_many(qry, data)

    def set_time_series_data_name(self, name):
        qry = "UPDATE rain_time_series SET name=? WHERE fid=?;"
        self.execute(
            qry,
            (
                name,
                self.series_fid,
            ),
        )


class Evaporation(GeoPackageUtils):
    """
    Evaporation data representation.
    """

    columns = ["fid", "ievapmonth", "iday", "clocktime"]

    def __init__(self, con, iface):
        super(Evaporation, self).__init__(con, iface)
        self.row = None
        self.month = "january"
        self.monthly = None
        self.hourly = None
        self.hourly_sum = 0

    def get_row(self):
        qry = "SELECT * FROM evapor;"
        values = [x if x is not None else "" for x in self.execute(qry).fetchone()]
        self.row = OrderedDict(list(zip(self.columns, values)))
        return self.row

    def get_monthly(self):
        qry = "SELECT month, monthly_evap FROM evapor_monthly;"
        self.monthly = self.execute(qry).fetchall()
        return self.monthly

    def get_hourly(self):
        qry = "SELECT hour, hourly_evap FROM evapor_hourly WHERE month = ? ORDER BY fid;"
        self.hourly = self.execute(qry, (self.month,)).fetchall()
        return self.hourly

    def get_hourly_sum(self):
        qry = "SELECT ROUND(SUM(hourly_evap), 3) FROM evapor_hourly WHERE month = ? ORDER BY fid;"
        self.hourly_sum = self.execute(qry, (self.month,)).fetchone()[0]
        return self.hourly_sum


class Street(GeoPackageUtils):
    """
    Street data implementation.
    """

    columns = ["fid", "str_fid", "igridn", "depex", "stman", "elstr", "geom"]

    def __init__(self, fid, con, iface):
        super(Street, self).__init__(con, iface)
        self.fid = fid
        self.row = None
        self.general = None
        self.elems = None
        self.name = None
        self.notes = None
        self.curb_height = None
        self.n_value = None
        self.elevation = None

    def get_row(self):
        qry = "SELECT * FROM street_elems WHERE fid = ?;"
        values = [x if x is not None else "" for x in self.execute(qry, (self.fid,)).fetchone()]
        self.row = OrderedDict(list(zip(self.columns, values)))
        self.name = self.row["name"]
        self.curb_height = self.row["depex"]
        self.n_value = self.row["stman"]
        self.elevation = self.row["elstr"]
        return self.row

    def get_name_notes(self):
        qry = "SELECT stname, notes FROM streets WHERE fid = ?;"
        values = [x if x is not None else "" for x in self.execute(qry, (self.fid,)).fetchone()]
        self.name, self.notes = values
        return self.name, self.notes

    def get_elems(self):
        qry = "SELECT istdir, widr FROM street_elems WHERE str_fid = ?;"
        self.elems = self.execute(qry, (self.fid,)).fetchall()


class Reservoir(GeoPackageUtils):
    """
    Reservoir data representation.
    """

    columns = ["fid", "name", "wsel", "notes"]

    def __init__(self, fid, con, iface):
        super(Reservoir, self).__init__(con, iface)
        self.fid = fid
        self.row = None
        self.name = None
        self.wsel = None

    def get_row(self):
        qry = "SELECT * FROM user_reservoirs WHERE fid = ?;"
        data = self.execute(qry, (self.fid,)).fetchone()
        if not data:
            return
        values = [x if x is not None else "" for x in data]
        self.row = OrderedDict(list(zip(self.columns, values)))
        self.name = self.row["name"]
        self.wsel = self.row["wsel"]
        return self.row

    def set_row(self):
        qry = """UPDATE user_reservoirs SET
            name = '{0}',
            wsel = {1}
        WHERE fid = {2};""".format(
            self.name, self.wsel, self.fid
        )
        self.execute(qry)

    def del_row(self):
        qry = "DELETE FROM user_reservoirs WHERE fid=?"
        self.execute(qry, (self.fid,))


class Structure(GeoPackageUtils):
    """
    Hydraulic structure object representation.
    """

    columns = [
        "fid",
        "type",
        "structname",
        "ifporchan",
        "icurvtable",
        "inflonod",
        "outflonod",
        "inoutcont",
        "headrefel",
        "clength",
        "cdiameter",
        "notes",
    ]

    def __init__(self, fid, con, iface):
        super(Structure, self).__init__(con, iface)
        self.row = None
        self.fid = fid
        self.type = None
        self.name = None
        self.ifporchan = None
        self.icurvtable = None
        self.inflonod = None
        self.outflonod = None
        self.inoutcont = None
        self.headrefel = None
        self.clength = None
        self.cdiameter = None
        self.notes = None
        self.geom = None

    def get_row(self):
        qry = "SELECT * FROM struct WHERE fid = ?;"
        values = [x if x is not None else "" for x in self.execute(qry, (self.fid,)).fetchone()]
        self.row = OrderedDict(list(zip(self.columns, values)))
        self.fid = self.row["fid"]
        self.type = self.row["type"]
        self.name = self.row["structname"]
        self.ifporchan = self.row["ifporchan"]
        self.icurvtable = self.row["icurvtable"]
        self.inflonod = self.row["inflonod"]
        self.outflonod = self.row["outflonod"]
        self.inoutcont = self.row["inoutcont"]
        self.headrefel = self.row["headrefel"]
        self.clength = self.row["clength"]
        self.cdiameter = self.row["cdiameter"]
        self.notes = self.row["notes"]
        return self.row

    def set_row(self):
        data = (
            self.type,
            self.name,
            self.ifporchan,
            self.icurvtable,
            self.inflonod,
            self.outflonod,
            self.inoutcont,
            self.headrefel,
            self.clength,
            self.cdiameter,
            self.notes,
            self.fid,
        )
        qry = """UPDATE struct SET
                    type = ?,
                    structname = ?,
                    ifporchan = ?,
                    icurvtable = ?,
                    inflonod = ?,
                    outflonod = ?,
                    inoutcont = ?,
                    headrefel = ?,
                    clength = ?,
                    cdiameter = ?,
                    notes = ?
                WHERE fid = ?;"""
        self.execute(qry, data)

    def del_row(self):
        # first try to delete the struct from user layer
        self.execute("DELETE FROM user_struct WHERE fid=?;", (self.fid,))
        self.execute("DELETE FROM rat_curves WHERE fid=?;", (self.fid,))
        self.execute("DELETE FROM repl_rat_curves WHERE fid=?;", (self.fid,))
        self.execute("DELETE FROM struct WHERE fid=?", (self.fid,))
        self.execute("DELETE FROM bridge_variables WHERE struct_fid=?", (self.fid,))
        self.execute("DELETE FROM bridge_xs WHERE struct_fid=?", (self.fid,))
        self.execute("DELETE FROM culvert_equations WHERE struct_fid=?", (self.fid,))
        self.execute("DELETE FROM storm_drains WHERE struct_fid=?", (self.fid,))

    def get_stormdrain(self):
        qry = "SELECT stormdmax FROM storm_drains WHERE struct_fid = ?;"
        row = self.execute(qry, (self.fid,)).fetchone()
        if row:
            return row[0]
        else:
            return False

    def set_stormdrain_capacity(self, stormdmax):
        qry_del = "DELETE FROM storm_drains WHERE struct_fid = ?;"
        self.execute(qry_del, (self.fid,))
        qry_ins = "INSERT INTO storm_drains (struct_fid, stormdmax) VALUES (?, ?);"
        self.execute(
            qry_ins,
            (
                self.fid,
                stormdmax,
            ),
        )

    def clear_stormdrain_data(self):
        """
        Delete storm drain data when user uncheck the storm drain checkbox.
        """
        qry = "DELETE FROM storm_drains WHERE struct_fid = ?;"
        self.execute(qry, (self.fid,))

    def get_table_data(self):
        res = []
        if self.icurvtable == 0:
            # rating curve
            qry_curv = "SELECT hdepexc, coefq, expq, coefa, expa FROM rat_curves WHERE struct_fid = ? ORDER BY hdepexc;"
            curv = self.execute(qry_curv, (self.fid,)).fetchall()
            qry_repl = (
                "SELECT repdep, rqcoef, rqexp, racoef, raexp FROM repl_rat_curves WHERE struct_fid = ? ORDER BY repdep;"
            )
            repl = self.execute(qry_repl, (self.fid,)).fetchall()
            for i, row in enumerate(curv):
                res.append(row)
                # check if a replacement curve is defined
                try:
                    for row2 in repl:
                        if row2 is not None:
                            del res[-1]
                            res.append(row + row2)
                            break

                #                     if repl[i][0]:
                #                         res += repl[i]
                except Exception as e:
                    pass
            if not res:
                res = [""] * 10
        elif self.icurvtable == 1:
            # rating table
            qry_tab = "SELECT hdepth, qtable, atable FROM rat_table WHERE struct_fid = ? ORDER BY hdepth;"
            res = self.execute(qry_tab, (self.fid,)).fetchall()
            if not res:
                res = [""] * 3
        elif self.icurvtable == 2:
            # culvert equation
            qry_tab = (
                "SELECT typec, typeen, culvertn, ke, cubase, multibarrels FROM culvert_equations WHERE struct_fid = ?;"
            )
            res = self.execute(qry_tab, (self.fid,)).fetchall()
            if not res:
                res = [""] * 6
            else:
                lst = list(res[0])
                lst[5] = 1 if lst[5] in [None, "0", "0.0"] else lst[5]
                res[0] = tuple(lst)
        elif self.icurvtable == 3:
            # bridge xs
            qry_tab = "SELECT xup, yup, yb FROM bridge_xs WHERE struct_fid = ? ORDER BY xup;"
            res = self.execute(qry_tab, (self.fid,)).fetchall()
            if not res:
                res = [""] * 3
        else:
            if not res:
                res = [""] * 3
        self.table_data = res
        return res

    def set_table_data(self, data):
        if self.icurvtable == 0:
            # rating curve
            qry = "DELETE FROM rat_curves WHERE struct_fid = ?;"
            self.execute(qry, (self.fid,))
            qry = "INSERT INTO rat_curves (struct_fid, hdepexc, coefq, expq, coefa, expa) VALUES ({}, ?, ?, ?, ?, ?);"
            self.execute_many(qry.format(self.fid), [row[:5] for row in data])
            qry = "DELETE FROM repl_rat_curves WHERE struct_fid = ?;"
            self.execute(qry, (self.fid,))
            for repl_data in [row[5:] for row in data]:
                if is_number(repl_data[0]) and not isnan(repl_data[0]):
                    qry = "INSERT INTO repl_rat_curves (struct_fid, repdep, rqcoef, rqexp, racoef, raexp) VALUES ({}, ?, ?, ?, ?, ?);"
                    self.execute(qry.format(self.fid), repl_data)
        elif self.icurvtable == 1:
            # rating table
            qry = "DELETE FROM rat_table WHERE struct_fid = ?;"
            self.execute(qry, (self.fid,))
            qry = "INSERT INTO rat_table (struct_fid, hdepth, qtable, atable) VALUES ({}, ?, ?, ?);"
            self.execute_many(qry.format(self.fid), [row[:3] for row in data])
        elif self.icurvtable == 2:
            # culvert equation
            qry = "DELETE FROM culvert_equations WHERE struct_fid = ?;"
            self.execute(qry, (self.fid,))
            qry = "INSERT INTO culvert_equations (struct_fid, typec, typeen, culvertn, ke, cubase, multibarrels) VALUES ({}, ?, ?, ?, ?, ?, ?);"
            for row in data:
                row[-1] = row[-1] if row[-1] not in [None, 0] else 1
                self.execute_many(qry.format(self.fid), [row[:6]])
        elif self.icurvtable == 3:
            # bridge xs
            qry = "DELETE FROM bridge_xs WHERE struct_fid = ?;"
            self.execute(qry, (self.fid,))
            qry = "INSERT INTO bridge_xs (struct_fid, xup, yup, yb) VALUES ({}, ?, ?, ?);"
            self.execute_many(qry.format(self.fid), [row[:3] for row in data])
        else:
            pass


class InletRatingTable(GeoPackageUtils):
    """
    Inlet data representation.
    """

    def __init__(self, con, iface):
        super(InletRatingTable, self).__init__(con, iface)
        self.name = None

    def get_rating_tables(self, order_by="name"):
        if order_by == "name":
            rt = self.execute("SELECT fid, name FROM swmmflort ORDER BY name COLLATE NOCASE;").fetchall()
        else:
            rt = self.execute("SELECT fid, name FROM swmmflort ORDER BY fid;").fetchall()
        return rt

    def add_rating_table(self, name=None):
        if name == None:
            qry = """INSERT INTO swmmflort (name) VALUES (?);"""
            rowid = self.execute(qry, (name,), get_rowid=True)
            name_qry = """UPDATE swmmflort SET name =  'RatingTable' || cast(fid as text) WHERE fid = ?;"""
            self.execute(name_qry, (rowid,))
            if not name:
                self.name = "RatingTable{}".format(rowid)
            return self.name
        else:
            sel_qry = "SELECT fid FROM swmmflort WHERE name = ?;"
            swmm_rt_fid = self.execute(sel_qry, (name,)).fetchone()
            if swmm_rt_fid:
                del_qry2 = "DELETE FROM swmmflort_data WHERE swmm_rt_fid = ?;"
                self.execute(del_qry2, (swmm_rt_fid[0],))
                del_qry = "DELETE FROM swmmflort WHERE name = ?;"
                self.execute(del_qry, (name,))
            qry = """INSERT INTO swmmflort (name) VALUES (?);"""
            rowid = self.execute(qry, (name,), get_rowid=True)
            name_qry = """UPDATE swmmflort SET name =  ? WHERE fid = ?;"""
            self.execute(
                name_qry,
                (
                    name,
                    rowid,
                ),
            )
            return name

    def del_rating_table(self, rt_fid):
        qry = "UPDATE user_swmm_nodes SET rt_fid = ? WHERE rt_fid = ?;"
        self.execute(qry, (None, rt_fid))
        qry = "DELETE FROM swmmflort WHERE fid = ?;"
        self.execute(qry, (rt_fid,))
        qry = "DELETE FROM swmmflort_data WHERE swmm_rt_fid = ?;"
        self.execute(qry, (rt_fid,))

    def get_inlet_table_data(self, rt_fid):
        qryRT = "SELECT depth, q FROM swmmflort_data WHERE swmm_rt_fid = ? ORDER BY depth;"
        rating_table_data = self.execute(qryRT, (rt_fid,)).fetchall()      
        if not rating_table_data:
            # add a new time series
            rating_table_data = self.add_rating_table_data(rt_fid, fetch=True)
        return rating_table_data

    def add_rating_table_data(self, rt_fid, rows=5, fetch=False):
        """
        Add new rows to swmmflort_data for a given rt_fid.
        """
        qry = "INSERT INTO swmmflort_data (swmm_rt_fid, depth, q) VALUES (?, 0, 0);"
        self.execute_many(qry, ([rt_fid],) * rows)
        if fetch:
            return self.get_inlet_table_data(rt_fid)

    def set_rating_table_data(self, rt_fid, name, data):
        qry = "UPDATE swmmflort SET name=? WHERE fid=?;"
        self.execute(
            qry,
            (
                name,
                rt_fid,
            ),
        )
        qry = "DELETE FROM swmmflort_data WHERE swmm_rt_fid = ?;"
        self.execute(qry, (rt_fid,))
        qry = "INSERT INTO swmmflort_data (swmm_rt_fid, depth, q) VALUES (?, ?, ?);"
        self.execute_many(qry, data)

    def set_rating_table_data_name(self, rt_fid, name):
        qry = "UPDATE swmmflort SET name=? WHERE fid=?;"
        self.execute(
            qry,
            (
                name,
                rt_fid,
            ),
        )


class PumpCurves(GeoPackageUtils):
    """
    Pumps data representation.
    """

    def __init__(self, con, iface):
        super(PumpCurves, self).__init__(con, iface)
        self.name = None

    def get_pump_curves(self, order_by="name"):
        if order_by == "name":
            crv = self.execute(
                "SELECT DISTINCT fid, pump_curve_name FROM swmm_pumps_curve_data ORDER BY pump_curve_name COLLATE NOCASE;"
            ).fetchall()
        else:
            crv = self.execute("SELECT fid, pump_curve_name FROM swmm_pumps_curve_data ORDER BY fid;").fetchall()
        # if not crv:
        #     crv = self.add_pump_curve()
        return crv

    def add_pump_curve(self, name=None):
        if name == None:
            qry = """INSERT INTO swmm_pumps_curve_data (pump_curve_name, pump_curve_type) VALUES (?, ?);"""
            rowid = self.execute(qry, (name, "Pump1"), get_rowid=True)
            name_qry = """UPDATE swmm_pumps_curve_data SET pump_curve_name =  'PumpCurve' || cast(fid as text) WHERE fid = ?;"""
            self.execute(name_qry, (rowid,))
            if not name:
                self.name = "PumpCurve{}".format(rowid)
            return self.name
        else:
            sel_qry = "SELECT fid FROM swmm_pumps_curve_data WHERE pump_curve_name = ?;"
            fid = self.execute(sel_qry, (name,)).fetchone()
            if fid:
                del_qry2 = "DELETE FROM swmm_pumps_curve_data WHERE fid = ?;"
                self.execute(del_qry2, (fid[0],))
                del_qry = "DELETE FROM swmm_pumps_curve_data WHERE pump_curve_name = ?;"
                self.execute(del_qry, (name,))
            qry = """INSERT INTO swmm_pumps_curve_data (pump_curve_name) VALUES (?);"""
            rowid = self.execute(qry, (name,), get_rowid=True)
            name_qry = """UPDATE swmm_pumps_curve_data SET pump_curve_name =  ? WHERE fid = ?;"""
            self.execute(
                name_qry,
                (
                    name,
                    rowid,
                ),
            )
            return name

    def del_pump_curve(self, name):
        self.execute("DELETE FROM swmm_pumps_curve_data WHERE pump_curve_name = ?;", (name,))
        self.execute("UPDATE user_swmm_pumps SET pump_curve = '*' WHERE pump_curve = ?", (name,))

    def get_pump_curve_data(self, name):
        qry = "SELECT x_value, y_value FROM swmm_pumps_curve_data WHERE pump_curve_name = ? ORDER BY x_value;"
        curve_data = self.execute(qry, (name,)).fetchall()
        if not curve_data:
            # add a new curve:
            curve_data = self.add_pump_curve_data(name, fetch=True)
        return curve_data

    def add_pump_curve_data(self, name, rows=5, fetch=False):
        """
        Add new rows to swmm_pumps_curve_data for a given name.
        """
        qry = "INSERT INTO swmm_pumps_curve_data (pump_curve_name, x_value, y_value) VALUES (?, 0, 0);"
        self.execute_many(qry, ([name],) * rows)
        if fetch:
            return self.get_pump_curve_data(name)

    def set_pump_curve_data(self, name, data):
        qry = "DELETE FROM swmm_pumps_curve_data WHERE pump_curve_name = ?;"
        self.execute(qry, (name,))
        qry = "INSERT INTO swmm_pumps_curve_data (pump_curve_name, x_value, y_value) VALUES (?, ?, ?);"
        self.execute_many(qry, data)

    def set_pump_curve_name(self, name, new_name):
        # fids = self.execute("SELECT fid FROM swmm_pumps_curve_data WHERE pump_curve_name = ?;", (name,)).fetchall()
        # qry = "UPDATE swmm_pumps_curve_data SET pump_curve_name = ? WHERE fid = ?;"
        # v = []
        # for f in fids:
        #     v.append((new_name, f[0]))
        # self.execute_many( qry, v)
        self.execute(
            "UPDATE swmm_pumps_curve_data SET pump_curve_name = ? WHERE pump_curve_name = ?;",
            (
                new_name,
                name,
            ),
        )
        self.execute(
            "UPDATE user_swmm_pumps SET pump_curve = ? WHERE pump_curve = ?;",
            (
                new_name,
                name,
            ),
        )
