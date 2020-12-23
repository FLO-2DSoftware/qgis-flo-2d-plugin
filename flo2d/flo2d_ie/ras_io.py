# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import re
import bisect
from collections import OrderedDict
from itertools import zip_longest, chain
from ..geopackage_utils import GeoPackageUtils
from ..flo2d_tools.schema2user_tools import remove_features

from qgis.core import QgsFeature, QgsGeometry, QgsPointXY

class RASProject(GeoPackageUtils):

    def __init__(self, con, iface, lyrs, prj_path=None, interpolated=False):
        super(RASProject, self).__init__(con, iface)
        self.lyrs = lyrs
        self.project_path = prj_path
        self.interpolated = interpolated
        self.ras_geom = None
        self.ras_plan = None
        self.ras_flow = None

    def find_geometry(self):
        if self.project_path is None:
            return
        fname = self.project_path[:-3]
        with open(self.project_path, 'r') as project:
            project_text = project.read()
            plan_regex = re.compile(r'(?P<head>Current Plan=)(?P<geom>[^\n]+)')
            plan_result = re.search(plan_regex, project_text)
            plandict = plan_result.groupdict()
            self.ras_plan = '{}{}'.format(fname, plandict['geom'])
        with open(self.ras_plan, 'r') as plan:
            plan_text = plan.read()
            geom_regex = re.compile(r'(?P<head>Geom File=)(?P<geom>[^\n]+)')
            geom_result = re.search(geom_regex, plan_text)
            geomdict = geom_result.groupdict()
            self.ras_geom = '{}{}'.format(fname, geomdict['geom'])

    def get_geometry(self, geom_pth=None):
        if geom_pth is None:
            geom_pth = self.ras_geom
        geometry = RASGeometry(geom_pth, self.interpolated)
        ras_geometry = geometry.get_ras_geometry()
        if ras_geometry:
            first_val = next(iter(ras_geometry.values()))
            if not first_val['xs_data']:
                raise Exception
            return ras_geometry
        else:
            raise Exception

    @staticmethod
    def create_xs_geometry(xs_data, limit=0):
        xs_points = xs_data['points']
        xs_polyline = [QgsPointXY(float(x), float(y)) for x, y in xs_points]
        xs_geom = QgsGeometry().fromPolylineXY(xs_polyline)
        if limit == 1:
            left_station, right_station, new_elev = RASGeometry.find_banks(xs_data)
        elif limit == 2:
            left_station, right_station, new_elev = RASGeometry.find_levees(xs_data)
        else:
            return xs_geom
        if left_station and right_station and new_elev:
            xs_data['elev'] = new_elev
            lpoint = xs_geom.interpolate(left_station)
            rpoint = xs_geom.interpolate(right_station)
            stations = [xs_geom.lineLocatePoint(QgsGeometry().fromPointXY(p)) for p in xs_polyline]
            lidx = bisect.bisect(stations, left_station)
            ridx = bisect.bisect(stations, right_station)
            xs_polyline = xs_polyline[lidx:ridx]
            xs_polyline.insert(0, lpoint.asPoint())
            xs_polyline.append(rpoint.asPoint())
            xs_geom = QgsGeometry().fromPolylineXY(xs_polyline)
        return xs_geom

    def write_xsections(self, ras_geometry, limit):
        user_lbank_lyr = self.lyrs.data['user_left_bank']['qlyr']
        user_rbank_lyr = self.lyrs.data['user_right_bank']['qlyr']
        user_xs_lyr = self.lyrs.data['user_xsections']['qlyr']
        remove_features(user_lbank_lyr)
        remove_features(user_rbank_lyr)
        remove_features(user_xs_lyr)
        self.clear_tables('user_chan_n', 'user_xsec_n_data')
        left_bank_fields = user_lbank_lyr.fields()
        right_bank_fields = user_rbank_lyr.fields()
        xs_fields = user_xs_lyr.fields()
        xs_fid = self.get_max('user_xsections') + 1
        nxsecnum = self.get_max('user_chan_n', 'nxsecnum') + 1
        uchan_n_rows = []
        uxsec_n_rows = []
        user_lbank_lyr.startEditing()
        user_rbank_lyr.startEditing()
        user_xs_lyr.startEditing()
        for seg_fid, (river_name, data) in enumerate(ras_geometry.items(), 1):
            left_bank_polyline, right_bank_polyline = [], []
            left_bank_feat, right_bank_feat = QgsFeature(), QgsFeature()
            left_bank_feat.setFields(left_bank_fields)
            right_bank_feat.setFields(right_bank_fields)
            for xs_key, xs_data in data['xs_data'].items():
                xs_geom = self.create_xs_geometry(xs_data, limit)
                xs_poly = xs_geom.asPolyline()
                left_bank_polyline.append(QgsPointXY(xs_poly[0]))
                right_bank_polyline.append(QgsPointXY(xs_poly[-1]))
                xs_feat = QgsFeature()
                xs_feat.setFields(xs_fields)
                xs_feat.setGeometry(xs_geom)
                xs_feat.setAttribute('fid', xs_fid)
                xs_feat.setAttribute('type', 'N')
                xs_feat.setAttribute('name', xs_key)
                fcn = xs_feat.attribute('fcn')
                xs_feat.setAttribute('fcn', fcn if fcn is not None else 0.04)
                user_xs_lyr.addFeature(xs_feat)
                uchan_n_rows.append((xs_fid, nxsecnum, xs_key))
                xs_elev = xs_data['elev']
                for xi, yi in xs_elev:
                    uxsec_n_rows.append((nxsecnum, float(xi), float(yi)))
                xs_fid += 1
                nxsecnum += 1
            left_bank_geom = QgsGeometry().fromPolylineXY(left_bank_polyline)
            left_bank_feat.setGeometry(left_bank_geom)
            left_bank_feat.setAttribute('fid', seg_fid)
            left_bank_feat.setAttribute('name', river_name)
            user_lbank_lyr.addFeature(left_bank_feat)
            right_bank_geom = QgsGeometry().fromPolylineXY(right_bank_polyline)
            right_bank_feat.setGeometry(right_bank_geom)
            right_bank_feat.setAttribute('chan_seg_fid', seg_fid)
            user_rbank_lyr.addFeature(right_bank_feat)
        cursor = self.con.cursor()
        cursor.executemany('INSERT INTO user_chan_n (user_xs_fid, nxsecnum, xsecname) VALUES (?,?,?);', uchan_n_rows)
        cursor.executemany('INSERT INTO user_xsec_n_data (chan_n_nxsecnum, xi, yi) VALUES (?,?,?);', uxsec_n_rows)
        self.con.commit()
        user_lbank_lyr.commitChanges()
        user_lbank_lyr.updateExtents()
        user_lbank_lyr.triggerRepaint()
        user_lbank_lyr.removeSelection()
        user_rbank_lyr.commitChanges()
        user_rbank_lyr.updateExtents()
        user_rbank_lyr.triggerRepaint()
        user_rbank_lyr.removeSelection()
        user_xs_lyr.commitChanges()
        user_xs_lyr.updateExtents()
        user_xs_lyr.triggerRepaint()
        user_xs_lyr.removeSelection()


class RASGeometry(object):

    def __init__(self, geom_path, interpolated=False):
        self.geom_path = geom_path
        self.interpolated = interpolated
        self.geom_txt = self.read_geom()
        self.ras_geometry = OrderedDict()

    def read_geom(self):
        with open(self.geom_path, 'r') as geom_file:
            geom_txt = geom_file.read()
        return geom_txt

    @staticmethod
    def find_slices(indexes):
        indices = []
        for n in range(len(indexes)):
            sl = indexes[n:n + 2]
            if len(sl) < 2:
                sl.append(None)
            indices.append(sl)
        return indices

    @staticmethod
    def split_txt_data(txt, width, chunk_size):
        split_values = []
        for row in txt.strip('\n').split('\n'):
            for n in range(0, width, chunk_size):
                chunk = row[n:n + chunk_size]
                try:
                    fchunk = float(chunk)
                    split_values.append(fchunk)
                except ValueError:
                    continue
        return split_values

    @staticmethod
    def find_banks(xs_data):
        text = xs_data['extra']
        elev = xs_data['elev']
        stations = [x[0] for x in elev]
        regex = re.compile(r'Bank Sta=(?P<stations>[^\n]+)')
        result = re.search(regex, text)
        if not result:
            return None, None, None
        banksdict = result.groupdict()
        banks = banksdict['stations']
        lbank_station, rbank_station = [float(b) for b in banks.split(',')]
        try:
            lidx = stations.index(lbank_station)
        except ValueError:
            lidx = 0
        ridx = stations.index(rbank_station) + 1
        new_elev = [(round(s - lbank_station, 3), e) for s, e in elev[lidx:ridx]]
        return lbank_station, rbank_station, new_elev

    @staticmethod
    def find_levees(xs_data):
        text = xs_data['extra']
        elev = xs_data['elev']
        stations = [x[0] for x in elev]
        regex = re.compile(r'Levee=(?P<stations>[^\n]+)')
        result = re.search(regex, text)
        if not result:
            return None, None, None
        leveedict = result.groupdict()
        levees = leveedict['stations'].split(',')
        llevee_station = elev[0][0]
        rlevee_station = elev[-1][0]
        trim_elev = elev
        shift = 0
        try:
            llevee_station, llevee_value = [float(l) for l in levees[1:3]]
            lidx = bisect.bisect(stations, llevee_station)
            trim_elev = trim_elev[lidx:]
            trim_elev.insert(0, (llevee_station, llevee_value))
            shift = lidx - 1
        except ValueError:
            pass
        try:
            rlevee_station, rlevee_value = [float(l) for l in levees[4:6]]
            ridx = bisect.bisect(stations, rlevee_station) - shift
            trim_elev = trim_elev[:ridx]
            trim_elev.append((rlevee_station, rlevee_value))
        except ValueError:
            pass
        first_station = trim_elev[0][0]
        new_elev = [(round(s - first_station, 3), e) for s, e in trim_elev]
        return llevee_station, rlevee_station, new_elev

    def get_ras_geometry(self):
        self.extract_xsections()
        return self.ras_geometry

    def extract_rivers(self):
        river_pattern = r'River Reach=(?P<river>[^,]+),(?P<reach>[^\n]+)[\n]' \
                        r'Reach XY=\s*(?P<length>\d+)[^\n]*(?P<points>[^a-zA-Z]+)'
        re_river = re.compile(river_pattern, re.M | re.S)
        river_results = re.finditer(re_river, self.geom_txt)
        endings = []
        for river_res in river_results:
            river_end = river_res.end()

            river_groups = river_res.groupdict()
            river_txt = river_groups['river']
            reach_txt = river_groups['reach']
            length_txt = river_groups['length']
            points_txt = river_groups['points']
            points_split = self.split_txt_data(points_txt, 64, 16)

            river = river_txt.strip().replace(' ', '_')
            reach = reach_txt.strip().replace(' ', '_')
            length = int(length_txt)
            points = list(zip_longest(*(iter(points_split),) * 2))
            if length == len(points):
                valid = True
            else:
                valid = False
            key = '{}_{}'.format(river, reach)
            values = {'river': river, 'reach': reach, 'points': points, 'valid': valid}
            self.ras_geometry[key] = values
            endings.append(river_end)

        indices = self.find_slices(endings)
        for key, (start, end) in zip(list(self.ras_geometry.keys()), indices):
            self.ras_geometry[key]['slice'] = slice(start, end)

    def extract_xsections(self):
        self.extract_rivers()
        xs_pattern = r'Type RM[^,]+,(?P<rm>[^,*]+)(?P<asterix>[*]?)\s*,.+?' \
                     r'XS GIS Cut Line=(?P<length>\d+)[^\n]*(?P<points>[^a-zA-Z]+)[^#]+' \
                     r'#Sta/Elev=\s*(?P<sta>\d+)[^\n]*(?P<elev>[^a-zA-Z#]+)' \
                     r'#Mann=(?P<man>[^a-zA-Z#]+)(?P<extra>[^/]+)'
        re_xs = re.compile(xs_pattern, re.M | re.S)
        for key, values in self.ras_geometry.items():
            s = values['slice']
            xs_data = OrderedDict()
            river_text = self.geom_txt[s]
            xs_results = chain(*(re.finditer(re_xs, txt) for txt in river_text.split('\n\n')))

            for xs_res in xs_results:
                xs_groups = xs_res.groupdict()
                if '*' in xs_groups['asterix'] and self.interpolated is False:
                    continue
                rm_txt = xs_groups['rm']
                length_txt = xs_groups['length']
                points_txt = xs_groups['points']
                sta_txt = xs_groups['sta']
                elev_txt = xs_groups['elev']
                man_txt = xs_groups['man']
                extra_txt = xs_groups['extra']

                points_split = self.split_txt_data(points_txt, 64, 16)
                elev_split = self.split_txt_data(elev_txt, 80, 8)

                rm = float(rm_txt)
                length = int(length_txt)
                points = list(zip_longest(*(iter(points_split),) * 2))
                sta = int(sta_txt)
                elev = list(zip_longest(*(iter(elev_split),) * 2))
                man = [float(n) for n in man_txt.replace(',', ' ').replace('.', ' ').split()]
                if length != len(points):
                    continue
                xs_key = '{}_{}'.format(key, rm)
                xs_data[xs_key] = {'rm': rm, 'points': points, 'sta': sta, 'elev': elev, 'man': man, 'extra': extra_txt}

            self.ras_geometry[key]['xs_data'] = xs_data
