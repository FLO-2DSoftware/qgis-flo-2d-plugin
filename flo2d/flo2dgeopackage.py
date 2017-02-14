# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
from operator import itemgetter
from itertools import chain, groupby, izip
from flo2d_parser import ParseDAT
from geopackage_utils import GeoPackageUtils


class Flo2dGeoPackage(GeoPackageUtils):
    """
    Class for proper import and export FLO-2D data.
    """
    def __init__(self, con, iface):
        super(Flo2dGeoPackage, self).__init__(con, iface)
        self.parser = None
        self.cell_size = None
        self.buffer = None
        self.shrink = None
        self.chunksize = float('inf')

    def set_parser(self, fpath):
        self.parser = ParseDAT()
        self.parser.scan_project_dir(fpath)
        self.cell_size = self.parser.calculate_cellsize()
        if self.cell_size == 0:
            self.uc.bar_error('Cell size is 0 - something went wrong!')
        else:
            pass
        self.buffer = self.cell_size * 0.4
        self.shrink = self.cell_size * 0.95

    def import_cont_toler(self):
        sql = ['''INSERT OR REPLACE INTO cont (name, value) VALUES''', 2]
        mann = self.get_cont_par('MANNING')
        if not mann:
            mann = '0.05'
        else:
            pass
        self.clear_tables('cont')
        cont = self.parser.parse_cont()
        toler = self.parser.parse_toler()
        cont.update(toler)
        for option in cont:
            sql += [(option, cont[option])]
        sql += [('CELLSIZE', self.cell_size)]
        sql += [('MANNING', mann)]

        self.batch_execute(sql)

    def import_mannings_n_topo(self):
        sql = ['''INSERT INTO grid (fid, n_value, elevation, geom) VALUES''', 4]

        self.clear_tables('grid')
        data = self.parser.parse_mannings_n_topo()

        c = 0
        man = slice(0, 2)
        coords = slice(2, 4)
        elev = slice(4, None)
        for row in data:
            row = tuple(row)
            if c < self.chunksize:
                geom = ' '.join(row[coords])
                g = self.build_square(geom, self.cell_size)
                sql += [row[man] + row[elev] + (g,)]
                c += 1
            else:
                self.batch_execute(sql)
                c = 0
        if len(sql) > 2:
            self.batch_execute(sql)
        else:
            pass

    def import_inflow(self):
        cont_sql = ['''INSERT INTO cont (name, value) VALUES''', 2]
        inflow_sql = ['''INSERT INTO inflow (time_series_fid, ident, inoutfc) VALUES''', 3]
        cells_sql = ['''INSERT INTO inflow_cells (inflow_fid, grid_fid) VALUES''', 2]
        ts_sql = ['''INSERT INTO inflow_time_series (fid) VALUES''', 1]
        tsd_sql = ['''INSERT INTO inflow_time_series_data (series_fid, time, value, value2) VALUES''', 4]
        reservoirs_sql = ['''INSERT INTO reservoirs (grid_fid, wsel, geom) VALUES''', 3]

        self.clear_tables('inflow', 'inflow_cells', 'reservoirs', 'inflow_time_series', 'inflow_time_series_data')
        head, inf, res = self.parser.parse_inflow()
        cont_sql += [('IDEPLT', head['IDEPLT']), ('IHOURDAILY', head['IHOURDAILY'])]
        gids = res.keys()
        cells = self.grid_centroids(gids, buffers=True)
        for i, gid in enumerate(inf, 1):
            row = inf[gid]['row']
            inflow_sql += [(i, row[0], row[1])]
            cells_sql += [(i, gid)]
            ts_sql += [(i,)]
            for n in inf[gid]['time_series']:
                tsd_sql += [(i,) + tuple(n[1:])]

        for gid in res:
            row = res[gid]['row']
            wsel = row[-1] if len(row) == 3 else None
            reservoirs_sql += [(row[1], wsel, cells[gid])]

        self.batch_execute(cont_sql, ts_sql, inflow_sql, cells_sql, tsd_sql, reservoirs_sql)
        qry = '''UPDATE inflow SET name = 'Inflow ' ||  cast(fid as text);'''
        self.execute(qry)
        qry = '''UPDATE reservoirs SET name = 'Reservoir ' ||  cast(fid as text);'''
        self.execute(qry)

    def import_outflow(self):
        outflow_sql = ['''INSERT INTO outflow (chan_out, fp_out, hydro_out, chan_tser_fid, chan_qhpar_fid,
                                            chan_qhtab_fid, fp_tser_fid) VALUES''', 7]
        cells_sql = ['''INSERT INTO outflow_cells (outflow_fid, grid_fid) VALUES''', 2]
        qh_params_sql = ['''INSERT INTO qh_params (fid) VALUES''', 1]
        qh_params_data_sql = ['''INSERT INTO qh_params_data (params_fid, hmax, coef, exponent) VALUES''', 4]
        qh_tab_sql = ['''INSERT INTO qh_table (fid) VALUES''', 1]
        qh_tab_data_sql = ['''INSERT INTO qh_table_data (table_fid, depth, q) VALUES''', 3]
        ts_sql = ['''INSERT INTO outflow_time_series (fid) VALUES''', 1]
        ts_data_sql = ['''INSERT INTO outflow_time_series_data (series_fid, time, value) VALUES''', 3]

        self.clear_tables('outflow', 'outflow_cells', 'qh_params', 'qh_params_data', 'qh_table', 'qh_table_data',
                          'outflow_time_series', 'outflow_time_series_data')
        data = self.parser.parse_outflow()

        qh_params_fid = 0
        qh_tab_fid = 0
        ts_fid = 0
        fid = 1
        for gid, values in data.iteritems():
            chan_out = values['K']
            fp_out = values['O']
            hydro_out = values['hydro_out']
            chan_tser_fid, chan_qhpar_fid, chan_qhtab_fid, fp_tser_fid = [0] * 4
            if values['qh_params']:
                qh_params_fid += 1
                chan_qhpar_fid = qh_params_fid
                qh_params_sql += [(qh_params_fid,)]
                for row in values['qh_params']:
                    qh_params_data_sql += [(qh_params_fid,) + tuple(row)]
            else:
                pass
            if values['qh_data']:
                qh_tab_fid += 1
                chan_qhtab_fid = qh_tab_fid
                qh_tab_sql += [(qh_tab_fid,)]
                for row in values['qh_data']:
                    qh_tab_data_sql += [(qh_tab_fid,) + tuple(row)]
            else:
                pass
            if values['time_series']:
                ts_fid += 1
                if values['N'] == 1:
                    fp_tser_fid = ts_fid
                elif values['N'] == 2:
                    chan_tser_fid = ts_fid
                else:
                    pass
                ts_sql += [(ts_fid,)]
                for row in values['time_series']:
                    ts_data_sql += [(ts_fid,) + tuple(row)]
            else:
                pass
            outflow_sql += [(chan_out, fp_out, hydro_out, chan_tser_fid, chan_qhpar_fid, chan_qhtab_fid, fp_tser_fid)]
            cells_sql += [(fid, gid)]
            fid += 1

        self.batch_execute(qh_params_sql, qh_params_data_sql, qh_tab_sql, qh_tab_data_sql, ts_sql, ts_data_sql,
                           outflow_sql, cells_sql)
        type_qry = '''UPDATE outflow SET type = (CASE
                    WHEN (fp_out > 0 AND chan_out = 0 AND fp_tser_fid = 0) THEN 1
                    WHEN (fp_out = 0 AND chan_out > 0 AND chan_tser_fid = 0 AND
                          chan_qhpar_fid = 0 AND chan_qhtab_fid = 0) THEN 2
                    WHEN (fp_out > 0 AND chan_out > 0) THEN 3
                    WHEN (hydro_out > 0) THEN 4
                    WHEN (fp_out = 0 AND fp_tser_fid > 0) THEN 5
                    WHEN (chan_out = 0 AND chan_tser_fid > 0) THEN 6
                    WHEN (fp_out > 0 AND fp_tser_fid > 0) THEN 7
                    WHEN (chan_out > 0 AND chan_tser_fid > 0) THEN 8
                    -- WHEN (chan_qhpar_fid > 0) THEN 9 -- stage-disscharge qhpar
                    WHEN (chan_qhpar_fid > 0) THEN 10 -- depth-discharge qhpar
                    WHEN (chan_qhtab_fid > 0) THEN 11
                    ELSE 0
                END),
                name = 'Outflow ' ||  cast(fid as text);'''
        self.execute(type_qry)
        # update series and tables names
        ts_name_qry = '''UPDATE outflow_time_series SET name = 'Time series ' ||  cast(fid as text);'''
        self.execute(ts_name_qry)
        qhpar_name_qry = '''UPDATE qh_params SET name = 'Q(h) parameters ' ||  cast(fid as text);'''
        self.execute(qhpar_name_qry)
        qhtab_name_qry = '''UPDATE qh_table SET name = 'Q(h) table ' ||  cast(fid as text);'''
        self.execute(qhtab_name_qry)

    def import_rain(self):
        rain_sql = ['''INSERT INTO rain (time_series_fid, irainreal, irainbuilding, tot_rainfall,
                                         rainabs, irainarf, movingstrom, rainspeed, iraindir) VALUES''', 9]
        ts_sql = ['''INSERT INTO rain_time_series (fid) VALUES''', 1]
        tsd_sql = ['''INSERT INTO rain_time_series_data (series_fid, time, value) VALUES''', 3]
        rain_arf_sql = ['''INSERT INTO rain_arf_areas (rain_fid, arf, geom) VALUES''', 3]
        cells_sql = ['''INSERT INTO rain_arf_cells (rain_arf_area_fid, grid_fid, arf) VALUES''', 3]

        self.clear_tables('rain', 'rain_arf_areas', 'rain_arf_cells', 'rain_time_series', 'rain_time_series_data')
        options, time_series, rain_arf = self.parser.parse_rain()
        gids = (x[0] for x in rain_arf)
        cells = self.grid_centroids(gids)

        fid = 1
        fid_ts = 1

        rain_sql += [(fid_ts,) + tuple(options.values())]
        ts_sql += [(fid_ts,)]

        for row in time_series:
            dummy, time, value = row
            tsd_sql += [(fid_ts, time, value)]

        for i, row in enumerate(rain_arf, 1):
            gid, val = row
            rain_arf_sql += [(fid, val, self.build_buffer(cells[gid], self.buffer))]
            cells_sql += [(i, gid, val)]

        self.batch_execute(ts_sql, rain_sql, tsd_sql, rain_arf_sql, cells_sql)

    def import_infil(self):
        infil_params = ['infmethod', 'abstr', 'sati', 'satf', 'poros', 'soild', 'infchan', 'hydcall',
                        'soilall', 'hydcadj', 'hydcxx', 'scsnall', 'abstr1', 'fhortoni', 'fhortonf', 'decaya']
        infil_sql = ['INSERT INTO infil (' + ', '.join(infil_params) + ') VALUES', 16]
        infil_seg_sql = ['''INSERT INTO infil_chan_seg (chan_seg_fid, hydcx, hydcxfinal, soildepthcx) VALUES''', 4]
        infil_green_sql = ['''INSERT INTO infil_areas_green (geom, hydc, soils, dtheta,
                                                             abstrinf, rtimpf, soil_depth) VALUES''', 7]
        infil_scs_sql = ['''INSERT INTO infil_areas_scs (geom, scscn) VALUES''', 2]
        infil_horton_sql = ['''INSERT INTO infil_areas_horton (geom, fhorti, fhortf, deca) VALUES''', 4]
        infil_chan_sql = ['''INSERT INTO infil_areas_chan (geom, hydconch) VALUES''', 2]

        cells_green_sql = ['''INSERT INTO infil_cells_green (infil_area_fid, grid_fid) VALUES''', 2]
        cells_scs_sql = ['''INSERT INTO infil_cells_scs (infil_area_fid, grid_fid) VALUES''', 2]
        cells_horton_sql = ['''INSERT INTO infil_cells_horton (infil_area_fid, grid_fid) VALUES''', 2]
        chan_sql = ['''INSERT INTO infil_chan_elems (infil_area_fid, grid_fid) VALUES''', 2]

        sqls = {
            'F': [infil_green_sql, cells_green_sql],
            'S': [infil_scs_sql, cells_scs_sql],
            'H': [infil_horton_sql, cells_horton_sql],
            'C': [infil_chan_sql, chan_sql]
        }

        self.clear_tables('infil', 'infil_chan_seg',
                          'infil_areas_green', 'infil_areas_scs', 'infil_areas_horton ', 'infil_areas_chan',
                          'infil_cells_green', 'infil_cells_scs', 'infil_cells_horton', 'infil_chan_elems')
        data = self.parser.parse_infil()

        infil_sql += [tuple([data[k.upper()] if k.upper() in data else None for k in infil_params])]
        gids = (x[0] for x in chain(data['F'], data['S'], data['C'], data['H']))
        cells = self.grid_centroids(gids)

        for i, row in enumerate(data['R'], 1):
            infil_seg_sql += [(i,) + tuple(row)]

        for k in sqls:
            if len(data[k]) > 0:
                for i, row in enumerate(data[k], 1):
                    gid = row[0]
                    geom = self.build_square(cells[gid], self.shrink)
                    sqls[k][0] += [(geom,) + tuple(row[1:])]
                    sqls[k][-1] += [(i, gid)]
            else:
                pass

        self.batch_execute(infil_sql, infil_seg_sql, infil_green_sql, infil_scs_sql, infil_horton_sql, infil_chan_sql,
                           cells_green_sql, cells_scs_sql, cells_horton_sql, chan_sql)

    def import_evapor(self):
        evapor_sql = ['''INSERT INTO evapor (ievapmonth, iday, clocktime) VALUES''', 3]
        evapor_month_sql = ['''INSERT INTO evapor_monthly (month, monthly_evap) VALUES''', 2]
        evapor_hour_sql = ['''INSERT INTO evapor_hourly (month, hour, hourly_evap) VALUES''', 3]

        self.clear_tables('evapor', 'evapor_monthly', 'evapor_hourly')
        head, data = self.parser.parse_evapor()
        evapor_sql += [tuple(head)]
        for month in data:
            row = data[month]['row']
            time_series = data[month]['time_series']
            evapor_month_sql += [tuple(row)]
            for i, ts in enumerate(time_series, 1):
                evapor_hour_sql += [(month, i, ts)]

        self.batch_execute(evapor_sql, evapor_month_sql, evapor_hour_sql)

    def import_chan(self):
        chan_sql = ['''INSERT INTO chan (geom, depinitial, froudc, roughadj, isedn) VALUES''', 5]
        chan_elems_sql = ['''INSERT INTO chan_elems (geom, fid, seg_fid, nr_in_seg, rbankgrid, fcn, xlen, type) VALUES''', 8]
        chan_r_sql = ['''INSERT INTO chan_r (elem_fid, bankell, bankelr, fcw, fcd) VALUES''', 5]
        chan_v_sql = ['''INSERT INTO chan_v (elem_fid, bankell, bankelr, fcd, a1, a2, b1, b2, c1, c2,
                                             excdep, a11, a22, b11, b22, c11, c22) VALUES''', 17]
        chan_t_sql = ['''INSERT INTO chan_t (elem_fid, bankell, bankelr, fcw, fcd, zl, zr) VALUES''', 7]
        chan_n_sql = ['''INSERT INTO chan_n (elem_fid, nxsecnum, xsecname) VALUES''', 3]
        chan_wsel_sql = ['''INSERT INTO chan_wsel (istart, wselstart, iend, wselend) VALUES''', 4]
        chan_conf_sql = ['''INSERT INTO chan_confluences (geom, conf_fid, type, chan_elem_fid) VALUES''', 4]
        chan_e_sql = ['''INSERT INTO noexchange_chan_areas (geom) VALUES''', 1]
        elems_e_sql = ['''INSERT INTO noexchange_chan_elems (noex_area_fid, chan_elem_fid) VALUES''', 2]

        sqls = {
            'R': [chan_r_sql, 4, 7],
            'V': [chan_v_sql, 4, 6],
            'T': [chan_t_sql, 4, 7],
            'N': [chan_n_sql, 2, 3]
        }

        self.clear_tables('chan', 'chan_elems', 'chan_r', 'chan_v', 'chan_t', 'chan_n',
                          'chan_confluences', 'noexchange_chan_areas', 'noexchange_chan_elems', 'chan_wsel')
        segments, wsel, confluence, noexchange = self.parser.parse_chan()
        for i, seg in enumerate(segments, 1):
            xs = seg[-1]
            gids = []
            for ii, row in enumerate(xs, 1):
                char = row[0]
                gid = row[1]
                rbank = row[-1]
                geom = self.build_linestring([gid, rbank]) if int(rbank) > 0 else None
                sql, fcn_idx, xlen_idx = sqls[char]
                xlen = row.pop(xlen_idx)
                fcn = row.pop(fcn_idx)
                params = row[1:-1]
                gids.append(gid)
                chan_elems_sql += [(geom, gid, i, ii, rbank, fcn, xlen, char)]
                sql += [tuple(params)]
            options = seg[:-1]
            geom = self.build_linestring(gids)
            chan_sql += [(geom,) + tuple(options)]

        for row in wsel:
            chan_wsel_sql += [tuple(row)]

        for i, row in enumerate(confluence, 1):
            gid1, gid2 = row[1], row[2]
            cells = self.grid_centroids([gid1, gid2], buffers=True)

            geom1, geom2 = cells[gid1], cells[gid2]
            chan_conf_sql += [(geom1, i, 0, gid1)]
            chan_conf_sql += [(geom2, i, 1, gid2)]

        for i, row in enumerate(noexchange, 1):
            gid = row[-1]
            geom = self.grid_centroids([gid])[0]
            chan_e_sql += [(self.build_buffer(geom, self.buffer),)]
            elems_e_sql += [(i, gid)]

        self.batch_execute(chan_sql, chan_elems_sql, chan_r_sql, chan_v_sql, chan_t_sql, chan_n_sql,
                           chan_conf_sql, chan_e_sql, elems_e_sql, chan_wsel_sql)
        qry = '''UPDATE chan SET name = 'Channel ' ||  cast(fid as text);'''
        self.execute(qry)

    def import_xsec(self):
        xsec_sql = ['''INSERT INTO xsec_n_data (chan_n_nxsecnum, xi, yi) VALUES''', 3]
        self.clear_tables('xsec_n_data')
        data = self.parser.parse_xsec()
        for xsec in data:
            nr, nodes = xsec
            for row in nodes:
                xsec_sql += [(nr,) + tuple(row)]

        self.batch_execute(xsec_sql)

    def import_hystruc(self):
        hystruc_params = ['geom', 'type', 'structname', 'ifporchan', 'icurvtable', 'inflonod', 'outflonod', 'inoutcont',
                          'headrefel', 'clength', 'cdiameter']
        hystruc_sql = ['INSERT INTO struct (' + ', '.join(hystruc_params) + ') VALUES', 11]
        ratc_sql = ['''INSERT INTO rat_curves (struct_fid, hdepexc, coefq, expq, coefa, expa) VALUES''', 6]
        repl_ratc_sql = ['''INSERT INTO repl_rat_curves (struct_fid, repdep, rqcoef, rqexp, racoef, raexp) VALUES''', 6]
        ratt_sql = ['''INSERT INTO rat_table (struct_fid, hdepth, qtable, atable) VALUES''', 4]
        culvert_sql = ['''INSERT INTO culvert_equations (struct_fid, typec, typeen, culvertn, ke, cubase) VALUES''', 6]
        storm_sql = ['''INSERT INTO storm_drains (struct_fid, istormdout, stormdmax) VALUES''', 3]

        sqls = {
            'C': ratc_sql,
            'R': repl_ratc_sql,
            'T': ratt_sql,
            'F': culvert_sql,
            'D': storm_sql
        }

        self.clear_tables('struct', 'rat_curves', 'repl_rat_curves', 'rat_table', 'culvert_equations', 'storm_drains')
        data = self.parser.parse_hystruct()
        nodes = slice(3, 5)
        for i, hs in enumerate(data, 1):
            params = hs[:-1]
            elems = hs[-1]
            geom = self.build_linestring(params[nodes])
            typ = elems.keys()[0] if len(elems) == 1 else 'C'
            hystruc_sql += [(geom, typ) + tuple(params)]
            for char in elems.keys():
                for row in elems[char]:
                    sqls[char] += [(i,) + tuple(row)]

        self.batch_execute(hystruc_sql, ratc_sql, repl_ratc_sql, ratt_sql, culvert_sql, storm_sql)
        qry = '''UPDATE struct SET notes = 'imported';'''
        self.execute(qry)

    def import_street(self):
        general_sql = ['''INSERT INTO street_general (strman, istrflo, strfno, depx, widst) VALUES''', 5]
        streets_sql = ['''INSERT INTO streets (stname) VALUES''', 1]
        seg_sql = ['''INSERT INTO street_seg (geom, str_fid, igridn, depex, stman, elstr) VALUES''', 6]
        elem_sql = ['''INSERT INTO street_elems (seg_fid, istdir, widr) VALUES''', 3]

        sqls = {
            'N': streets_sql,
            'S': seg_sql,
            'W': elem_sql
        }

        self.clear_tables('street_general', 'streets', 'street_seg', 'street_elems')
        head, data = self.parser.parse_street()
        general_sql += [tuple(head)]
        seg_fid = 1
        for i, n in enumerate(data, 1):
            name = n[0]
            sqls['N'] += [(name,)]
            for s in n[-1]:
                gid = s[0]
                directions = []
                s_params = s[:-1]
                for w in s[-1]:
                    d = w[0]
                    directions.append(d)
                    sqls['W'] += [(seg_fid,) + tuple(w)]
                geom = self.build_multilinestring(gid, directions, self.cell_size)
                sqls['S'] += [(geom, i) + tuple(s_params)]
                seg_fid += 1

        self.batch_execute(general_sql, streets_sql, seg_sql, elem_sql)

    def import_arf(self):
        cont_sql = ['''INSERT INTO cont (name, value) VALUES''', 2]
        cells_sql = ['''INSERT INTO blocked_cells (geom, area_fid, grid_fid, arf,
                                                   wrf1, wrf2, wrf3, wrf4, wrf5, wrf6, wrf7, wrf8) VALUES''', 12]

        self.clear_tables('blocked_cells')
        head, data = self.parser.parse_arf()
        cont_sql += [('arfblockmod',) + tuple(head)]
        gids = (x[0] for x in chain(data['T'], data['PB']))
        cells = self.grid_centroids(gids, buffers=True)

        for i, row in enumerate(chain(data['T'], data['PB']), 1):
            gid = row[0]
            centroid = cells[gid]
            cells_sql += [(centroid, i) + tuple(row)]

        self.batch_execute(cont_sql, cells_sql)

    def import_mult(self):
        mult_sql = ['''INSERT INTO mult (wmc, wdrall, dmall, nodchansall,
                                         xnmultall, sslopemin, sslopemax, avuld50) VALUES''', 8]
        mult_area_sql = ['''INSERT INTO mult_areas (geom, wdr, dm, nodchns, xnmult) VALUES''', 5]
        cells_sql = ['''INSERT INTO mult_cells (area_fid, grid_fid) VALUES''', 2]

        self.clear_tables('mult', 'mult_areas', 'mult_cells')
        head, data = self.parser.parse_mult()
        mult_sql += [tuple(head)]
        gids = (x[0] for x in data)
        cells = self.grid_centroids(gids)
        for i, row in enumerate(data, 1):
            gid = row[0]
            geom = self.build_square(cells[gid], self.shrink)
            mult_area_sql += [(geom,) + tuple(row[1:])]
            cells_sql += [(i, gid)]

        self.batch_execute(mult_sql, mult_area_sql, cells_sql)

    def import_sed(self):
        sed_m_sql = ['''INSERT INTO mud (va, vb, ysa, ysb, sgsm, xkx) VALUES''', 6]
        sed_c_sql = ['''INSERT INTO sed (isedeqg, isedsizefrac, dfifty, sgrad, sgst, dryspwt,
                                         cvfg, isedsupply, isedisplay, scourdep) VALUES''', 10]
        sgf_sql = ['''INSERT INTO sed_group_frac (fid) VALUES''', 1]
        sed_z_sql = ['''INSERT INTO sed_groups (dist_fid, isedeqi, bedthick, cvfi) VALUES''', 4]
        sed_p_sql = ['''INSERT INTO sed_group_frac_data (dist_fid, sediam, sedpercent) VALUES''', 3]
        areas_d_sql = ['''INSERT INTO mud_areas (geom, debrisv) VALUES''', 2]
        cells_d_sql = ['''INSERT INTO mud_cells (area_fid, grid_fid) VALUES''', 2]
        areas_g_sql = ['''INSERT INTO sed_group_areas (geom, group_fid) VALUES''', 2]
        cells_g_sql = ['''INSERT INTO sed_group_cells (area_fid, grid_fid) VALUES''', 2]
        areas_r_sql = ['''INSERT INTO sed_rigid_areas (geom) VALUES''', 1]
        cells_r_sql = ['''INSERT INTO sed_rigid_cells (area_fid, grid_fid) VALUES''', 2]
        areas_s_sql = ['''INSERT INTO sed_supply_areas (geom, dist_fid, isedcfp, ased, bsed) VALUES''', 5]
        cells_s_sql = ['''INSERT INTO sed_supply_cells (area_fid, grid_fid) VALUES''', 2]
        sed_n_sql = ['''INSERT INTO sed_supply_frac (fid) VALUES''', 1]
        data_n_sql = ['''INSERT INTO sed_supply_frac_data (dist_fid, ssediam, ssedpercent) VALUES''', 3]

        parts = [
            ['D', areas_d_sql, cells_d_sql],
            ['G', areas_g_sql, cells_g_sql],
            ['R', areas_r_sql, cells_r_sql]
        ]

        self.clear_tables('mud', 'mud_areas', 'mud_cells', 'sed', 'sed_groups', 'sed_group_areas', 'sed_group_cells',
                          'sed_group_frac', 'sed_group_frac_data', 'sed_rigid_areas', 'sed_rigid_cells',
                          'sed_supply_areas', 'sed_supply_cells', 'sed_supply_frac', 'sed_supply_frac_data')

        data = self.parser.parse_sed()
        gids = (x[0] for x in chain(data['D'], data['G'], data['R'], data['S']))
        cells = self.grid_centroids(gids)
        for row in data['M']:
            sed_m_sql += [tuple(row)]
        for row in data['C']:
            erow = data['E'][0]
            if erow:
                row += erow
            else:
                row.append(None)
            sed_c_sql += [tuple(row)]
        for i, row in enumerate(data['Z'], 1):
            sgf_sql += [(i,)]
            sed_z_sql += [(i,) + tuple(row[:-1])]
            for prow in row[-1]:
                sed_p_sql += [(i,) + tuple(prow)]
        for char, asql, csql in parts:
            for i, row in enumerate(data[char], 1):
                gid = row[0]
                vals = row[1:]
                geom = self.build_square(cells[gid], self.shrink)
                asql += [(geom,) + tuple(vals)]
                csql += [(i, gid)]

        for i, row in enumerate(data['S'], 1):
            gid = row[0]
            vals = row[1:-1]
            nrows = row[-1]
            geom = self.build_square(cells[gid], self.shrink)
            areas_s_sql += [(geom, i) + tuple(vals)]
            cells_s_sql += [(i, gid)]
            for ii, nrow in enumerate(nrows, 1):
                sed_n_sql += [(ii,)]
                data_n_sql += [(i,) + tuple(nrow)]

        self.batch_execute(sed_m_sql, areas_d_sql, cells_d_sql, sed_c_sql, sgf_sql, sed_z_sql, areas_g_sql, cells_g_sql,
                           sed_p_sql, areas_r_sql, cells_r_sql, areas_s_sql, cells_s_sql, sed_n_sql, data_n_sql)

    def import_levee(self):
        lgeneral_sql = ['''INSERT INTO levee_general (raiselev, ilevfail, gfragchar, gfragprob) VALUES''', 4]
        ldata_sql = ['''INSERT INTO levee_data (geom, grid_fid, ldir, levcrest) VALUES''', 4]
        lfailure_sql = ['''INSERT INTO levee_failure (grid_fid, lfaildir, failevel, failtime,
                                                      levbase, failwidthmax, failrate, failwidrate) VALUES''', 8]
        lfragility_sql = ['''INSERT INTO levee_fragility (grid_fid, levfragchar, levfragprob) VALUES''', 3]

        self.clear_tables('levee_general', 'levee_data', 'levee_failure', 'levee_fragility')
        head, data = self.parser.parse_levee()

        lgeneral_sql += [tuple(head)]
        for gid, directions in data['L']:
            for row in directions:
                ldir, levcrest = row
                geom = self.build_levee(gid, ldir, self.cell_size)
                ldata_sql += [(geom, gid, ldir, levcrest)]
        for gid, directions in data['F']:
            for row in directions:
                lfailure_sql += [(gid,) + tuple(row)]

        for row in data['P']:
            lfragility_sql += [tuple(row)]

        self.batch_execute(lgeneral_sql, ldata_sql, lfailure_sql, lfragility_sql)

    def import_fpxsec(self):
        cont_sql = ['''INSERT INTO cont (name, value) VALUES''', 2]
        fpxsec_sql = ['''INSERT INTO fpxsec (geom, iflo, nnxsec) VALUES''', 3]
        cells_sql = ['''INSERT INTO fpxsec_cells (geom, fpxsec_fid, grid_fid) VALUES''', 3]

        self.clear_tables('fpxsec', 'fpxsec_cells')
        head, data = self.parser.parse_fpxsec()
        cont_sql += [('NXPRT', head)]
        for i, xs in enumerate(data, 1):
            params, gids = xs
            geom = self.build_linestring(gids)
            fpxsec_sql += [(geom,) + tuple(params)]
            for gid in gids:
                grid_geom = self.single_centroid(gid, buffers=True)
                cells_sql += [(grid_geom, i, gid)]

        self.batch_execute(cont_sql, fpxsec_sql, cells_sql)

    def import_breach(self):
        glob = [
            'ibreachsedeqn', 'gbratio', 'gweircoef', 'gbreachtime', 'gzu', 'gzd', 'gzc', 'gcrestwidth', 'gcrestlength',
            'gbrbotwidmax', 'gbrtopwidmax', 'gbrbottomel', 'gd50c', 'gporc', 'guwc', 'gcnc', 'gafrc', 'gcohc', 'gunfcc',
            'gd50s', 'gpors', 'guws', 'gcns', 'gafrs', 'gcohs', 'gunfcs', 'ggrasslength', 'ggrasscond', 'ggrassvmaxp',
            'gsedconmax', 'd50df', 'gunfcdf'
        ]
        local = [
            'geom', 'ibreachdir', 'zu', 'zd', 'zc', 'crestwidth', 'crestlength', 'brbotwidmax', 'brtopwidmax',
            'brbottomel', 'weircoef', 'd50c', 'porc', 'uwc', 'cnc', 'afrc', 'cohc', 'unfcc', 'd50s', 'pors', 'uws',
            'cns', 'afrs', 'cohs', 'unfcs', 'bratio', 'grasslength', 'grasscond', 'grassvmaxp', 'sedconmax', 'd50df',
            'unfcdf', 'breachtime'
        ]
        global_sql = ['INSERT INTO breach_global (' + ', '.join(glob) + ') VALUES', 32]
        local_sql = ['INSERT INTO breach (' + ', '.join(local) + ') VALUES', 33]
        cells_sql = ['''INSERT INTO breach_cells (breach_fid, grid_fid) VALUES''', 2]
        frag_sql = ['''INSERT INTO breach_fragility_curves (fragchar, prfail, prdepth) VALUES''', 3]

        self.clear_tables('breach_global', 'breach', 'breach_cells', 'breach_fragility_curves')
        data = self.parser.parse_breach()
        gids = (x[0] for x in data['D'])
        cells = self.grid_centroids(gids, buffers=True)
        for row in data['G']:
            global_sql += [tuple(row)]
        for i, row in enumerate(data['D'], 1):
            gid = row[0]
            geom = cells[gid]
            local_sql += [(geom,) + tuple(row[1:])]
            cells_sql += [(i, gid)]
        for row in data['F']:
            frag_sql += [tuple(row)]

        self.batch_execute(global_sql, local_sql, cells_sql, frag_sql)

    def import_fpfroude(self):
        fpfroude_sql = ['''INSERT INTO fpfroude (geom, froudefp) VALUES''', 2]
        cells_sql = ['''INSERT INTO fpfroude_cells (area_fid, grid_fid) VALUES''', 2]

        self.clear_tables('fpfroude', 'fpfroude_cells')
        data = self.parser.parse_fpfroude()
        gids = (x[0] for x in data)
        cells = self.grid_centroids(gids)
        for i, row in enumerate(data, 1):
            gid, froudefp = row
            geom = self.build_square(cells[gid], self.shrink)
            fpfroude_sql += [(geom, froudefp)]
            cells_sql += [(i, gid)]

        self.batch_execute(fpfroude_sql, cells_sql)

    def import_swmmflo(self):
        swmmflo_sql = ['''INSERT INTO swmmflo (geom, swmm_jt, intype, swmm_length,
                                               swmm_width, swmm_height, swmm_coeff, flapgate) VALUES''', 8]

        self.clear_tables('swmmflo')
        data = self.parser.parse_swmmflo()
        gids = (x[0] for x in data)
        cells = self.grid_centroids(gids)
        for row in data:
            gid = row[0]
            geom = self.build_square(cells[gid], self.shrink)
            swmmflo_sql += [(geom,) + tuple(row)]

        self.batch_execute(swmmflo_sql)

    def import_swmmflort(self):
        swmmflort_sql = ['''INSERT INTO swmmflort (grid_fid) VALUES''', 1]
        data_sql = ['''INSERT INTO swmmflort_data (swmm_rt_fid, depth, q) VALUES''', 3]

        self.clear_tables('swmmflort', 'swmmflort_data')
        data = self.parser.parse_swmmflort()
        for i, row in enumerate(data, 1):
            gid, params = row
            swmmflort_sql += [(gid,)]
            for n in params:
                data_sql += [(i,) + tuple(n)]

        self.batch_execute(swmmflort_sql, data_sql)

    def import_swmmoutf(self):
        swmmoutf_sql = ['''INSERT INTO swmmoutf (geom, name, grid_fid, outf_flo) VALUES''', 4]

        self.clear_tables('swmmoutf')
        data = self.parser.parse_swmmoutf()
        gids = (x[1] for x in data)
        cells = self.grid_centroids(gids)
        for row in data:
            gid = row[1]
            geom = self.build_square(cells[gid], self.shrink)
            swmmoutf_sql += [(geom,) + tuple(row)]

        self.batch_execute(swmmoutf_sql)

    def import_tolspatial(self):
        tolspatial_sql = ['''INSERT INTO tolspatial (geom, tol) VALUES''', 2]
        cells_sql = ['''INSERT INTO tolspatial_cells (area_fid, grid_fid) VALUES''', 2]

        self.clear_tables('tolspatial', 'tolspatial_cells')
        data = self.parser.parse_tolspatial()
        gids = (x[0] for x in data)
        cells = self.grid_centroids(gids)
        for i, row in enumerate(data, 1):
            gid, tol = row
            geom = self.build_square(cells[gid], self.shrink)
            tolspatial_sql += [(geom, tol)]
            cells_sql += [(i, gid)]

        self.batch_execute(tolspatial_sql, cells_sql)

    def import_wsurf(self):
        wsurf_sql = ['''INSERT INTO wsurf (geom, grid_fid, wselev) VALUES''', 3]

        self.clear_tables('wsurf')
        dummy, data = self.parser.parse_wsurf()
        gids = (x[0] for x in data)
        cells = self.grid_centroids(gids, buffers=True)
        for row in data:
            gid = row[0]
            geom = cells[gid]
            wsurf_sql += [(geom,) + tuple(row)]

        self.batch_execute(wsurf_sql)

    def import_wstime(self):
        wstime_sql = ['''INSERT INTO wstime (geom, grid_fid, wselev, wstime) VALUES''', 4]

        self.clear_tables('wstime')
        dummy, data = self.parser.parse_wstime()
        gids = (x[0] for x in data)
        cells = self.grid_centroids(gids, buffers=True)
        for row in data:
            gid = row[0]
            geom = cells[gid]
            wstime_sql += [(geom,) + tuple(row)]

        self.batch_execute(wstime_sql)

    def export_cont_toler(self, outdir):
        parser = ParseDAT()
        sql = '''SELECT name, value FROM cont;'''
        options = {o: v if v is not None else '' for o, v in self.execute(sql).fetchall()}
        cont = os.path.join(outdir, 'CONT.DAT')
        toler = os.path.join(outdir, 'TOLER.DAT')
        rline = ' {0}'
        with open(cont, 'w') as c:
            for row in parser.cont_rows:
                lst = ''
                for o in row:
                    val = options[o]
                    lst += rline.format(val)
                lst += '\n'
                if lst.isspace() is False:
                    c.write(lst)
                else:
                    pass

        with open(toler, 'w') as t:
            for row in parser.toler_rows:
                lst = ''
                for o in row:
                    val = options[o]
                    lst += rline.format(val)
                lst += '\n'
                if lst.isspace() is False:
                    t.write(lst)
                else:
                    pass

    def export_mannings_n_topo(self, outdir):
        sql = '''SELECT fid, n_value, elevation, ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM grid ORDER BY fid;'''
        records = self.execute(sql)
        mannings = os.path.join(outdir, 'MANNINGS_N.DAT')
        topo = os.path.join(outdir, 'TOPO.DAT')

        mline = '{0: >10} {1: >10}\n'
        tline = '{0: >15} {1: >15} {2: >10}\n'

        with open(mannings, 'w') as m, open(topo, 'w') as t:
            for row in records:
                fid, man, elev, geom = row
                x, y = geom.strip('POINT()').split()
                m.write(mline.format(fid, '{0:.3f}'.format(man)))
                t.write(tline.format('{0:.3f}'.format(float(x)), '{0:.3f}'.format(float(y)), '{0:.2f}'.format(elev)))

    def export_inflow(self, outdir):
        # check if there are any inflows defined
        if self.is_table_empty('inflow'):
            return
        cont_sql = '''SELECT value FROM cont WHERE name = ?;'''
        inflow_sql = '''SELECT fid, time_series_fid, ident, inoutfc FROM inflow WHERE fid = ?;'''
        inflow_cells_sql = '''SELECT inflow_fid, grid_fid FROM inflow_cells ORDER BY fid, grid_fid;'''
        ts_data_sql = '''SELECT time, value, value2 FROM inflow_time_series_data WHERE series_fid = ? ORDER BY fid;'''
        reservoirs_sql = '''SELECT grid_fid, wsel FROM reservoirs ORDER BY fid;'''

        head_line = ' {0: <15} {1}'
        inf_line = '\n{0: <15} {1: <15} {2}'
        tsd_line = '\nH              {0: <15} {1: <15} {2}'
        res_line = '\nR              {0: <15} {1}'

        idplt = self.execute(cont_sql, ('IDEPLT',)).fetchone()
        ihourdaily = self.execute(cont_sql, ('IHOURDAILY',)).fetchone()

        # TODO: Need to implement correct export for idplt and ihourdaily parameters
        if ihourdaily is None:
            ihourdaily = (0,)
        if idplt is None:
            first_gid = self.execute('''SELECT grid_fid FROM inflow_cells ORDER BY fid LIMIT 1;''').fetchone()
            idplt = first_gid if first_gid is not None else (0,)

        inflow = os.path.join(outdir, 'INFLOW.DAT')
        previous_iid = -1
        row = None
        with open(inflow, 'w') as i:
            i.write(head_line.format(ihourdaily[0], idplt[0]))
            for iid, gid in self.execute(inflow_cells_sql):

                if previous_iid != iid:
                    row = self.execute(inflow_sql, (iid,)).fetchone()
                    row = [x if x is not None else '' for x in row]
                    previous_iid = iid
                else:
                    pass

                fid, ts_fid, ident, inoutfc = row
                i.write(inf_line.format(ident, inoutfc, gid))
                series = self.execute(ts_data_sql, (ts_fid,))
                for tsd_row in series:
                    tsd_row = [x if x is not None else '' for x in tsd_row]
                    i.write(tsd_line.format(*tsd_row).rstrip())
            for res in self.execute(reservoirs_sql):
                res = [x if x is not None else '' for x in res]
                i.write(res_line.format(*res).rstrip())

    def export_outflow(self, outdir):
        # check if there are any outflows defined
        if self.is_table_empty('outflow'):
            return
        outflow_sql = '''
        SELECT fid, fp_out, chan_out, hydro_out, chan_tser_fid, chan_qhpar_fid, chan_qhtab_fid, fp_tser_fid
        FROM outflow WHERE fid = ?;'''
        outflow_cells_sql = '''SELECT outflow_fid, grid_fid FROM outflow_cells ORDER BY outflow_fid, grid_fid;'''
        qh_params_data_sql = '''SELECT hmax, coef, exponent FROM qh_params_data WHERE params_fid = ?;'''
        qh_table_data_sql = '''SELECT depth, q FROM qh_table_data WHERE table_fid = ? ORDER BY fid;'''
        ts_data_sql = '''SELECT time, value FROM outflow_time_series_data WHERE series_fid = ? ORDER BY fid;'''

        k_line = 'K  {0}\n'
        qh_params_line = 'H  {0}  {1}  {2}\n'
        qh_table_line = 'T  {0}  {1}\n'
        n_line = 'N     {0}  {1}\n'
        ts_line = 'S  {0}  {1}\n'
        o_line = '{0}  {1}\n'

        out_cells = self.execute(outflow_cells_sql).fetchall()
        if not out_cells:
            return
        else:
            pass
        outflow = os.path.join(outdir, 'OUTFLOW.DAT')
        floodplains = {}
        previous_oid = -1
        row = None

        with open(outflow, 'w') as o:
            for oid, gid in out_cells:

                if previous_oid != oid:
                    row = self.execute(outflow_sql, (oid,)).fetchone()
                    row = [x if x is not None else '' for x in row]
                    previous_oid = oid
                else:
                    pass

                fid, fp_out, chan_out, hydro_out, chan_tser_fid, chan_qhpar_fid, chan_qhtab_fid, fp_tser_fid = row
                if gid not in floodplains and (fp_out == 1 or hydro_out > 0):
                    floodplains[gid] = hydro_out
                if chan_out == 1:
                    o.write(k_line.format(gid))
                    for values in self.execute(qh_params_data_sql, (chan_qhpar_fid,)):
                        o.write(qh_params_line.format(*values))
                    for values in self.execute(qh_table_data_sql, (chan_qhtab_fid,)):
                        o.write(qh_table_line.format(*values))
                else:
                    pass
                if chan_tser_fid > 0 or fp_tser_fid > 0:
                    nostacfp = 0 if chan_tser_fid > 0 else 1
                    o.write(n_line.format(gid, nostacfp))
                    series_fid = chan_tser_fid if chan_tser_fid > 0 else fp_tser_fid
                    for values in self.execute(ts_data_sql, (series_fid,)):
                        o.write(ts_line.format(*values))
                else:
                    pass

            for gid, hydro_out in sorted(floodplains.iteritems(), key=lambda items: (items[1], items[0])):
                ident = 'O{0}'.format(hydro_out) if hydro_out > 0 else 'O'
                o.write(o_line.format(ident, gid))

    def export_rain(self, outdir):
        # check if there is any rain defined
        if self.is_table_empty('rain'):
            return
        rain_sql = '''SELECT time_series_fid, irainreal, irainbuilding, tot_rainfall,
                             rainabs, irainarf, movingstrom, rainspeed, iraindir
                      FROM rain;'''
        rain_cells_sql = '''SELECT grid_fid, arf FROM rain_arf_cells ORDER BY fid;'''
        ts_data_sql = '''SELECT time, value FROM rain_time_series_data WHERE series_fid = ? ORDER BY fid;'''

        rain_line1 = '{0}  {1}\n'
        rain_line2 = '{0}   {1}  {2}  {3}\n'
        rain_line4 = '{0}   {1}\n'
        tsd_line = 'R {0:.3f}   {1:.3f}\n'
        cell_line = '{0: <10} {1}\n'

        rain_row = self.execute(rain_sql).fetchone()
        if rain_row is None:
            return
        else:
            pass
        rain = os.path.join(outdir, 'RAIN.DAT')
        with open(rain, 'w') as r:
            fid = rain_row[0]
            r.write(rain_line1.format(*rain_row[1:3]))
            r.write(rain_line2.format(*rain_row[3:7]))
            for row in self.execute(ts_data_sql, (fid,)):
                r.write(tsd_line.format(*row))
            if rain_row[-1] is not None:
                r.write(rain_line4.format(*rain_row[-2:]))
            else:
                pass
            for row in self.execute(rain_cells_sql):
                r.write(cell_line.format(*row))

    def export_infil(self, outdir):
        # check if there is any infiltration defined
        if self.is_table_empty('infil'):
            return
        infil_sql = '''SELECT * FROM infil;'''
        infil_r_sql = '''SELECT hydcx, hydcxfinal, soildepthcx FROM infil_chan_seg ORDER BY chan_seg_fid, fid;'''
        iarea_green_sql = '''SELECT hydc, soils, dtheta, abstrinf, rtimpf, soil_depth FROM infil_areas_green WHERE fid = ?;'''
        icell_green_sql = '''SELECT grid_fid, infil_area_fid FROM infil_cells_green ORDER BY grid_fid;'''
        iarea_scs_sql = '''SELECT scscn FROM infil_areas_scs WHERE fid = ?;'''
        icell_scs_sql = '''SELECT grid_fid, infil_area_fid FROM infil_cells_scs ORDER BY grid_fid;'''
        iarea_horton_sql = '''SELECT fhorti, fhortf, deca FROM infil_areas_horton WHERE fid = ?;'''
        icell_horton_sql = '''SELECT grid_fid, infil_area_fid FROM infil_cells_horton ORDER BY grid_fid;'''
        iarea_chan_sql = '''SELECT hydconch FROM infil_areas_chan WHERE fid = ?;'''
        ielem_chan_sql = '''SELECT grid_fid, infil_area_fid FROM infil_chan_elems ORDER BY grid_fid;'''

        line1 = '{0}'
        line2 = '\n' + '  {}' * 6
        line3 = '\n' + '  {}' * 3
        line4 = '\n{0}'
        line4ab = '\nR  {0}  {1}  {2}'
        line5 = '\n{0}  {1}'
        line6 = '\n' + 'F' + '  {}' * 7
        line7 = '\nS  {0}  {1}'
        line8 = '\nC  {0}  {1}'
        line9 = '\nI  {0}  {1}  {2}'
        line10 = '\nH  {0}  {1}  {2}  {3}'

        infil_row = self.execute(infil_sql).fetchone()
        if infil_row is None:
            return
        else:
            pass
        infil = os.path.join(outdir, 'INFIL.DAT')
        with open(infil, 'w') as i:
            gen = [x if x is not None else '' for x in infil_row[1:]]
            v1, v2, v3, v4, v5, v9 = gen[0], gen[1:7], gen[7:10], gen[10:11], gen[11:13], gen[13:]
            i.write(line1.format(v1))
            for val, line in izip([v2, v3, v4], [line2, line3, line4]):
                if any(val) is True:
                    i.write(line.format(*val))
                else:
                    pass
            for row in self.execute(infil_r_sql):
                row = [x if x is not None else '' for x in row]
                i.write(line4ab.format(*row))
            if any(v5) is True:
                i.write(line5.format(*v5))
            else:
                pass
            for gid, iid in self.execute(icell_green_sql):
                for row in self.execute(iarea_green_sql, (iid,)):
                    i.write(line6.format(gid, *row))
            for gid, iid in self.execute(icell_scs_sql):
                for row in self.execute(iarea_scs_sql, (iid,)):
                    i.write(line7.format(gid, *row))
            for gid, iid in self.execute(ielem_chan_sql):
                for row in self.execute(iarea_chan_sql, (iid,)):
                    i.write(line8.format(gid, *row))
            if any(v9) is True:
                i.write(line9.format(*v9))
            else:
                pass
            for gid, iid in self.execute(icell_horton_sql):
                for row in self.execute(iarea_horton_sql, (iid,)):
                    i.write(line10.format(gid, *row))

    def export_evapor(self, outdir):
        # check if there is any evaporation defined
        if self.is_table_empty('evapor'):
            return
        evapor_sql = '''SELECT ievapmonth, iday, clocktime FROM evapor;'''
        evapor_month_sql = '''SELECT month, monthly_evap FROM evapor_monthly ORDER BY fid;'''
        evapor_hour_sql = '''SELECT hourly_evap FROM evapor_hourly WHERE month = ? ORDER BY fid;'''

        head = '{0}   {1}   {2:.2f}\n'
        monthly = '  {0}  {1:.2f}\n'
        hourly = '    {0:.4f}\n'

        evapor_row = self.execute(evapor_sql).fetchone()
        if evapor_row is None:
            return
        else:
            pass
        evapor = os.path.join(outdir, 'EVAPOR.DAT')
        with open(evapor, 'w') as e:
            e.write(head.format(*evapor_row))
            for mrow in self.execute(evapor_month_sql):
                month = mrow[0]
                e.write(monthly.format(*mrow))
                for hrow in self.execute(evapor_hour_sql, (month,)):
                    e.write(hourly.format(*hrow))

    def export_chan(self, outdir):
        # check if there are any channels defined
        if self.is_table_empty('chan'):
            return
        chan_sql = '''SELECT fid, depinitial, froudc, roughadj, isedn FROM chan ORDER BY fid;'''
        chan_elems_sql = '''SELECT fid, rbankgrid, fcn, xlen, type FROM chan_elems WHERE seg_fid = ? ORDER BY nr_in_seg;'''

        chan_r_sql = '''SELECT elem_fid, bankell, bankelr, fcw, fcd FROM chan_r WHERE elem_fid = ?;'''
        chan_v_sql = '''SELECT elem_fid, bankell, bankelr, fcd, a1, a2, b1, b2, c1, c2,
                               excdep, a11, a22, b11, b22, c11, c22 FROM chan_v WHERE elem_fid = ?;'''
        chan_t_sql = '''SELECT elem_fid, bankell, bankelr, fcw, fcd, zl, zr FROM chan_t WHERE elem_fid = ?;'''
        chan_n_sql = '''SELECT elem_fid, nxsecnum FROM chan_n WHERE elem_fid = ?;'''

        chan_wsel_sql = '''SELECT istart, wselstart, iend, wselend FROM chan_wsel ORDER BY fid;'''
        chan_conf_sql = '''SELECT chan_elem_fid FROM chan_confluences ORDER BY fid;'''
        chan_e_sql = '''SELECT chan_elem_fid FROM noexchange_chan_elems ORDER BY fid;'''

        segment = '   {0:.2f}   {1:.2f}   {2:.2f}   {3}\n'
        chan_r = 'R' + '  {}' * 7 + '\n'
        chan_v = 'V' + '  {}' * 19 + '\n'
        chan_t = 'T' + '  {}' * 9 + '\n'
        chan_n = 'N' + '  {}' * 4 + '\n'
        chanbank = ' {0: <10} {1}\n'
        wsel = '{0} {1:.2f}\n'
        conf = ' C {0}  {1}\n'
        chan_e = ' E {0}\n'

        sqls = {
            'R': [chan_r_sql, chan_r, 3, 6],
            'V': [chan_v_sql, chan_v, 3, 5],
            'T': [chan_t_sql, chan_t, 3, 6],
            'N': [chan_n_sql, chan_n, 1, 2]
        }

        chan_rows = self.execute(chan_sql).fetchall()
        if not chan_rows:
            return
        else:
            pass
        chan = os.path.join(outdir, 'CHAN.DAT')
        bank = os.path.join(outdir, 'CHANBANK.DAT')

        with open(chan, 'w') as c, open(bank, 'w') as b:
            for row in chan_rows:
                row = [x if x is not None else '' for x in row]
                fid = row[0]
                c.write(segment.format(*row[1:]))
                for elems in self.execute(chan_elems_sql, (fid,)):
                    elems = [x if x is not None else '' for x in elems]
                    eid, rbank, fcn, xlen, typ = elems
                    sql, line, fcn_idx, xlen_idx = sqls[typ]
                    res = [x if x is not None else '' for x in self.execute(sql, (eid,)).fetchone()]
                    res.insert(fcn_idx, fcn)
                    res.insert(xlen_idx, xlen)
                    c.write(line.format(*res))
                    b.write(chanbank.format(eid, rbank))

            for row in self.execute(chan_wsel_sql):
                c.write(wsel.format(*row[:2]))
                c.write(wsel.format(*row[2:]))

            pairs = []
            for row in self.execute(chan_conf_sql):
                chan_elem = row[0]
                if not pairs:
                    pairs.append(chan_elem)
                else:
                    pairs.append(chan_elem)
                    c.write(conf.format(*pairs))
                    del pairs[:]

            for row in self.execute(chan_e_sql):
                c.write(chan_e.format(row[0]))

    def export_xsec(self, outdir):
        chan_n_sql = '''SELECT nxsecnum, xsecname FROM chan_n ORDER BY nxsecnum;'''
        xsec_sql = '''SELECT xi, yi FROM xsec_n_data WHERE chan_n_nxsecnum = ? ORDER BY fid;'''

        xsec_line = '''X     {0}  {1}\n'''
        pkt_line = ''' {0:<10} {1: >10}\n'''
        nr = '{0:.2f}'

        chan_n = self.execute(chan_n_sql).fetchall()
        if not chan_n:
            return
        else:
            pass
        xsec = os.path.join(outdir, 'XSEC.DAT')
        with open(xsec, 'w') as x:
            for nxecnum, xsecname in chan_n:
                x.write(xsec_line.format(nxecnum, xsecname))
                for xi, yi in self.execute(xsec_sql, (nxecnum,)):
                    x.write(pkt_line.format(nr.format(xi), nr.format(yi)))

    def export_hystruc(self, outdir):
        # check if there is any hydraulic structure defined
        if self.is_table_empty('struct'):
            return
        hystruct_sql = '''SELECT * FROM struct ORDER BY fid;'''
        ratc_sql = '''SELECT * FROM rat_curves WHERE struct_fid = ? ORDER BY fid;'''
        repl_ratc_sql = '''SELECT * FROM repl_rat_curves WHERE struct_fid = ? ORDER BY fid;'''
        ratt_sql = '''SELECT * FROM rat_table WHERE struct_fid = ? ORDER BY fid;'''
        culvert_sql = '''SELECT * FROM culvert_equations WHERE struct_fid = ? ORDER BY fid;'''
        storm_sql = '''SELECT * FROM storm_drains WHERE struct_fid = ? ORDER BY fid;'''

        line1 = 'S' + '  {}' * 9 + '\n'
        line2 = 'C' + '  {}' * 5 + '\n'
        line3 = 'R' + '  {}' * 5 + '\n'
        line4 = 'T' + '  {}' * 3 + '\n'
        line5 = 'F' + '  {}' * 5 + '\n'
        line6 = 'D' + '  {}' * 2 + '\n'

        pairs = [
            [ratc_sql, line2],
            [repl_ratc_sql, line3],
            [ratt_sql, line4],
            [culvert_sql, line5],
            [storm_sql, line6]
            ]

        hystruc_rows = self.execute(hystruct_sql).fetchall()
        if not hystruc_rows:
            return
        else:
            pass
        hystruc = os.path.join(outdir, 'HYSTRUC.DAT')
        with open(hystruc, 'w') as h:
            for stru in hystruc_rows:
                fid = stru[0]
                vals = [x if x is not None else '' for x in stru[2:-2]]
                h.write(line1.format(*vals))
                for qry, line in pairs:
                    for row in self.execute(qry, (fid,)):
                        subvals = [x if x is not None else '' for x in row[2:]]
                        h.write(line.format(*subvals))

    def export_street(self, outdir):
        # check if there is any street defined
        if self.is_table_empty('streets'):
            return
        street_gen_sql = '''SELECT * FROM street_general ORDER BY fid;'''
        streets_sql = '''SELECT stname FROM streets ORDER BY fid;'''
        streets_seg_sql = '''SELECT igridn, depex, stman, elstr FROM street_seg WHERE str_fid = ? ORDER BY fid;'''
        streets_elem_sql = '''SELECT istdir, widr FROM street_elems WHERE seg_fid = ? ORDER BY fid;'''

        line1 = '  {}' * 5 + '\n'
        line2 = ' N {}\n'
        line3 = ' S' + '  {}' * 4 + '\n'
        line4 = ' W' + '  {}' * 2 + '\n'

        head = self.execute(street_gen_sql).fetchone()
        if head is None:
            return
        else:
            pass
        street = os.path.join(outdir, 'STREET.DAT')
        with open(street, 'w') as s:
            s.write(line1.format(*head[1:]))
            seg_fid = 1
            for i, sts in enumerate(self.execute(streets_sql), 1):
                s.write(line2.format(*sts))
                for seg in self.execute(streets_seg_sql, (i,)):
                    s.write(line3.format(*seg))
                    for elem in self.execute(streets_elem_sql, (seg_fid,)):
                        s.write(line4.format(*elem))
                    seg_fid += 1

    def export_arf(self, outdir):
        # check if there are any grid cells with ARF defined
        if self.is_table_empty('arfwrf'):
            return
        cont_sql = '''SELECT name, value FROM cont WHERE name = 'arfblockmod';'''
        tbc_sql = '''SELECT grid_fid FROM blocked_cells WHERE arf = 1 ORDER BY grid_fid;'''
        pbc_sql = '''SELECT grid_fid, arf, wrf1, wrf2, wrf3, wrf4, wrf5, wrf6, wrf7, wrf8
                     FROM blocked_cells WHERE arf < 1 ORDER BY grid_fid;'''

        line1 = 'S  {}\n'
        line2 = ' T   {}\n'
        line3 = '   {}' * 10 + '\n'

        option = self.execute(cont_sql).fetchone()
        if option is None:
            # TODO: We need to implement correct export of 'arfblockmod'
            option = ('arfblockmod', 0)

        arf = os.path.join(outdir, 'ARF.DAT')
        with open(arf, 'w') as a:
            head = option[-1]
            if head is not None:
                a.write(line1.format(head))
            else:
                pass
            for row in self.execute(tbc_sql):
                a.write(line2.format(*row))
            for row in self.execute(pbc_sql):
                row = [x if x is not None else '' for x in row]
                a.write(line3.format(*row))

    def export_mult(self, outdir):
        # check if there is any multiple channel defined
        if self.is_table_empty('mult'):
            return
        mult_sql = '''SELECT * FROM mult;'''
        mult_cell_sql = '''SELECT grid_fid, area_fid FROM mult_cells ORDER BY grid_fid;'''
        mult_area_sql = '''SELECT wdr, dm, nodchns, xnmult FROM mult_areas WHERE fid = ?;'''

        line1 = ' {}' * 8 + '\n'
        line2 = ' {}' * 5 + '\n'

        head = self.execute(mult_sql).fetchone()
        if head is None:
            return
        else:
            pass
        mult = os.path.join(outdir, 'MULT.DAT')
        with open(mult, 'w') as m:
            m.write(line1.format(*head[1:]).replace('None', ''))
            for gid, aid in self.execute(mult_cell_sql):
                for row in self.execute(mult_area_sql, (aid,)):
                    vals = [x if x is not None else '' for x in row]
                    m.write(line2.format(gid, *vals))

    def export_sed(self, outdir):
        # check if there is any sedimentation data defined
        if self.is_table_empty('mud') and self.is_table_empty('sed'):
            return
        sed_m_sql = '''SELECT va, vb, ysa, ysb, sgsm, xkx FROM mud ORDER BY fid;'''
        sed_ce_sql = '''SELECT isedeqg, isedsizefrac, dfifty, sgrad, sgst, dryspwt, cvfg, isedsupply, isedisplay, scourdep
                        FROM sed ORDER BY fid;'''
        sed_z_sql = '''SELECT dist_fid, isedeqi, bedthick, cvfi FROM sed_groups ORDER BY dist_fid;'''
        sed_p_sql = '''SELECT sediam, sedpercent FROM sed_group_frac_data WHERE dist_fid = ? ORDER BY sedpercent;'''
        areas_d_sql = '''SELECT fid, debrisv FROM mud_areas ORDER BY fid;'''
        cells_d_sql = '''SELECT grid_fid FROM mud_cells WHERE area_fid = ? ORDER BY grid_fid;'''
        cells_r_sql = '''SELECT grid_fid FROM sed_rigid_cells ORDER BY grid_fid;'''
        areas_s_sql = '''SELECT fid, dist_fid, isedcfp, ased, bsed FROM sed_supply_areas ORDER BY dist_fid;'''
        cells_s_sql = '''SELECT grid_fid FROM sed_supply_cells WHERE area_fid = ?;'''
        data_n_sql = '''SELECT ssediam, ssedpercent FROM sed_supply_frac_data WHERE dist_fid = ? ORDER BY ssedpercent;'''
        areas_g_sql = '''SELECT fid, group_fid FROM sed_group_areas ORDER BY fid;'''
        cells_g_sql = '''SELECT grid_fid FROM sed_group_cells WHERE area_fid = ? ORDER BY grid_fid;'''

        line1 = 'M  {0}  {1}  {2}  {3}  {4}  {5}\n'
        line2 = 'C  {0}  {1}  {2}  {3}  {4}  {5}  {6}\n'
        line3 = 'Z  {0}  {1}  {2}\n'
        line4 = 'P  {0}  {1}\n'
        line5 = 'D  {0}  {1}\n'
        line6 = 'E  {0}\n'
        line7 = 'R  {0}\n'
        line8 = 'S  {0}  {1}  {2}  {3}\n'
        line9 = 'N  {0}  {1}\n'
        line10 = 'G  {0}  {1}\n'

        m_data = self.execute(sed_m_sql).fetchone()
        ce_data = self.execute(sed_ce_sql).fetchone()
        if m_data is None and ce_data is None:
            return
        else:
            pass
        sed = os.path.join(outdir, 'SED.DAT')
        with open(sed, 'w') as s:
            if m_data is not None:
                s.write(line1.format(*m_data))
                e_data = None
            else:
                e_data = ce_data[-1]
                s.write(line2.format(*ce_data[:-1]))
            for row in self.execute(sed_z_sql):
                dist_fid = row[0]
                s.write(line3.format(*row[1:]))
                for prow in self.execute(sed_p_sql, (dist_fid,)):
                    s.write(line4.format(*prow))
            for aid, debrisv in self.execute(areas_d_sql):
                gid = self.execute(cells_d_sql, (aid,)).fetchone()[0]
                s.write(line5.format(gid, debrisv))
            if e_data is not None:
                s.write(line6.format(e_data))
            else:
                pass
            for row in self.execute(cells_r_sql):
                s.write(line7.format(*row))
            for row in self.execute(areas_s_sql):
                aid = row[0]
                dist_fid = row[1]
                gid = self.execute(cells_s_sql, (aid,)).fetchone()[0]
                s.write(line8.format(gid, *row[1:]))
                for nrow in self.execute(data_n_sql, (dist_fid,)):
                    s.write(line9.format(*nrow))
            for aid, group_fid in self.execute(areas_g_sql):
                gid = self.execute(cells_g_sql, (aid,)).fetchone()[0]
                s.write(line10.format(gid, group_fid))

    def export_levee(self, outdir):
        # check if there are any levees defined
        if self.is_table_empty('levee_data'):
            return
        levee_gen_sql = '''SELECT raiselev, ilevfail, gfragchar, gfragprob FROM levee_general;'''
        levee_data_sql = '''SELECT grid_fid, ldir, levcrest FROM levee_data ORDER BY grid_fid, fid;'''
        levee_fail_sql = '''SELECT * FROM levee_failure ORDER BY grid_fid, fid;'''
        levee_frag_sql = '''SELECT grid_fid, levfragchar, levfragprob FROM levee_fragility ORDER BY grid_fid;'''

        line1 = '{0}  {1}\n'
        line2 = 'L  {0}\n'
        line3 = 'D  {0}  {1}\n'
        line4 = 'F  {0}\n'
        line5 = 'W  {0}  {1}  {2}  {3}  {4}  {5}\n'
        line6 = 'C  {0}  {1}\n'
        line7 = 'P  {0}  {1}  {2}\n'

        general = self.execute(levee_gen_sql).fetchone()
        if general is None:
            # TODO: Need to implement correct export for levee_general, levee_failure and levee_fragility
            general = (0, 0, None, None)
        head = general[:2]
        glob_frag = general[2:]
        levee = os.path.join(outdir, 'LEVEE.DAT')
        with open(levee, 'w') as l:
            l.write(line1.format(*head))
            levee_rows = groupby(self.execute(levee_data_sql), key=itemgetter(0))
            for gid, directions in levee_rows:
                l.write(line2.format(gid))
                for row in directions:
                    l.write(line3.format(*row[1:]))
            fail_rows = groupby(self.execute(levee_fail_sql), key=itemgetter(1))
            for gid, directions in fail_rows:
                l.write(line4.format(gid))
                for row in directions:
                    l.write(line5.format(*row[2:]))
            if None not in glob_frag:
                l.write(line6.format(*glob_frag))
            else:
                pass
            for row in self.execute(levee_frag_sql):
                l.write(line7.format(*row))

    def export_fpxsec(self, outdir):
        # check if there are any floodplain cross section defined
        if self.is_table_empty('fpxsec'):
            return
        cont_sql = '''SELECT name, value FROM cont WHERE name = 'NXPRT';'''
        fpxsec_sql = '''SELECT fid, iflo, nnxsec FROM fpxsec ORDER BY fid;'''
        cell_sql = '''SELECT grid_fid FROM fpxsec_cells WHERE fpxsec_fid = ? ORDER BY grid_fid;'''

        line1 = 'P  {}\n'
        line2 = 'X {0} {1} {2}\n'

        option = self.execute(cont_sql).fetchone()
        if option is None:
            return
        else:
            pass
        fpxsec = os.path.join(outdir, 'FPXSEC.DAT')
        with open(fpxsec, 'w') as f:
            head = option[-1]
            f.write(line1.format(head))

            for row in self.execute(fpxsec_sql):
                fid, iflo, nnxsec = row
                grids = self.execute(cell_sql, (fid,))
                grids_txt = ' '.join(['{}'.format(x[0]) for x in grids])
                f.write(line2.format(iflo, nnxsec, grids_txt))

    def export_breach(self, outdir):
        # check if there is any breach defined
        if self.is_table_empty('breach'):
            return
        global_sql = '''SELECT * FROM breach_global ORDER BY fid;'''
        local_sql = '''SELECT * FROM breach ORDER BY fid;'''
        cells_sql = '''SELECT grid_fid FROM breach_cells WHERE breach_fid = ?;'''
        frag_sql = '''SELECT fragchar, prfail, prdepth FROM breach_fragility_curves ORDER BY fid;'''

        b1, g1, g2, g3, g4 = slice(1, 5), slice(5, 13), slice(13, 20), slice(20, 27), slice(27, 33)
        b2, d1, d2, d3, d4 = slice(0, 2), slice(2, 11), slice(11, 18), slice(18, 25), slice(25, 33)

        bline = 'B{0} {1}\n'
        line_1 = '{0}1 {1}\n'
        line_2 = '{0}2 {1}\n'
        line_3 = '{0}3 {1}\n'
        line_4 = '{0}4 {1}\n'
        fline = 'F {0} {1} {2}\n'

        parts = [
            [g1, d1, line_1],
            [g2, d2, line_2],
            [g3, d3, line_3],
            [g4, d4, line_4]
        ]

        global_rows = self.execute(global_sql).fetchall()
        local_rows = self.execute(local_sql).fetchall()
        if not global_rows and not local_rows:
            return
        else:
            pass
        breach = os.path.join(outdir, 'BREACH.DAT')
        with open(breach, 'w') as b:
            c = 1
            for row in global_rows:
                row_slice = [str(x) if x is not None else '' for x in row[b1]]
                b.write(bline.format(c, ' '.join(row_slice)))
                for gslice, dslice, line in parts:
                    row_slice = [str(x) if x is not None else '' for x in row[gslice]]
                    if any(row_slice) is True:
                        b.write(line.format('G', '  '.join(row_slice)))
                    else:
                        pass
                c += 1
            for row in local_rows:
                fid = row[0]
                gid = self.execute(cells_sql, (fid,)).fetchone()[0]
                row_slice = [str(x) if x is not None else '' for x in row[b2]]
                row_slice[0] = str(gid)
                b.write(bline.format(c, ' '.join(row_slice)))
                for gslice, dslice, line in parts:
                    row_slice = [str(x) if x is not None else '' for x in row[dslice]]
                    if any(row_slice) is True:
                        b.write(line.format('D', '  '.join(row_slice)))
                    else:
                        pass
                c += 1
            for row in self.execute(frag_sql):
                b.write(fline.format(*row))

    def export_fpfroude(self, outdir):
        # check if there is any limiting Froude number defined
        if self.is_table_empty('fpfroude'):
            return
        fpfroude_sql = '''SELECT fid, froudefp FROM fpfroude ORDER BY fid;'''
        cell_sql = '''SELECT grid_fid FROM fpfroude_cells WHERE area_fid = ? ORDER BY grid_fid;'''

        line1 = 'F {0} {1}\n'

        fpfroude_rows = self.execute(fpfroude_sql).fetchall()
        if not fpfroude_rows:
            return
        else:
            pass
        fpfroude = os.path.join(outdir, 'FPFROUDE.DAT')
        with open(fpfroude, 'w') as f:
            for fid, froudefp in fpfroude_rows:
                gid = self.execute(cell_sql, (fid,)).fetchone()[0]
                f.write(line1.format(gid, froudefp))

    def export_swmmflo(self, outdir):
        # check if there is any SWMM data defined
        if self.is_table_empty('swmmflo'):
            return
        swmmflo_sql = '''SELECT swmm_jt, intype, swmm_length, swmm_width, swmm_height, swmm_coeff, flapgate
                         FROM swmmflo ORDER BY fid;'''

        line1 = 'D  {0} {1} {2} {3} {4} {5} {6}\n'

        swmmflo_rows = self.execute(swmmflo_sql).fetchall()
        if not swmmflo_rows:
            return
        else:
            pass
        swmmflo = os.path.join(outdir, 'SWMMFLO.DAT')
        with open(swmmflo, 'w') as s:
            for row in swmmflo_rows:
                s.write(line1.format(*row))

    def export_swmmflort(self, outdir):
        # check if there is any SWMM rating data defined
        if self.is_table_empty('swmmflort'):
            return
        swmmflort_sql = '''SELECT fid, grid_fid FROM swmmflort ORDER BY grid_fid;'''
        data_sql = '''SELECT depth, q FROM swmmflort_data WHERE swmm_rt_fid = ? ORDER BY depth;'''

        line1 = 'D {0}\n'
        line2 = 'N {0}  {1}\n'

        swmmflort_rows = self.execute(swmmflort_sql).fetchall()
        if not swmmflort_rows:
            return
        else:
            pass
        swmmflort = os.path.join(outdir, 'SWMMFLORT.DAT')
        with open(swmmflort, 'w') as s:
            for fid, gid in swmmflort_rows:
                s.write(line1.format(gid))
                for row in self.execute(data_sql, (fid,)):
                    s.write(line2.format(*row))

    def export_swmmoutf(self, outdir):
        # check if there is any SWMM data defined
        if self.is_table_empty('swmmoutf'):
            return
        swmmoutf_sql = '''SELECT name, grid_fid, outf_flo FROM swmmoutf ORDER BY fid;'''

        line1 = '{0}  {1}  {2}\n'

        swmmoutf_rows = self.execute(swmmoutf_sql).fetchall()
        if not swmmoutf_rows:
            return
        else:
            pass
        swmmoutf = os.path.join(outdir, 'SWMMOUTF.DAT')
        with open(swmmoutf, 'w') as s:
            for row in swmmoutf_rows:
                s.write(line1.format(*row))

    def export_tolspatial(self, outdir):
        # check if there is any tolerance data defined
        if self.is_table_empty('tolspatial'):
            return
        tolspatial_sql = '''SELECT fid, tol FROM tolspatial ORDER BY fid;'''
        cell_sql = '''SELECT grid_fid FROM tolspatial_cells WHERE area_fid = ? ORDER BY grid_fid;'''

        line1 = '{0}  {1}\n'

        tolspatial_rows = self.execute(tolspatial_sql).fetchall()
        if not tolspatial_rows:
            return
        else:
            pass
        tolspatial = os.path.join(outdir, 'TOLSPATIAL.DAT')
        with open(tolspatial, 'w') as t:
            for fid, tol in tolspatial_rows:
                for row in self.execute(cell_sql, (fid,)):
                    gid = row[0]
                    t.write(line1.format(gid, tol))

    def export_wsurf(self, outdir):
        # check if there is any water surface data defined
        if self.is_table_empty('wsurf'):
            return
        count_sql = '''SELECT COUNT(fid) FROM wsurf;'''
        wsurf_sql = '''SELECT grid_fid, wselev FROM wsurf ORDER BY fid;'''

        line1 = '{0}\n'
        line2 = '{0}  {1}\n'

        wsurf_rows = self.execute(wsurf_sql).fetchall()
        if not wsurf_rows:
            return
        else:
            pass
        wsurf = os.path.join(outdir, 'WSURF.DAT')
        with open(wsurf, 'w') as w:
            count = self.execute(count_sql).fetchone()[0]
            w.write(line1.format(count))
            for row in wsurf_rows:
                w.write(line2.format(*row))

    def export_wstime(self, outdir):
        # check if there is any water surface data defined
        if self.is_table_empty('wstime'):
            return
        count_sql = '''SELECT COUNT(fid) FROM wstime;'''
        wstime_sql = '''SELECT grid_fid, wselev, wstime FROM wstime ORDER BY fid;'''

        line1 = '{0}\n'
        line2 = '{0}  {1}  {2}\n'

        wstime_rows = self.execute(wstime_sql).fetchall()
        if not wstime_rows:
            return
        else:
            pass
        wstime = os.path.join(outdir, 'WSTIME.DAT')
        with open(wstime, 'w') as w:
            count = self.execute(count_sql).fetchone()[0]
            w.write(line1.format(count))
            for row in wstime_rows:
                w.write(line2.format(*row))
