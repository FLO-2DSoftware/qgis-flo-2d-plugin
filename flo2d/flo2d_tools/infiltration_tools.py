# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from math import log, exp
from grid_tools import poly2poly


class InfiltrationCalculator(object):

    def __init__(self, grid_lyr):
        self.grid_lyr = grid_lyr
        self.soil_lyr = None
        self.land_lyr = None
        self.curve_lyr = None
        self.combined_lyr = None

        # Soil fields
        self.xksat_fld = None
        self.rtimps_fld = None
        self.eff_fld = None
        self.soil_depth_fld = None

        # Land use fields
        self.saturation_fld = None
        self.vc_fld = None
        self.ia_fld = None
        self.rtimpl_fld = None

        # SCS (single) layer fields
        self.curve_fld = None

        # SCS (multiple) combined layers fields
        self.landsoil_fld = None
        self.cd_fld = None
        self.imp_fld = None

    def setup_green_ampt(
            self,
            soil,
            land,
            xksat_fld='XKSAT',
            rtimps_fld='field_4',
            eff_fld='field_5',
            soil_depth_fld='soil_depth',
            saturation_fld='field_6',
            vc_fld='field_5',
            ia_fld='field_3',
            rtimpl_fld='field_4'):

        self.soil_lyr = soil
        self.land_lyr = land

        # Soil fields
        self.xksat_fld = xksat_fld
        self.rtimps_fld = rtimps_fld
        self.eff_fld = eff_fld
        self.soil_depth_fld = soil_depth_fld

        # Land use fields
        self.saturation_fld = saturation_fld
        self.vc_fld = vc_fld
        self.ia_fld = ia_fld
        self.rtimpl_fld = rtimpl_fld

    def setup_scs_single(self, curve_lyr, curve_fld='CurveNum'):
        self.curve_lyr = curve_lyr
        self.curve_fld = curve_fld

    def setup_scs_multi(
            self,
            combined_lyr,
            landsoil_fld='LandSoil',
            cd_fld='cov_den',
            imp_fld='IMP'):

        self.combined_lyr = combined_lyr
        self.landsoil_fld = landsoil_fld
        self.cd_fld = cd_fld
        self.imp_fld = imp_fld

    def green_ampt_infiltration(self):
        grid_params = {}
        green_ampt = GreenAmpt()

        soil_values = poly2poly(
            self.grid_lyr,
            self.soil_lyr,
            None,
            self.xksat_fld,
            self.rtimps_fld,
            self.eff_fld,
            self.soil_depth_fld
        )
        for gid, values in soil_values:
            xksat_parts = [(row[0], row[-1]) for row in values]
            imp_parts = [(row[1] * 0.01, row[2] * 0.01, row[-1]) for row in values]
            avg_soil_depth = sum(row[3] * row[-1] for row in values)
            avg_xksat = green_ampt.calculate_xksat(xksat_parts)
            psif = green_ampt.calculate_psif(avg_xksat)
            rtimp_1 = green_ampt.calculate_rtimp_1(imp_parts)

            grid_params[gid] = {'hydc': avg_xksat, 'soils': psif, 'rtimpf': rtimp_1, 'soil_depth': avg_soil_depth}

        land_values = poly2poly(
            self.grid_lyr,
            self.land_lyr,
            None,
            self.saturation_fld,
            self.vc_fld,
            self.ia_fld,
            self.rtimpl_fld
        )
        for gid, values in land_values:
            params = grid_params[gid]
            avg_xksat = params['hydc']
            rtimp_1 = params['rtimpf']

            vc_parts = [(row[1], row[-1]) for row in values]
            ia_parts = [(row[2], row[-1]) for row in values]
            rtimp_parts = [(row[3] * 0.01, row[-1]) for row in values]

            dtheta = sum([green_ampt.calculate_dtheta(avg_xksat, row[0]) * row[-1] for row in values])
            xksatc = green_ampt.calculate_xksatc(avg_xksat, vc_parts)
            iabstr = green_ampt.calculate_iabstr(ia_parts)
            rtimp = green_ampt.calculate_rtimp(rtimp_1, rtimp_parts)

            params['dtheta'] = dtheta
            params['hydc'] = xksatc
            params['abstrinf'] = iabstr
            params['rtimpf'] = rtimp

        return grid_params

    def scs_infiltration_single(self):
        grid_params = {}
        curve_values = poly2poly(
            self.grid_lyr,
            self.curve_lyr,
            None,
            self.curve_fld)
        for gid, values in curve_values:
            grid_cn = sum(cn * subarea for cn, subarea in values)
            grid_params[gid] = {'scsn': grid_cn}

        return grid_params

    def scs_infiltration_multi(self):
        grid_params = {}
        scs = SCPCurveNumber()
        ground_values = poly2poly(
            self.grid_lyr,
            self.combined_lyr,
            None,
            self.landsoil_fld,
            self.cd_fld,
            self.imp_fld)
        for gid, values in ground_values:
            grid_cn = scs.calculate_scs_cn(values)
            grid_params[gid] = {'scsn': grid_cn}

        return grid_params


class GreenAmpt(object):

    @staticmethod
    def calculate_xksat(parts):
        xksat_gen = (area * log(xksat) for xksat, area in parts if xksat > 0)
        avg_xksat = exp(sum(xksat_gen))
        return avg_xksat

    @staticmethod
    def calculate_psif(avg_xksat):
        if 0.01 <= avg_xksat <= 1.2:
            psif = exp(0.9813 - 0.439 * log(avg_xksat) + 0.0051 * (log(avg_xksat))**2 + 0.0060 * (log(avg_xksat))**3)
            return psif
        else:
            raise ValueError

    @staticmethod
    def calculate_dtheta(avg_xksat, saturation):
        if saturation == 'dry':
            if 0.01 <= avg_xksat <= 0.15:
                dtheta = exp(-0.2394 + 0.3616 * log(avg_xksat))
            elif 0.15 < avg_xksat <= 0.25:
                dtheta = exp(-1.4122 - 0.2614 * log(avg_xksat))
            elif 0.25 < avg_xksat <= 1.2:
                dtheta = 0.35
            else:
                raise ValueError
        elif saturation == 'normal':
            if 0.01 <= avg_xksat <= 0.02:
                dtheta = exp(1.6094 + log(avg_xksat))
            elif 0.02 < avg_xksat <= 0.04:
                dtheta = exp(-0.0142 + 0.585 * log(avg_xksat))
            elif 0.04 < avg_xksat <= 0.1:
                dtheta = 0.15
            elif 0.1 < avg_xksat <= 0.15:
                dtheta = exp(1.0038 + 1.2599 * log(avg_xksat))
            elif 0.15 < avg_xksat <= 0.4:
                dtheta = 0.25
            elif 0.4 < avg_xksat <= 1.2:
                dtheta = exp(-1.2342 + 0.1660 * log(avg_xksat))
            else:
                raise ValueError
        elif saturation == 'wet' or saturation == 'saturated':
            dtheta = 0
        else:
            raise ValueError
        return dtheta

    @staticmethod
    def calculate_xksatc(avg_xksat, parts):
        if avg_xksat < 0.4:
            pc_gen = (((vc - 10) / 90 + 1) * area for vc, area in parts)
            xksatc = avg_xksat * sum(pc_gen)
        else:
            xksatc = avg_xksat
        return xksatc

    @staticmethod
    def calculate_iabstr(parts):
        iabstr_gen = (area * ia for ia, area in parts)
        iabstr = sum(iabstr_gen)
        return iabstr

    @staticmethod
    def calculate_rtimp_1(parts):
        rtimp_gen_1 = (area * (rtimps * eff) for rtimps, eff, area in parts)
        rtimp_1 = sum(rtimp_gen_1)
        return rtimp_1

    @staticmethod
    def calculate_rtimp(rtimp_1, parts):
        rtimp_gen = (area * rtimpl for rtimpl, area in parts)
        rtimp = rtimp_1 + sum(rtimp_gen)
        return rtimp


class SCPCurveNumber(object):

    def __init__(self):
        self.scs_calc = {
            'desert brush': self.calculate_desert_brush,
            'herbaceous': self.calculate_herbaceous,
            'mountain brush': self.calculate_mountain_brush,
            'juniper - grass': self.calculate_juniper_grass,
            'ponderosa pine': self.calculate_ponderosa_pine,
            'pervious - urban law': self.calculate_ponderosa_pine
        }

    def calculate_scs_cn(self, parts):
        partial_var = []
        for landsoil, cd, imp, subarea in parts:
            cd = float(cd)
            soil_group, hsc = landsoil.split(' ', 1)
            calc_method = self.scs_calc[hsc.lower()]
            if '%' in soil_group:
                cn = 0
                for sg_perc in soil_group.strip('%').split('%'):
                    sg = sg_perc[0]
                    perc = (float(sg_perc[1:]) * 0.01) * (1 - imp)
                    part_cn = calc_method(sg, cd) * perc
                    cn += part_cn
                cn += imp * 99
            else:
                perc = 1 * (1 - imp)
                cn = calc_method(soil_group, cd) * perc + imp * 99
            var = subarea * cn
            partial_var.append(var)
        grid_cn = sum(partial_var)
        return grid_cn

    @staticmethod
    def calculate_desert_brush(soil_group, cover_density):
        if soil_group == 'D':
            cn = -0.08 * cover_density + 93
        elif soil_group == 'C':
            cn = -0.08 * cover_density + 90
        elif soil_group == 'B':
            cn = -0.07 * cover_density + 84
        else:
            raise ValueError
        return cn

    @staticmethod
    def calculate_herbaceous(soil_group, cover_density):
        if soil_group == 'D':
            cn = -0.0875 * cover_density + 93
        elif soil_group == 'C':
            cn = -0.1875 * cover_density + 90
        elif soil_group == 'B':
            cn = -0.2625 * cover_density + 84
        else:
            raise ValueError
        return cn

    @staticmethod
    def calculate_mountain_brush(soil_group, cover_density):
        if soil_group == 'D':
            cn = -0.0013 * cover_density**2 + -0.1737 * cover_density + 95
        elif soil_group == 'C':
            cn = -0.0014 * cover_density**2 + -0.2942 * cover_density + 90
        elif soil_group == 'B':
            cn = -0.0025 * cover_density**2 + -0.3522 * cover_density + 83
        else:
            raise ValueError
        return cn

    @staticmethod
    def calculate_juniper_grass(soil_group, cover_density):
        if soil_group == 'D':
            cn = -0.1125 * cover_density + 93
        elif soil_group == 'C':
            cn = -0.34375 * cover_density + 90.5
        elif soil_group == 'B':
            cn = -0.525 * cover_density + 84
        else:
            raise ValueError
        return cn

    @staticmethod
    def calculate_ponderosa_pine(soil_group, cover_density):
        if 0 < cover_density <= 10:
            if soil_group == 'C':
                cn = -0.08 * cover_density**2 + -1.9 * cover_density + 91
            elif soil_group == 'B':
                cn = -0.1 * cover_density**2 + -2.4 * cover_density + 84
            else:
                raise ValueError
        elif 10 < cover_density <= 80:
            if soil_group == 'C':
                cn = -0.242857 * cover_density + 82.42857
            elif soil_group == 'B':
                cn = -0.3 * cover_density + 73
            else:
                raise ValueError
        else:
            raise ValueError
        return cn
