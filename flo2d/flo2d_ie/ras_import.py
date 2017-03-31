# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import re
from collections import OrderedDict
from itertools import izip_longest
from flo2d.geopackage_utils import GeoPackageUtils
from flo2d.flo2d_tools.schematic_conversion import remove_features
from qgis.core import QgsFeature, QgsGeometry, QgsPoint


class RASProject(GeoPackageUtils):

    def __init__(self, con, iface, lyrs, prj_path=None):
        super(RASProject, self).__init__(con, iface)
        self.lyrs = lyrs
        self.project_path = prj_path
        self.ras_geom = None
        self.ras_plan = None
        self.ras_flow = None

    def find_geometry(self):
        if self.project_path is None:
            return
        fname = self.project_path[:-3]
        with open(self.project_path, 'r') as project:
            project_text = project.read()
            plan_regex = re.compile(r'(?P<head>Current Plan=)(?P<geom>[^\r\n]+)')
            plan_result = re.search(plan_regex, project_text)
            plandict = plan_result.groupdict()
            self.ras_plan = '{}{}'.format(fname, plandict['geom'])
        with open(self.ras_plan, 'r') as plan:
            plan_text = plan.read()
            geom_regex = re.compile(r'(?P<head>Geom File=)(?P<geom>[^\r\n]+)')
            geom_result = re.search(geom_regex, plan_text)
            geomdict = geom_result.groupdict()
            self.ras_geom = '{}{}'.format(fname, geomdict['geom'])

    def get_geometry(self, geom_pth=None):
        if geom_pth is None:
            geom_pth = self.ras_geom
        geometry = RASGeometry(geom_pth)
        ras_geometry = geometry.get_ras_geometry()
        if ras_geometry:
            first_val = next(ras_geometry.itervalues())
            if not first_val['xs_data']:
                raise Exception
            return ras_geometry
        else:
            raise Exception

    def write_xsections(self, ras_geometry):
        user_lbank_lyr = self.lyrs.data['user_left_bank']['qlyr']
        user_xs_lyr = self.lyrs.data['user_xsections']['qlyr']
        remove_features(user_lbank_lyr)
        remove_features(user_xs_lyr)
        self.clear_tables('user_chan_n', 'user_xsec_n_data')
        river_fields = user_lbank_lyr.fields()
        xs_fields = user_xs_lyr.fields()
        xs_fid = self.get_max('user_xsections') + 1
        nxsecnum = self.get_max('user_chan_n', 'nxsecnum') + 1
        uchan_n_rows = []
        uxsec_n_rows = []
        user_lbank_lyr.startEditing()
        user_xs_lyr.startEditing()
        for river_name, data in ras_geometry.iteritems():
            river_polyline = []
            river_feat = QgsFeature()
            river_feat.setFields(river_fields)
            for xs_key, xs_data in data['xs_data'].iteritems():
                xs_points = xs_data['points']
                xs_polyline = [QgsPoint(float(x), float(y)) for x, y in xs_points]
                river_polyline.append(xs_polyline[0])
                xs_geom = QgsGeometry().fromPolyline(xs_polyline)
                xs_feat = QgsFeature()
                xs_feat.setFields(xs_fields)
                xs_feat.setGeometry(xs_geom)
                xs_feat.setAttribute('fid', xs_fid)
                xs_feat.setAttribute('type', 'N')
                xs_feat.setAttribute('name', xs_key)
                user_xs_lyr.addFeature(xs_feat)

                uchan_n_rows.append((xs_fid, nxsecnum, xs_key))
                xs_elev = xs_data['elev']
                for xi, yi in xs_elev:
                    uxsec_n_rows.append((nxsecnum, float(xi), float(yi)))
                xs_fid += 1
                nxsecnum += 1

            river_geom = QgsGeometry().fromPolyline(river_polyline)
            river_feat.setGeometry(river_geom)
            river_feat.setAttribute('name', river_name)
            user_lbank_lyr.addFeature(river_feat)
        cursor = self.con.cursor()
        cursor.executemany('INSERT INTO user_chan_n (user_xs_fid, nxsecnum, xsecname) VALUES (?,?,?);', uchan_n_rows)
        cursor.executemany('INSERT INTO user_xsec_n_data (chan_n_nxsecnum, xi, yi) VALUES (?,?,?);', uxsec_n_rows)
        self.con.commit()
        user_lbank_lyr.commitChanges()
        user_lbank_lyr.updateExtents()
        user_lbank_lyr.triggerRepaint()
        user_lbank_lyr.removeSelection()
        user_xs_lyr.commitChanges()
        user_xs_lyr.updateExtents()
        user_xs_lyr.triggerRepaint()
        user_xs_lyr.removeSelection()


class RASGeometry(object):

    def __init__(self, geom_path):
        self.geom_path = geom_path
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

    def get_ras_geometry(self):
        self.extract_xsections()
        return self.ras_geometry

    def extract_rivers(self):
        river_pattern = r'River Reach=(?P<river>[^,]+),(?P<reach>[^\r\n]+)[\r\n]' \
                        r'Reach XY=\s*(?P<length>\d+)[^\r\n]*(?P<points>[^a-zA-Z]+)'
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

            river = river_txt.strip()
            reach = reach_txt.strip()
            length = int(length_txt)
            points = list(izip_longest(*(iter(points_split),) * 2))
            if length == len(points):
                valid = True
            else:
                valid = False
            key = '{} {}'.format(river, reach)
            values = {'river': river, 'reach': reach, 'points': points, 'valid': valid}
            self.ras_geometry[key] = values
            endings.append(river_end)

        indices = self.find_slices(endings)
        for key, (start, end) in zip(self.ras_geometry.keys(), indices):
            self.ras_geometry[key]['slice'] = slice(start, end)

    def extract_xsections(self):
        self.extract_rivers()
        xs_pattern = r'Type RM[^,]+,(?P<rm>[^,]+),.+?' \
                     r'XS GIS Cut Line=(?P<length>\d+)[^\r\n]*(?P<points>[^a-zA-Z]+)[^#]+' \
                     r'#Sta/Elev=(?P<sta>\s*\d+)[^\r\n]*(?P<elev>[^a-zA-Z]+)' \
                     r'#Mann=(?P<man>[^a-zA-Z#]+)'
        re_xs = re.compile(xs_pattern, re.M | re.S)
        for key, values in self.ras_geometry.iteritems():
            s = values['slice']
            xs_results = re.finditer(re_xs, self.geom_txt[s])
            xs_data = OrderedDict()

            for xs_res in xs_results:
                xs_groups = xs_res.groupdict()

                rm_txt = xs_groups['rm']
                length_txt = xs_groups['length']
                points_txt = xs_groups['points']
                sta_txt = xs_groups['sta']
                elev_txt = xs_groups['elev']
                man_txt = xs_groups['man']

                points_split = self.split_txt_data(points_txt, 64, 16)
                elev_split = self.split_txt_data(elev_txt, 80, 8)

                rm = float(rm_txt)
                length = int(length_txt)
                points = list(izip_longest(*(iter(points_split),) * 2))
                sta = int(sta_txt)
                elev = list(izip_longest(*(iter(elev_split),) * 2))
                man = [float(n) for n in man_txt.replace(',', ' ').split()]
                if length != len(points):
                    continue
                xs_key = '{} {}'.format(key, rm)
                xs_data[xs_key] = {'rm': rm, 'points': points, 'sta': sta, 'elev': elev, 'man': man}
            self.ras_geometry[key]['xs_data'] = xs_data
