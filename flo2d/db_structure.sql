-- Create GeoPackage structure


 -- Create base GeoPackage tables

SELECT gpkgCreateBaseTables();

-- Add aspatial extension

INSERT INTO gpkg_extensions
  (table_name, column_name, extension_name, definition, scope)
VALUES (
    NULL,
    NULL,
    'gdal_aspatial',
    'http://gdal.org/geopackage_aspatial.html',
    'read-write'
);

-- enable foreign keys, disable synchronous, setting journal_mode as 'MEMORY'

PRAGMA foreign_keys = ON;
--PRAGMA synchronous=FULL;
PRAGMA journal_mode = memory; -- try to create the db using memory journal as it is much faster than WAL
--then, once the db is opened by QGIS, it will switch automatically to WAL (persistent mode)

-- FLO-2D tables definitions

-- The main table with model control parameters (from CONT.DAT and others)

CREATE TABLE cont (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL UNIQUE ON CONFLICT REPLACE,
    "value" TEXT,
    "note" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('cont', 'aspatial');


-- Triggers control table
CREATE TABLE "trigger_control" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "name" TEXT,
    "enabled" INTEGER
);


-- Grid table - data from FPLAIN.DAT, CADPTS.DAT, TOPO.DAT, MANNINGS_N.DAT

CREATE TABLE "grid" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "cell_north" INTEGER,
    "cell_east" INTEGER,
    "cell_south" INTEGER,
    "cell_west" INTEGER,
    "n_value" REAL,
    "elevation" REAL
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('grid', 'features', 4326);
SELECT gpkgAddGeometryColumn('grid', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('grid', 'geom');
SELECT gpkgAddSpatialIndex('grid', 'geom');



-- Inflow - INFLOW.DAT

CREATE TABLE "inflow" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "name" TEXT,
    "time_series_fid" INTEGER,
    "ident" TEXT  DEFAULT 'F',
    "inoutfc" INTEGER DEFAULT 0,
    "note" TEXT,
    "geom_type" TEXT,
    "bc_fid" INTEGER,
    CONSTRAINT inflow_unique_gtype_fid UNIQUE (geom_type, bc_fid) ON CONFLICT IGNORE
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('inflow', 'aspatial');

CREATE TABLE "inflow_cells" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "inflow_fid" INTEGER NOT NULL,
    "grid_fid" INTEGER NOT NULL,
    "area_factor" REAL
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('inflow_cells', 'aspatial');

---- trigger for a new inflow
--INSERT INTO trigger_control (name, enabled) VALUES ('update_inflow_cells_on_inflow_insert', 1);
--CREATE TRIGGER "update_inflow_cells_on_inflow_insert"
--    AFTER INSERT ON "inflow"
--    WHEN (
--        SELECT enabled FROM trigger_control WHERE name = 'update_inflow_cells_on_inflow_insert'
--    )
--    BEGIN
--        INSERT INTO inflow_cells
--            (inflow_fid, grid_fid)
--        SELECT
--            NEW.fid, g.fid
--        FROM
--            grid AS g,
--            all_user_bc AS abc
--        WHERE
--            abc.type = 'inflow' AND
--            abc.geom_type = NEW.geom_type AND
--            abc.bc_fid = NEW.bc_fid AND
--            ST_Intersects(CastAutomagic(g.geom), CastAutomagic(abc.geom));
--    END;
--
---- inflow updated
--INSERT INTO trigger_control (name, enabled) VALUES ('update_inflow_cells_on_inflow_update', 1);
--CREATE TRIGGER "update_inflow_cells_on_inflow_update"
--    AFTER UPDATE ON "inflow"
--    WHEN (
--        SELECT enabled FROM trigger_control WHERE name = 'update_inflow_cells_on_inflow_update'
--    )
--    BEGIN
--        DELETE FROM inflow_cells WHERE inflow_fid = NEW.fid;
--        INSERT INTO inflow_cells
--            (inflow_fid, grid_fid)
--        SELECT
--            NEW.fid, g.fid
--        FROM
--            grid AS g,
--            all_user_bc AS abc
--        WHERE
--            abc.type = 'inflow' AND
--            abc.geom_type = NEW.geom_type AND
--            abc.bc_fid = NEW.bc_fid AND
--            ST_Intersects(CastAutomagic(g.geom), CastAutomagic(abc.geom));
--    END;
--
---- inflow deleted
--INSERT INTO trigger_control (name, enabled) VALUES ('update_inflow_cells_on_inflow_delete', 1);
--CREATE TRIGGER "update_inflow_cells_on_inflow_delete"
--    AFTER DELETE ON "inflow"
--    WHEN (
--        SELECT enabled FROM trigger_control WHERE name = 'update_inflow_cells_on_inflow_delete'
--    )
--    BEGIN
--        DELETE FROM inflow_cells WHERE inflow_fid = OLD.fid;
--    END;

CREATE TABLE "reservoirs" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "user_res_fid" INTEGER,
    "name" TEXT,
    "grid_fid" INTEGER,
    "wsel" REAL,
    "note" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('reservoirs', 'features', 4326);
SELECT gpkgAddGeometryColumn('reservoirs', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('reservoirs', 'geom');
-- SELECT gpkgAddSpatialIndex('reservoirs', 'geom');

CREATE TABLE "inflow_time_series" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "name" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('inflow_time_series', 'aspatial');

CREATE TABLE "inflow_time_series_data" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "series_fid" INTEGER,
    "time" REAL,
    "value" REAL,
    "value2" REAL
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('inflow_time_series_data', 'aspatial');

CREATE TABLE "outflow_time_series" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "name" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('outflow_time_series', 'aspatial');

CREATE TABLE "outflow_time_series_data" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "series_fid" INTEGER,
    "time" REAL,
    "value" REAL
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('outflow_time_series_data', 'aspatial');

CREATE TABLE "rain_time_series" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "name" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('rain_time_series', 'aspatial');

CREATE TABLE "rain_time_series_data" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "series_fid" INTEGER,
    "time" REAL,
    "value" REAL
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('rain_time_series_data', 'aspatial');


-- OUTFLOW.DAT

CREATE TABLE "outflow" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "name" TEXT,
    "chan_out" INTEGER,
    "fp_out" INTEGER,
    "hydro_out" INTEGER,
    "chan_tser_fid" INTEGER,
    "chan_qhpar_fid" INTEGER,
    "chan_qhtab_fid" INTEGER,
    "fp_tser_fid" INTEGER,
    "type" INTEGER,
    "geom_type" TEXT,
    "bc_fid" INTEGER,
    CONSTRAINT outflow_unique_gtype_fid UNIQUE (geom_type, bc_fid) ON CONFLICT IGNORE
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('outflow', 'aspatial');

CREATE TABLE "outflow_cells" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "outflow_fid" INTEGER,
    "grid_fid" INTEGER,
    "area_factor" REAL
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('outflow_cells', 'aspatial');

---- trigger for a new outflow
--INSERT INTO trigger_control (name, enabled) VALUES ('update_outflow_cells_on_outflow_insert', 1);
--CREATE TRIGGER "update_outflow_cells_on_outflow_insert"
--    AFTER INSERT ON "outflow"
--    WHEN (
--        SELECT enabled FROM trigger_control WHERE name = 'update_outflow_cells_on_outflow_insert'
--    )
--    BEGIN
--        INSERT INTO "outflow_cells" (outflow_fid, grid_fid)
--            SELECT
--                NEW.fid, g.fid
--            FROM
--                grid AS g, all_user_bc AS abc
--            WHERE
--                abc.type = 'outflow' AND
--                abc.geom_type = NEW.geom_type AND
--                abc.bc_fid = NEW.bc_fid AND
--                ST_Intersects(CastAutomagic(g.geom), CastAutomagic(abc.geom));
--    END;
--
---- outflow updated
--INSERT INTO trigger_control (name, enabled) VALUES ('update_outflow_cells_on_outflow_update', 1);
--CREATE TRIGGER "update_outflow_cells_on_outflow_update"
--    AFTER UPDATE ON "outflow"
--    WHEN (
--        SELECT enabled FROM trigger_control WHERE name = 'update_outflow_cells_on_outflow_update'
--    )
--    BEGIN
--        DELETE FROM outflow_cells WHERE outflow_fid = NEW.fid;
--        INSERT INTO "outflow_cells" (outflow_fid, grid_fid)
--            SELECT
--                NEW.fid, g.fid
--            FROM
--                grid AS g, all_user_bc AS abc
--            WHERE
--                abc.type = 'outflow' AND
--                abc.geom_type = NEW.geom_type AND
--                abc.bc_fid = NEW.bc_fid AND
--                ST_Intersects(CastAutomagic(g.geom), CastAutomagic(abc.geom));
--    END;
--
---- outflow deleted
--INSERT INTO trigger_control (name, enabled) VALUES ('update_outflow_cells_on_outflow_delete', 1);
--CREATE TRIGGER "update_outflow_cells_on_outflow_delete"
--    AFTER DELETE ON "outflow"
--    WHEN (
--        SELECT enabled FROM trigger_control WHERE name = 'update_outflow_cells_on_outflow_delete'
--    )
--    BEGIN
--        DELETE FROM outflow_cells WHERE outflow_fid = OLD.fid;
--    END;

CREATE VIEW outflow_chan_elems (
    elem_fid,
    outflow_fid
) AS
SELECT
    c.grid_fid, o.fid
FROM
    outflow AS o,
    outflow_cells AS c
WHERE
    o.fid = c.outflow_fid AND
    (o.chan_out > 0 OR
    o.chan_tser_fid > 0 OR
    o.chan_qhpar_fid > 0 OR
    o.chan_qhtab_fid > 0);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('outflow_chan_elems', 'aspatial');

CREATE VIEW outflow_fp_elems (
    elem_fid,
    outflow_fid
) AS
SELECT
    c.grid_fid, o.fid
FROM
    outflow AS o,
    outflow_cells AS c
WHERE
    o.fid = c.outflow_fid AND
    (o.fp_out > 0 OR
    o.fp_tser_fid > 0);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('outflow_fp_elems', 'aspatial');

-- CREATE VIEW "chan_elems_in_segment" (
--     chan_elem_fid,
--     seg_fid
-- ) AS
-- SELECT DISTINCT ichangrid, seg_fid FROM chan_r
-- UNION ALL
-- SELECT DISTINCT ichangrid, seg_fid FROM chan_v
-- UNION ALL
-- SELECT DISTINCT ichangrid, seg_fid FROM chan_t
-- UNION ALL
-- SELECT DISTINCT ichangrid, seg_fid FROM chan_n;

--CREATE TRIGGER "find_outflow_cells_insert"
--    AFTER INSERT ON "outflow"
--    WHEN (new."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom") AND NEW."ident" = 'N')
--    BEGIN
--        DELETE FROM "outflow_cells" WHERE outflow_fid = NEW."fid";
--        INSERT INTO "outflow_cells" (outflow_fid, grid_fid, area_factor)
--        SELECT NEW.fid, g.fid, ST_Area(ST_Intersection(CastAutomagic(g.geom), CastAutomagic(NEW.geom)))/ST_Area(NEW.geom) FROM grid as g
--        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_outflow_chan_elems_insert"
--    AFTER INSERT ON "outflow"
--    WHEN (new."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom") AND NEW."ident" = 'K')
--    BEGIN
--        DELETE FROM "outflow_chan_elems" WHERE outflow_fid = NEW."fid";
--        INSERT INTO "outflow_chan_elems" (outflow_fid, elem_fid) SELECT NEW.fid, g.fid FROM grid as g
--        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_outflow_cells_update"
--    AFTER UPDATE ON "outflow"
--    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom") AND NOT NULL)
--    BEGIN
--        DELETE FROM "outflow_cells" WHERE outflow_fid = OLD."fid" AND NEW."ident" = 'N';
--        INSERT INTO "outflow_cells" (outflow_fid, grid_fid) SELECT OLD.fid, g.fid FROM grid as g
--        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom)) AND NEW."ident" = 'N';
--    END;
--
--CREATE TRIGGER "find_outflow_chan_elems_update"
--    AFTER UPDATE ON "outflow"
--    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom") AND NOT NULL)
--    BEGIN
--        DELETE FROM "outflow_chan_elems" WHERE outflow_fid = OLD."fid" AND NEW."ident" = 'K';
--        INSERT INTO "outflow_chan_elems" (outflow_fid, elem_fid) SELECT OLD.fid, g.fid FROM grid as g
--        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom)) AND NEW."ident" = 'K';
--    END;
--
--CREATE TRIGGER "find_outflow_cells_delete"
--    AFTER DELETE ON "outflow"
--    WHEN (OLD."ident" = 'N')
--    BEGIN
--        DELETE FROM "outflow_cells" WHERE outflow_fid = OLD."fid";
--    END;
--
--CREATE TRIGGER "find_outflow_chan_elems_delete"
--    AFTER DELETE ON "outflow"
--    WHEN (OLD."ident" = 'K')
--    BEGIN
--        DELETE FROM "outflow_chan_elems" WHERE outflow_fid = OLD."fid";
--    END;

CREATE TABLE "qh_params" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "name" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('qh_params', 'aspatial');

CREATE TABLE "qh_params_data" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "params_fid" INTEGER, -- fid of params group from qh_params table
    "hmax" REAL,
    "coef" REAL,
    "exponent" REAL
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('qh_params_data', 'aspatial');

CREATE TABLE "qh_table" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "name" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('qh_table', 'aspatial');

CREATE TABLE "qh_table_data" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "table_fid" INTEGER, -- fid of QH table
    "depth" REAL, -- CHDEPTH, depth above the thalweg
    "q" REAL -- CQTABLE, discharge for the channel outflow
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('qh_table_data', 'aspatial');

CREATE TABLE "out_hydrographs" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "hydro_sym" TEXT, -- O1-O9
    "name" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('out_hydrographs', 'features', 4326);
SELECT gpkgAddGeometryColumn('out_hydrographs', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('out_hydrographs', 'geom');
-- SELECT gpkgAddSpatialIndex('out_hydrographs', 'geom');

CREATE TABLE "out_hydrographs_cells" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "hydro_fid" INTEGER, -- fid of outflow hydrograph form out_hydrographs table
    "grid_fid" INTEGER
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('out_hydrographs_cells', 'aspatial');


-- RAIN.DAT

CREATE TABLE "rain" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "name" TEXT, -- name of rain
    "irainreal" INTEGER, -- IRAINREAL switch for real-time rainfall (NEXRAD)
    "irainbuilding" INTEGER, -- IRAINBUILDING, switch, if 1 rainfall on ARF portion of grid will be contributed to surface runoff
    "time_series_fid" INTEGER, -- id of time series used for rain cumulative distribution (in time)
    "tot_rainfall" REAL, -- RTT, total storm rainfall [inch or mm]
    "rainabs" REAL, -- RAINABS, rain interception or abstraction
    "irainarf" REAL, -- IRAINARF, switch for individual grid elements rain area reduction factor (1 is ON)
    "movingstrom" INTEGER, -- MOVINGSTORM, switch for moving storm simulation (1 is ON)
    "rainspeed" REAL, -- RAINSPEED, speed of moving storm
    "iraindir" INTEGER, -- IRAINDIR, direction of moving storm
    "notes" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('rain', 'aspatial');

CREATE TABLE "rain_arf_areas" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "rain_fid" INTEGER, -- fid of rain the area is defined for
    "arf" REAL, -- RAINARF(I), area reduction factor
    "notes" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('rain_arf_areas', 'features', 4326);
SELECT gpkgAddGeometryColumn('rain_arf_areas', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('rain_arf_areas', 'geom');
-- SELECT gpkgAddSpatialIndex('rain_arf_areas', 'geom');

CREATE TABLE "rain_arf_cells" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "rain_arf_area_fid" INTEGER, -- fid of area with ARF defined
    "grid_fid" INTEGER, -- IRGRID(I), nr of grid element
    "arf" REAL -- RAINARF(I), ARF value for a grid elemen
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('rain_arf_cells', 'aspatial');

--CREATE TRIGGER "find_rain_arf_cells_insert"
--    AFTER INSERT ON "rain_arf_areas"
--    WHEN (new."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--    BEGIN
--        DELETE FROM "rain_arf_cells" WHERE rain_arf_area_fid = NEW."fid";
--        INSERT INTO "rain_arf_cells" (rain_arf_area_fid, grid_fid, arf)
--        SELECT NEW.fid, g.fid, NEW.arf FROM grid as g
--        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_rain_arf_cells_update"
--    AFTER UPDATE ON "rain_arf_areas"
--    WHEN (new."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--    BEGIN
--        DELETE FROM "rain_arf_cells" WHERE rain_arf_area_fid = NEW."fid";
--        INSERT INTO "rain_arf_cells" (rain_arf_area_fid, grid_fid, arf)
--        SELECT NEW.fid, g.fid, NEW.arf FROM grid as g
--        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_rain_arf_cells_delete"
--    AFTER DELETE ON "rain_arf_areas"
--    BEGIN
--        DELETE FROM "rain_arf_cells" WHERE rain_arf_area_fid = OLD."fid";
--    END;


-- CHAN.DAT

CREATE TABLE "chan" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "name" TEXT, -- name of segment (optional)
    "depinitial" REAL DEFAULT 0, -- DEPINITIAL, initial channel flow depth
    "froudc" REAL DEFAULT 0, -- FROUDC, max Froude channel number
    "roughadj" REAL DEFAULT 0, -- ROUGHADJ, coefficient for depth adjustment
    "isedn" INTEGER DEFAULT 0, -- ISEDN, sediment transport equation or data
    "notes" TEXT,
    "user_lbank_fid" INTEGER, -- FID of parent left bank line,
    "rank" INTEGER
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('chan', 'features', 4326);
SELECT gpkgAddGeometryColumn('chan', 'geom', 'LINESTRING', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('chan', 'geom');
-- SELECT gpkgAddSpatialIndex('chan', 'geom');


CREATE TABLE "chan_elems" (
    "id" INTEGER NOT NULL PRIMARY KEY,
    "fid" INTEGER NOT NULL, -- ICHANGRID, grid element number for left bank
    "seg_fid" INTEGER, -- fid of cross-section's segment
    "nr_in_seg" INTEGER, -- cross-section number in segment
    "rbankgrid" INTEGER, -- RIGHTBANK, right bank grid element fid
    "fcn" REAL, -- FCN, average Manning's n in the grid element
    "xlen" REAL, -- channel length contained within the grid element ICHANGRID
    "type" TEXT, -- SHAPE, type of cross-section shape definition
    "notes" TEXT,
    "user_xs_fid" INTEGER,
    "interpolated" INTEGER

);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('chan_elems', 'features', 4326);
SELECT gpkgAddGeometryColumn('chan_elems', 'geom', 'LINESTRING', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('chan_elems', 'geom');
-- SELECT gpkgAddSpatialIndex('chan_elems', 'geom');

CREATE TABLE rbank (
    "fid" INTEGER PRIMARY KEY,
    "chan_seg_fid" INTEGER
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('rbank', 'features', 4326);
SELECT gpkgAddGeometryColumn('rbank', 'geom', 'LINESTRING', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('rbank', 'geom');

CREATE TABLE "chan_r" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "elem_fid" INTEGER, -- fid of cross-section's element
    "bankell" REAL, -- BANKELL, left bank elevation
    "bankelr" REAL, -- BANKELR, right bank elevation
    "fcw" REAL, -- FCW, channel width
    "fcd" REAL -- channel channel thalweg depth (deepest part measured from the lowest bank)
    
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('chan_r', 'aspatial');

CREATE TABLE "chan_v" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "elem_fid" INTEGER, -- fid of cross-section's element
    "bankell" REAL, -- BANKELL, left bank elevation
    "bankelr" REAL, -- BANKELR, right bank elevation
    "fcd" REAL, -- channel channel thalweg depth (deepest part measured from the lowest bank)
    "a1" REAL, -- A1,
    "a2" REAL, -- A2,
    "b1" REAL, -- B1,
    "b2" REAL, -- B2,
    "c1" REAL, -- C1,
    "c2" REAL, -- C2,
    "excdep" REAL, -- EXCDEP, channel depth above which second variable area relationship will be applied
    "a11" REAL, -- A11,
    "a22" REAL, -- A22,
    "b11" REAL, -- B11,
    "b22" REAL, -- B22,
    "c11" REAL, -- C11,
    "c22" REAL -- C22,
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('chan_v', 'aspatial');

CREATE TABLE "chan_t" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "elem_fid" INTEGER, -- fid of cross-section's element
    "bankell" REAL, -- BANKELL, left bank elevation
    "bankelr" REAL, -- BANKELR, right bank elevation
    "fcw" REAL, -- FCW, channel width
    "fcd" REAL, -- channel channel thalweg depth (deepest part measured from the lowest bank)
    "zl" REAL, -- ZL left side slope
    "zr" REAL --ZR right side slope
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('chan_t', 'aspatial');

CREATE TABLE "chan_n" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "elem_fid" INTEGER, -- fid of cross-section's element
    "nxsecnum" INTEGER, -- NXSECNUM, surveyed cross section number assigned in XSEC.DAT
    "xsecname" TEXT -- xsection name
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('chan_n', 'aspatial');

-- TODO: create triggers for geometry INSERT and UPDATE
-- use notes column to flag features created by user!
-- -- create geometry when rightbank and leftbank are given
-- CREATE TRIGGER "chan_n_geom_insert"
--     AFTER INSERT ON "chan_n"
--     WHEN (NEW."ichangrid" NOT NULL AND NEW."rbankgrid" NOT NULL)
--     BEGIN
--         UPDATE "chan_n" 
--             SET geom = (
--                 SELECT 
--                     AsGPB(MakeLine((ST_Centroid(CastAutomagic(g1.geom))),
--                     (ST_Centroid(CastAutomagic(g2.geom)))))
--                 FROM grid AS g1, grid AS g2
--                 WHERE g1.fid = ichangrid AND g2.fid = rbankgrid);
--     END;

--update left and right bank fids when geometry changed
-- CREATE TRIGGER "chan_n_banks_update_geom_changed"
--     AFTER UPDATE ON "chan_n"
--     WHEN ( NEW.notes IS NULL )
--     BEGIN
--         UPDATE "chan_n" SET ichangrid = (SELECT g.fid FROM grid AS g
--             WHERE ST_Intersects(g.geom,StartPoint(CastAutomagic(geom))))
--             WHERE fid = NEW.fid;
--         UPDATE "chan_n" SET rbankgrid = (SELECT g.fid FROM grid AS g
--             WHERE ST_Intersects(g.geom,EndPoint(CastAutomagic(geom))))
--             WHERE fid = NEW.fid;
--     END;
--
-- CREATE TRIGGER "chan_n_geom_update_banks_changed"
--     AFTER UPDATE OF ichangrid, rbankgrid ON "chan_n"
-- --     WHEN (NEW."ichangrid" NOT NULL AND NEW."rbankgrid" NOT NULL)
--     BEGIN
--         UPDATE "chan_n" 
--             SET geom = (
--                 SELECT 
--                     AsGPB(MakeLine((ST_Centroid(CastAutomagic(g1.geom))),
--                     (ST_Centroid(CastAutomagic(g2.geom)))))
--                 FROM grid AS g1, grid AS g2
--                 WHERE g1.fid = ichangrid AND g2.fid = rbankgrid);
--     END;

-- CREATE VIEW "chan_elems_in_segment" (
--     chan_elem_fid,
--     seg_fid
-- ) AS
-- SELECT DISTINCT ichangrid, seg_fid FROM chan_r
-- UNION ALL
-- SELECT DISTINCT ichangrid, seg_fid FROM chan_v
-- UNION ALL
-- SELECT DISTINCT ichangrid, seg_fid FROM chan_t
-- UNION ALL
-- SELECT DISTINCT ichangrid, seg_fid FROM chan_n;

-- CREATE TABLE "rightbanks" (
--     "fid" INTEGER NOT NULL PRIMARY KEY,
--     "seg_fid" INTEGER
-- );
-- INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('rightbanks', 'features', 4326);
-- SELECT gpkgAddGeometryColumn('rightbanks', 'geom', 'LINESTRING', 0, 0, 0);
-- SELECT gpkgAddGeometryTriggers('rightbanks', 'geom');
-- -- SELECT gpkgAddSpatialIndex('rightbanks', 'geom');
--
-- CREATE TRIGGER "find_rbank_n_insert"
--     AFTER INSERT ON "chan_n"
--     WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--     BEGIN
--         DELETE FROM "rightbanks" WHERE seg_fid = NEW."seg_fid";
--         INSERT INTO "rightbanks" (seg_fid, geom)
--             SELECT
--                 NEW.seg_fid, AsGPB(MakeLine(Centroid(CastAutomagic(g.geom)))) AS geom FROM chan_n AS ch, grid AS g
--             WHERE
--                 NEW.rbankgrid = g.fid AND seg_fid = NEW.seg_fid
--             GROUP BY seg_fid;
--     END;
--
-- CREATE TRIGGER "find_rbank_n_update"
--     AFTER UPDATE ON "chan_n"
--     WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--     BEGIN
--         DELETE FROM "rightbanks" WHERE seg_fid = NEW."seg_fid";
--         INSERT INTO "rightbanks" (seg_fid, geom)
--             SELECT
--                 NEW.seg_fid, AsGPB(MakeLine(Centroid(CastAutomagic(g.geom)))) AS geom FROM chan_n AS ch, grid AS g
--             WHERE
--                 NEW.rbankgrid = g.fid AND seg_fid = NEW.seg_fid
--             GROUP BY seg_fid;
--     END;
--
-- CREATE TRIGGER "find_rbank_n_delete"
--     AFTER DELETE ON "chan_n"
--     BEGIN
--         DELETE FROM "rightbanks" WHERE seg_fid = OLD."seg_fid";
--     END;

CREATE TABLE "chan_confluences" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "conf_fid" INTEGER, -- confluence fid
    "type" INTEGER, -- switch, tributary (0 if ICONFLO1) or main channel (1 if ICONFLO2) 
    "chan_elem_fid" INTEGER, -- ICONFLO1 or ICONFLO2, tributary or main channel element fid
    "notes" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('chan_confluences', 'features', 4326);
SELECT gpkgAddGeometryColumn('chan_confluences', 'geom', 'POINT', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('chan_confluences', 'geom');
-- SELECT gpkgAddSpatialIndex('chan_confluences', 'geom');

-- automatically create/modify geometry of confluences on iconflo1/2 insert/update
--CREATE TRIGGER "confluence_geom_insert"
--    AFTER INSERT ON "chan_confluences"
--    WHEN (NEW."chan_elem_fid" NOT NULL)
--    BEGIN
--        UPDATE "chan_confluences"
--            SET geom = (SELECT AsGPB(ST_Centroid(CastAutomagic(g.geom))) FROM grid AS g WHERE g.fid = chan_elem_fid);
--        -- TODO: set also seg_fid
--    END;
--
--CREATE TRIGGER "confluence_geom_update"
--    AFTER UPDATE ON "chan_confluences"
--    WHEN (NEW."chan_elem_fid" NOT NULL)
--    BEGIN
--        UPDATE "chan_confluences"
--            SET geom = (SELECT AsGPB(ST_Centroid(CastAutomagic(g.geom))) FROM grid AS g WHERE g.fid = chan_elem_fid);
--        -- TODO: set also seg_fid
--    END;

CREATE TABLE "noexchange_chan_areas" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "notes" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('noexchange_chan_areas', 'features', 4326);
SELECT gpkgAddGeometryColumn('noexchange_chan_areas', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('noexchange_chan_areas', 'geom');
-- SELECT gpkgAddSpatialIndex('noexchange_chan_areas', 'geom');

CREATE TABLE "noexchange_chan_elems" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "noex_area_fid" INTEGER, -- fid of noexchange_chan_area polygon
    "chan_elem_fid" INTEGER -- NOEXCHANGE, channel element number not exchanging flow. Filled in by a geoprocessing trigger
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('noexchange_chan_elems', 'aspatial');

--CREATE TRIGGER "find_noexchange_cells_insert"
--    AFTER INSERT ON "noexchange_chan_areas"
--    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--    BEGIN
--        DELETE FROM "noexchange_chan_elems" WHERE noex_fid = NEW."fid";
--        INSERT INTO "noexchange_chan_elems" (noex_fid, grid_fid)
--        SELECT NEW.fid, g.fid FROM grid as g
--        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_noexchange_cells_update"
--    AFTER UPDATE ON "noexchange_chan_areas"
--    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--    BEGIN
--        DELETE FROM "noexchange_chan_elems" WHERE noex_fid = NEW."fid";
--        INSERT INTO "noexchange_chan_elems" (noex_fid, grid_fid)
--        SELECT NEW.fid, g.fid FROM grid as g
--        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_noexchange_cells_delete"
--    AFTER DELETE ON "noexchange_chan_areas"
--    BEGIN
--        DELETE FROM "noexchange_chan_elems" WHERE noex_fid = OLD."fid";
--    END;

CREATE TABLE "chan_wsel" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "seg_fid" INTEGER, -- found by geoprocessing trigger, channel segment for which the WSELs are specified
    "istart" INTEGER, -- ISTART, first channel element with a starting WSEL specified
    "wselstart" REAL, -- WSELSTART, first channel element starting WSEL
    "iend" INTEGER, -- IEND, last channel element with a starting WSEL specified
    "wselend" REAL -- WSELEND, last channel element starting WSEL
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('chan_wsel', 'aspatial');


-- XSEC.DAT

CREATE TABLE "xsec_n_data" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "chan_n_nxsecnum" INTEGER, -- NXSECNUM, fid of cross-section in chan_n
    "xi" REAL, -- XI, station distance from left point
    "yi" REAL -- YI, elevation
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('xsec_n_data', 'aspatial');


-- EVAPOR.DAT

CREATE TABLE "evapor" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "ievapmonth" INTEGER, -- IEVAPMONTH, starting month of simulation
    "iday" INTEGER, -- IDAY, starting day of the week (1-7)
    "clocktime" REAL -- CLOCKTIME, starting clock time
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('evapor', 'aspatial');

CREATE TABLE "evapor_monthly" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "month" TEXT, -- EMONTH, name of the month
    "monthly_evap" REAL -- EVAP, monthly evaporation rate
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('evapor_monthly', 'aspatial');

CREATE TABLE "evapor_hourly" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "month" TEXT, -- EMONTH, name of the month
    "hour" INTEGER, -- hour of the day (1-24)
    "hourly_evap" REAL -- EVAPER, Hourly percentage of the daily total evaporation
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('evapor_hourly', 'aspatial');


-- INFIL.DAT

CREATE TABLE "infil" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "infmethod" INTEGER, -- INFMETHOD, infiltration method number
    "abstr" REAL, -- ABSTR, Green Ampt global floodplain rainfall abstraction or interception
    "sati" REAL, -- SATI, Global initial saturation of the soil
    "satf" REAL, -- SATF, Global final saturation of the soil
    "poros" REAL, -- POROS, global floodplain soil porosity
    "soild" REAL, -- SOILD, Green Ampt global soil limiting depth storage
    "infchan" INTEGER, -- INFCHAN, switch for simulating channel infiltration
    "hydcall" REAL, -- HYDCALL, average global floodplain hydraulic conductivity
    "soilall" REAL, -- SOILALL, average global floodplain capillary suction
    "hydcadj" REAL, -- HYDCADJ, hydraulic conductivity adjustment variable
    "hydcxx" REAL, -- HYDCXX, global channel infiltration hydraulic conductivity
    "scsnall" REAL, -- SCSNALL, global floodplain SCS curve number
    "abstr1" REAL, -- ABSTR1, SCS global floodplain rainfall abstraction or interception
    "fhortoni" REAL, -- FHORTONI, global Horton’s equation initial infiltration rate
    "fhortonf" REAL, -- FHORTONF, global Horton’s equation final infiltration rate
    "decaya" REAL --DECAYA, Horton’s equation decay coefficient
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('infil', 'aspatial');

CREATE TABLE "infil_chan_seg" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "chan_seg_fid" INTEGER, -- channel segment fid from chan table
    "hydcx" REAL, -- HYDCX, initial hydraulic conductivity for a channel segment
    "hydcxfinal" REAL, -- HYDCXFINAL, final hydraulic conductivity for a channel segment
    "soildepthcx" REAL -- SOILDEPTHCX, maximum soil depth for the initial channel infiltration
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('infil_chan_seg', 'aspatial');

CREATE TABLE "infil_areas_green" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "hydc" REAL, -- HYDC, grid element average hydraulic conductivity
    "soils" REAL, -- SOILS, capillary suction head for floodplain grid elements
    "dtheta" REAL, -- DTHETA, grid element soil moisture deficit
    "abstrinf" REAL, -- ABSTRINF, grid element rainfall abstraction
    "rtimpf" REAL, -- RTIMPF, percent impervious floodplain area on a grid element
    "soil_depth" REAL -- SOIL_DEPTH, maximum soil depth for infiltration on a grid element
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('infil_areas_green', 'features', 4326);
SELECT gpkgAddGeometryColumn('infil_areas_green', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('infil_areas_green', 'geom');
-- SELECT gpkgAddSpatialIndex('infil_areas_green', 'geom');

    -- Green Ampt

CREATE TABLE "infil_cells_green" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "grid_fid" INTEGER, -- grid element number from grid table
    "infil_area_fid" INTEGER -- polygon fid from infil_areas_green table
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('infil_cells_green', 'aspatial');

--CREATE TRIGGER "find_infil_cells_green_insert"
--    AFTER INSERT ON "infil_areas_green"
--    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--    BEGIN
--        DELETE FROM "infil_cells_green" WHERE infil_area_fid = NEW."fid";
--        INSERT INTO "infil_cells_green" (infil_area_fid, grid_fid)
--            SELECT NEW.fid, g.fid FROM grid as g
--            WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_infil_cells_green_update"
--    AFTER UPDATE ON "infil_areas_green"
--    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--    BEGIN
--        DELETE FROM "infil_cells_green" WHERE infil_area_fid = NEW."fid";
--        INSERT INTO "infil_cells_green" (infil_area_fid, grid_fid)
--        SELECT NEW.fid, g.fid FROM grid as g
--        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_infil_cells_green_delete"
--    AFTER DELETE ON "infil_areas_green"
--    BEGIN
--        DELETE FROM "infil_cells_green" WHERE infil_area_fid = OLD."fid";
--    END;

    -- SCS

CREATE TABLE "infil_areas_scs" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "scscn" REAL -- SCSCN, SCS curve numbers of the floodplain grid elements
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('infil_areas_scs', 'features', 4326);
SELECT gpkgAddGeometryColumn('infil_areas_scs', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('infil_areas_scs', 'geom');
-- SELECT gpkgAddSpatialIndex('infil_areas_scs', 'geom');

CREATE TABLE "infil_cells_scs" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "grid_fid" INTEGER, -- grid element number from grid table
    "infil_area_fid" INTEGER -- polygon fid from infil_areas_scs table
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('infil_cells_scs', 'aspatial');

--CREATE TRIGGER "find_infil_cells_scs_insert"
--    AFTER INSERT ON "infil_areas_scs"
--    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--    BEGIN
--        DELETE FROM "infil_cells_scs" WHERE infil_area_fid = NEW."fid";
--        INSERT INTO "infil_cells_scs" (infil_area_fid, grid_fid)
--            SELECT NEW.fid, g.fid FROM grid as g
--            WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_infil_cells_scs_update"
--    AFTER UPDATE ON "infil_areas_scs"
--    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--    BEGIN
--        DELETE FROM "infil_cells_scs" WHERE infil_area_fid = NEW."fid";
--        INSERT INTO "infil_cells_scs" (infil_area_fid, grid_fid)
--        SELECT NEW.fid, g.fid FROM grid as g
--        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_infil_cells_scs_delete"
--    AFTER DELETE ON "infil_areas_scs"
--    BEGIN
--        DELETE FROM "infil_cells_scs" WHERE infil_area_fid = OLD."fid";
--    END;

    -- HORTON

CREATE TABLE "infil_areas_horton" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "fhorti" REAL, -- FHORTI, Horton’s equation floodplain initial infiltration rate
    "fhortf" REAL, -- FHORTF, Horton’s equation floodplain final infiltration rate
    "deca" REAL --DECA, Horton’s equation decay coefficient
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('infil_areas_horton', 'features', 4326);
SELECT gpkgAddGeometryColumn('infil_areas_horton', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('infil_areas_horton', 'geom');
-- SELECT gpkgAddSpatialIndex('infil_areas_horton', 'geom');

CREATE TABLE "infil_cells_horton" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "grid_fid" INTEGER, -- grid element number from grid table
    "infil_area_fid" INTEGER -- polygon fid from infil_areas_horton table
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('infil_cells_horton', 'aspatial');

--CREATE TRIGGER "find_infil_cells_horton_insert"
--    AFTER INSERT ON "infil_areas_horton"
--    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--    BEGIN
--        DELETE FROM "infil_cells_horton" WHERE infil_area_fid = NEW."fid";
--        INSERT INTO "infil_cells_horton" (infil_area_fid, grid_fid)
--            SELECT NEW.fid, g.fid FROM grid as g
--            WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_infil_cells_horton_update"
--    AFTER UPDATE ON "infil_areas_horton"
--    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--    BEGIN
--        DELETE FROM "infil_cells_horton" WHERE infil_area_fid = NEW."fid";
--        INSERT INTO "infil_cells_horton" (infil_area_fid, grid_fid)
--        SELECT NEW.fid, g.fid FROM grid as g
--        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_infil_cells_horton_delete"
--    AFTER DELETE ON "infil_areas_horton"
--    BEGIN
--        DELETE FROM "infil_cells_horton" WHERE infil_area_fid = OLD."fid";
--    END;

    -- CHANNELS

CREATE TABLE "infil_areas_chan" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "hydconch" REAL -- HYDCONCH, hydraulic conductivity for a channel element
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('infil_areas_chan', 'features', 4326);
SELECT gpkgAddGeometryColumn('infil_areas_chan', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('infil_areas_chan', 'geom');
-- SELECT gpkgAddSpatialIndex('infil_areas_chan', 'geom');

CREATE TABLE "infil_chan_elems" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "grid_fid" INTEGER, -- grid element number from grid table
    "infil_area_fid" INTEGER -- polygon fid from infil_areas_chan table
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('infil_chan_elems', 'aspatial');

--CREATE TRIGGER "find_infil_chan_elems_insert"
--    AFTER INSERT ON "infil_areas_chan"
--    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--    BEGIN
--        DELETE FROM "infil_chan_elems" WHERE infil_area_fid = NEW."fid";
--        INSERT INTO "infil_chan_elems" (infil_area_fid, grid_fid)
--            SELECT NEW.fid, g.fid FROM grid as g
--            WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_infil_chan_elems_update"
--    AFTER UPDATE ON "infil_areas_chan"
--    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--    BEGIN
--        DELETE FROM "infil_chan_elems" WHERE infil_area_fid = NEW."fid";
--        INSERT INTO "infil_chan_elems" (infil_area_fid, grid_fid)
--        SELECT NEW.fid, g.fid FROM grid as g
--        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_infil_chan_elems_delete"
--    AFTER DELETE ON "infil_areas_chan"
--    BEGIN
--        DELETE FROM "infil_chan_elems" WHERE infil_area_fid = OLD."fid";
--    END;

-- HYSTRUC.DAT

CREATE TABLE "struct" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "type" TEXT, -- type of the structure, equal to the next line's STRUCHAR, decides in which table the data are stored (C for rating_curves table, R for repl_rat_curves, T for rat_table, F for culvert_equations, or D for storm_drains)
    "structname" TEXT, -- STRUCTNAME, name of the structure
    "ifporchan" INTEGER, -- IFPORCHAN, switch, 0 for floodplain structure (shares discharge between 2 floodplain elements), 1 for channel structure (channel to channel), 2 for floodplain to channel, 3 for channel to floodplain
    "icurvtable" INTEGER, -- ICURVTABLE, switch, 0 for rating curve, 1 for rating table, 2 for culvert equation
    "inflonod" INTEGER, -- INFLONOD, grid element containing the structure or structure inlet
    "outflonod" INTEGER, -- OUTFLONOD, grid element receiving the structure discharge (structure outlet)
    "inoutcont" INTEGER, -- INOUTCONT, 0 for no tailwater effects - compute discharge based on headwater, 1 for reduced discharge (no upstream flow allowed), 2 for reduced discharge and upstream flow allowed
    "headrefel" REAL, -- HEADREFEL, reference elevation above which the headwater is determined, Set 0.0 to use existing channel bed
    "clength" REAL, -- CLENGTH, culvert length,
    "cdiameter" REAL, -- CDIAMETER, culvert diameter,
    "notes" TEXT -- structure notes
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('struct', 'features', 4326);
SELECT gpkgAddGeometryColumn('struct', 'geom', 'LINESTRING', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('struct', 'geom');

CREATE TABLE "user_struct" (
    "fid" INTEGER NOT NULL PRIMARY KEY
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('user_struct', 'features', 4326);
SELECT gpkgAddGeometryColumn('user_struct', 'geom', 'LINESTRING', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('user_struct', 'geom');


CREATE TABLE "rat_curves" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "struct_fid" INTEGER, -- structure fid, for which the data are defined
    "hdepexc" REAL, -- HDEPEXC, maximum depth that a hydraulic structure rating curve is valid
    "coefq" REAL, -- COEFQ, discharge rating curve coefficients as a power function of the headwater depth. If 0 discharge is calculated as normal depth flow routing
    "expq" REAL, -- EXPQ, hydraulic structure discharge exponent where the discharge is expressed as a power function of the headwater depth
    "coefa" REAL, -- COEFA, flow area rating curve coefficient where the flow area A is expressed as a power function of the headwater depth, A = COEFA * depth**EXPA
    "expa" REAL -- EXPA, hydraulic structure flow area exponent where the flow area is expressed as a power function of the headwater depth
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('rat_curves', 'aspatial');

CREATE TABLE "repl_rat_curves" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "struct_fid" INTEGER, -- structure fid, for which the data are defined
    "repdep" REAL, -- REPDEP, flow depth that if exceeded will invoke the replacement structure rating curve parameters
    "rqcoef" REAL, -- RQCOEFQ (or RQCOEF), structure rating curve discharge replacement coefficients
    "rqexp" REAL, -- RQEXP, structure rating curve discharge replacement exponent
    "racoef" REAL, -- RACOEF, structure rating curve flow area replacement coefficient
    "raexp" REAL -- RAEXP, structure rating curve flow area replacement exponent
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('repl_rat_curves', 'aspatial');

CREATE TABLE "rat_table" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "struct_fid" INTEGER, -- structure fid, for which the data are defined
    "hdepth" REAL, -- HDEPTH, headwater depth for the structure headwater depth-discharge rating table
    "qtable" REAL, -- QTABLE, hydraulic structure discharges for the headwater depths
    "atable" REAL -- ATABLE, hydraulic structure flow area for each headwater depth in the rating table
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('rat_table', 'aspatial');

CREATE TABLE "culvert_equations" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "struct_fid" INTEGER, -- structure fid, for which the data are defined
    "typec" INTEGER, -- TYPEC, culvert switch, 1 for a box culvert and 2 for a pipe culvert
    "typeen" INTEGER, -- TYPEEN, culvert switch for entrance type 1, 2, or 3
    "culvertn" REAL, -- CULVERTN, culvert Manning’s roughness coefficient
    "ke" REAL, -- KE, culvert entrance loss coefficient
    "cubase" REAL -- CUBASE, flow width of box culvert for TYPEC = 1. For a circular culvert, CUBASE = 0
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('culvert_equations', 'aspatial');

CREATE TABLE "storm_drains" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "struct_fid" INTEGER, -- structure fid, for which the data are defined
    "istormdout" INTEGER, -- ISTORMDOUT, hydraulic structure outflow grid element number used to simulate a simplified storm drain (junction or outflow node)
    "stormdmax" REAL -- STORMDMAX, maximum allowable discharge (conveyance capacity) of the collection pipe represented by the ISTORMDOUT element.
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('storm_drains', 'aspatial');


-- STREET.DAT

CREATE TABLE "street_general" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "strman" REAL, -- STRMAN, global n-value for street flow
    "istrflo" INTEGER, -- ISTRFLO, if equal to 1 specifies that the floodplain inflow hydrograph will enter the streets rather than entering the overland portion of the grid element
    "strfno" REAL, -- STRFNO, maximum street Froude number
    "depx" REAL, -- DEPX, street curb height
    "widst" REAL -- WIDST, global assignment of street width to all streets
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('street_general', 'aspatial');

CREATE TABLE "streets" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "stname" TEXT, -- STNAME, character name of the street. Up to 15 characters can be used
    "notes" TEXT -- notes for a street
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('streets', 'aspatial');

CREATE TABLE "street_seg" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "str_fid" INTEGER, -- street fid for the street segment (from streets table)
    "igridn" INTEGER, -- IGRIDN, grid element number
    "depex" REAL, -- DEPX(L) or DEPEX(L), optional curb height, 0 to use global DEPX
    "stman" REAL, -- STMAN(L), optional spatially variable street n-value within a given grid element. 0 for global
    "elstr" REAL -- ELSTR(L), optional street elevation. If 0, the model will assign the street elevation as grid element elevation
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('street_seg', 'features', 4326);
SELECT gpkgAddGeometryColumn('street_seg', 'geom', 'MULTILINESTRING', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('street_seg', 'geom');
-- SELECT gpkgAddSpatialIndex('street_seg', 'geom');

CREATE TABLE "street_elems" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "seg_fid" INTEGER, -- street segment fid for the street element (from street_seg table)
    "istdir" INTEGER, -- ISTDIR, street element direction (flow direction) from the center of the grid element to a neighboring element, 1-8
    "widr" REAL -- WIDR, optional grid element street width in the ISTDIR direction
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('street_elems', 'aspatial');

-- TODO: geometry triggers fro streets


-- ARF.DAT

-- CREATE TABLE "blocked_areas_tot" (
--     "fid" INTEGER NOT NULL PRIMARY KEY
-- );
-- INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('blocked_areas_tot', 'features', 4326);
-- SELECT gpkgAddGeometryColumn('blocked_areas_tot', 'geom', 'POLYGON', 0, 0, 0);
-- SELECT gpkgAddGeometryTriggers('blocked_areas_tot', 'geom');
-- -- SELECT gpkgAddSpatialIndex('blocked_areas_tot', 'geom');
-- 
-- CREATE TABLE "blocked_cells_tot" (
--     "fid" INTEGER NOT NULL PRIMARY KEY,
--     "grid_fid" INTEGER, -- equal to fid from grid table
--     "area_fid" INTEGER -- fid of area from blocked_areas_tot table
-- );
-- INSERT INTO gpkg_contents (table_name, data_type) VALUES ('blocked_cells_tot', 'aspatial');

--CREATE TRIGGER "find_cells_arf_tot_insert"
--    AFTER INSERT ON "blocked_areas_tot"
--    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--    BEGIN
--        DELETE FROM "blocked_cells_tot" WHERE area_fid = NEW."fid";
--        INSERT INTO "blocked_cells_tot" (area_fid, grid_fid)
--            SELECT NEW.fid, g.fid FROM grid as g
--            WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_cells_arf_tot_update"
--    AFTER UPDATE ON "blocked_areas_tot"
--    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--    BEGIN
--        DELETE FROM "blocked_cells_tot" WHERE area_fid = NEW."fid";
--        INSERT INTO "blocked_cells_tot" (area_fid, grid_fid)
--        SELECT NEW.fid, g.fid FROM grid as g
--        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_cells_arf_tot_delete"
--    AFTER DELETE ON "blocked_areas_tot"
--    BEGIN
--        DELETE FROM "blocked_cells_tot" WHERE area_fid = OLD."fid";
--    END;

CREATE TABLE "blocked_areas" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "collapse" INTEGER, -- collapse option for blocking object
    "calc_arf" INTEGER, -- flag for calculating ARFs
    "calc_wrf" INTEGER -- flag for calculating WRFs
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('blocked_areas', 'features', 4326);
SELECT gpkgAddGeometryColumn('blocked_areas', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('blocked_areas', 'geom');
-- SELECT gpkgAddSpatialIndex('blocked_areas', 'geom');

CREATE TABLE "blocked_cells" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "grid_fid" INTEGER, -- equal to fid from grid table
    "area_fid" INTEGER, -- fid of area from blocked_areas table
    "arf" REAL, -- ARF, area reduction factor for cells
    "wrf1" REAL, -- WRF(I,J), width reduction factor for the North direction
    "wrf2" REAL, -- WRF(I,J), width reduction factor for the East direction
    "wrf3" REAL, -- WRF(I,J), width reduction factor for the South direction
    "wrf4" REAL, -- WRF(I,J), width reduction factor for the West direction
    "wrf5" REAL, -- WRF(I,J), width reduction factor for the Northeast direction
    "wrf6" REAL, -- WRF(I,J), width reduction factor for the Southeast direction
    "wrf7" REAL, -- WRF(I,J), width reduction factor for the Southwest direction
    "wrf8" REAL  -- WRF(I,J), width reduction factor for the Northwest direction
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('blocked_cells', 'features', 4326);
SELECT gpkgAddGeometryColumn('blocked_cells', 'geom', 'POINT', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('blocked_cells', 'geom');
-- SELECT gpkgAddSpatialIndex('blocked_cells', 'geom');

CREATE VIEW arfwrf AS SELECT b.fid, b.grid_fid, b.arf, b.wrf1, b.wrf2, b.wrf3, b.wrf4, b.wrf5, b.wrf6, b.wrf7, b.wrf8, g.geom FROM blocked_cells as b, grid as g where g.fid = b.grid_fid;
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('arfwrf', 'features', 4326);
INSERT INTO gpkg_geometry_columns (table_name, column_name, geometry_type_name, srs_id, z, m) VALUES ('arfwrf', 'geom', 'POLYGON', 4326, 0, 0);

CREATE VIEW wrf AS SELECT b.fid, b.grid_fid, b.arf, b.wrf1, b.wrf2, b.wrf3, b.wrf4, b.wrf5, b.wrf6, b.wrf7, b.wrf8, g.geom FROM blocked_cells as b, grid as g where b.arf <> 1 AND g.fid = b.grid_fid;
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('wrf', 'features', 4326);
INSERT INTO gpkg_geometry_columns (table_name, column_name, geometry_type_name, srs_id, z, m) VALUES ('wrf', 'geom', 'POLYGON', 4326, 0, 0);


CREATE VIEW arf AS SELECT b.fid, b.grid_fid, b.arf, g.geom FROM blocked_cells as b, grid as g where g.fid = b.grid_fid;
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('arf', 'features', 4326);
INSERT INTO gpkg_geometry_columns (table_name, column_name, geometry_type_name, srs_id, z, m) VALUES ('arf', 'geom', 'POLYGON', 4326, 0, 0);

--CREATE TRIGGER "find_cells_arf_insert"
--    AFTER INSERT ON "blocked_areas"
--    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--    BEGIN
--        DELETE FROM "blocked_cells" WHERE area_fid = NEW."fid";
--        INSERT INTO "blocked_cells" (area_fid, grid_fid)
--            SELECT NEW.fid, g.fid FROM grid as g
--            WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_cells_arf_update"
--    AFTER UPDATE ON "blocked_areas"
--    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--    BEGIN
--        DELETE FROM "blocked_cells" WHERE area_fid = NEW."fid";
--        INSERT INTO "blocked_cells" (area_fid, grid_fid)
--        SELECT NEW.fid, g.fid FROM grid as g
--        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_cells_arf_delete"
--    AFTER DELETE ON "blocked_areas"
--    BEGIN
--        DELETE FROM "blocked_cells" WHERE area_fid = OLD."fid";
--    END;


-- MULT.DAT

CREATE TABLE "mult" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "wmc" REAL, -- WMC, incremental width by which multiple channels will be expanded when the maximum depth DM is exceeded
    "wdrall" REAL, -- WDRALL, global assignment of the multiple channel width
    "dmall" REAL, -- DMALL, global assignment of the maximum depth
    "nodchansall" INTEGER, -- NODCHNSALL, global assignment of the number of multiple channels
    "xnmultall" REAL, -- XNMULTALL, global assignment of the multiple channel n-values
    "sslopemin" REAL, -- SSLOPEMIN, minimum slope that multiple channel assignments will be made
    "sslopemax" REAL, -- SSLOPEMAX, maximum slope that multiple channel assignments will be made
    "avuld50" REAL -- AVULD50, D50 sediment size that initiates the potential for channel avulsion
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('mult', 'aspatial');

CREATE TABLE "mult_areas" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "wdr" REAL, -- WDR, channel width for individual grid elements
    "dm" REAL, -- DM, maximum depth of multiple channels
    "nodchns" REAL, -- NODCHNS, number of multiple channels assigned in a grid element
    "xnmult" REAL -- XNMULT, channel n-values for individual grid elements
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('mult_areas', 'features', 4326);
SELECT gpkgAddGeometryColumn('mult_areas', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('mult_areas', 'geom');
-- SELECT gpkgAddSpatialIndex('mult_areas', 'geom');

CREATE TABLE "mult_cells" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "grid_fid" INTEGER, -- equal to fid from grid table
    "area_fid" INTEGER -- fid of area from mult_areas table
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('mult_cells', 'aspatial');

--CREATE TRIGGER "find_cells_mult_insert"
--    AFTER INSERT ON "mult_areas"
--    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--    BEGIN
--        DELETE FROM "mult_cells" WHERE area_fid = NEW."fid";
--        INSERT INTO "mult_cells" (area_fid, grid_fid)
--            SELECT NEW.fid, g.fid FROM grid as g
--            WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_cells_mult_update"
--    AFTER UPDATE ON "mult_areas"
--    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
--    BEGIN
--        DELETE FROM "mult_cells" WHERE area_fid = NEW."fid";
--        INSERT INTO "mult_cells" (area_fid, grid_fid)
--        SELECT NEW.fid, g.fid FROM grid as g
--        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
--    END;
--
--CREATE TRIGGER "find_cells_mult_delete"
--    AFTER DELETE ON "mult_areas"
--    BEGIN
--        DELETE FROM "mult_cells" WHERE area_fid = OLD."fid";
--    END;


-- LEVEE.DAT

CREATE TABLE "levee_general" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "raiselev" REAL, -- RAISELEV, incremental height that all the levee grid element crest elevations are raised
    "ilevfail" INTEGER, -- ILEVFAIL, switch identifying levee failure mode: 0 for no failure, 1 for prescribed level failure rates, 2 for initiation of levee or dam breach failure routine
    "gfragchar" TEXT, -- GFRAGCHAR, global levee fragility curve ID
    "gfragprob" REAL -- GFRAGPROB, global levee fragility curve failure probability
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('levee_general', 'aspatial');

CREATE TABLE "levee_data" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "grid_fid" INTEGER, -- LGRIDNO, grid element fid with a levee
    "ldir" INTEGER, -- LDIR, flow direction that will be cutoff (1-8)
    "levcrest" REAL, -- LEVCREST, the elevation of the levee crest,
    "user_line_fid" INTEGER -- FID of parent user levee line
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('levee_data', 'features', 4326);
SELECT gpkgAddGeometryColumn('levee_data', 'geom', 'LINESTRING', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('levee_data', 'geom');
-- SELECT gpkgAddSpatialIndex('levee_data', 'geom');

CREATE TABLE "levee_failure" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "grid_fid" INTEGER, -- LFAILGRID, grid element fid with a failure potential
    "lfaildir" INTEGER, -- LFAILDIR, the potential failure direction
    "failevel" REAL, -- FAILEVEL, the maximum elevation of the prescribed levee failure
    "failtime" REAL, -- FAILTIME, the duration (hr) that the levee will fail after the FAILEVEL elevation is exceeded by the flow depth
    "levbase" REAL, -- LEVBASE, the prescribed final failure elevation
    "failwidthmax" REAL, -- FAILWIDTHMAX, the maximum breach width
    "failrate" REAL, -- FAILRATE, the rate of vertical levee failure
    "failwidrate" REAL -- FAILWIDRATE, the rate at which the levee breach widens
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('levee_failure', 'aspatial');

CREATE TABLE "levee_fragility" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "grid_fid" INTEGER, -- LEVFRAGGRID, grid element fid with an individual fragility curve assignment
    "levfragchar" TEXT, -- LEVFRAGCHAR, levee fragility curve ID
    "levfragprob" REAL -- LEVFRAGPROB, levee fragility curve failure probability
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('levee_fragility', 'aspatial');


-- FPXSEC.DAT

CREATE TABLE "fpxsec" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "iflo" INTEGER, -- IFLO, general direction that the flow is expected to cross the floodplain cross section
    "nnxsec" INTEGER -- NNXSEC, number of floodplain elements in a given cross section
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('fpxsec', 'features', 4326);
SELECT gpkgAddGeometryColumn('fpxsec', 'geom', 'LINESTRING', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('fpxsec', 'geom');
-- SELECT gpkgAddSpatialIndex('fpxsec', 'geom');

CREATE TABLE "fpxsec_cells" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "fpxsec_fid" INTEGER, -- fid of a floodplain xsection from fpxsec table
    "grid_fid" INTEGER -- NODX, fid of grid cell contained in a fpxsection
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('fpxsec_cells', 'features', 4326);
SELECT gpkgAddGeometryColumn('fpxsec_cells', 'geom', 'POINT', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('fpxsec_cells', 'geom');


-- FPFROUDE.DAT

CREATE TABLE "fpfroude" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "froudefp" REAL -- FROUDEFP, Froude number for grid elements
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('fpfroude', 'features', 4326);
SELECT gpkgAddGeometryColumn('fpfroude', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('fpfroude', 'geom');
-- SELECT gpkgAddSpatialIndex('fpfroude', 'geom');

CREATE TABLE "fpfroude_cells" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "area_fid" INTEGER, -- fid of area from frfroude table
    "grid_fid" INTEGER -- grid element fid that has an individual Froude number
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('fpfroude_cells', 'aspatial');


-- SWMMFLO.DAT

CREATE TABLE "swmmflo" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "swmm_jt" INTEGER, -- SWMM_JT, fid of the grid element with storm drain inlet
    "intype" INTEGER, -- INTYPE, inlet type (1-5)
    "swmm_length" REAL, -- SWMMlength, storm drain inlet curb opening lengths along the curb
    "swmm_height" REAL, -- SWMMheight, storm drain curb opening height
    "swmm_width" REAL, -- SWMMwidth
    "swmm_coeff" REAL, -- SWMMcoeff, storm drain inlet weir discharge coefficient
    "flapgate" INTEGER, -- FLAPGATE, switch (0 no flap gate, 1 flapgate)
    "name" TEXT -- optional inlet name
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('swmmflo', 'features', 4326);
SELECT gpkgAddGeometryColumn('swmmflo', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('swmmflo', 'geom');
-- SELECT gpkgAddSpatialIndex('swmmflo', 'geom');


-- SWMMFLORT.DAT

CREATE TABLE "swmmflort" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "grid_fid" INTEGER, -- SWMM_JT, fid of the grid element with a storm drain inlet
    "name" TEXT -- optional name of the rating table
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('swmmflort', 'aspatial');

CREATE TABLE "swmmflort_data" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "swmm_rt_fid" INTEGER, -- fid of a rating table from swmmflort
    "depth" REAL, -- DEPTHSWMMRT, flow depths for the discharge rating table pairs
    "q" REAL -- QSWMMRT, discharge values for the storm drain inlet rating table
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('swmmflort_data', 'aspatial');


-- SWMMOUTF.DAT

CREATE TABLE "swmmoutf" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "grid_fid" INTEGER, -- OUTF_GRID, fid of the grid element with a storm drain outflow
    "name" TEXT, -- OUTF_NAME, name of the outflow
    "outf_flo" INTEGER -- OUTF_FLO2DVOL, switch, 0 for all discharge removed from strom drain system, 1 allows for the discharge to be returned to FLO-2D
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('swmmoutf', 'features', 4326);
SELECT gpkgAddGeometryColumn('swmmoutf', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('swmmoutf', 'geom');
-- SELECT gpkgAddSpatialIndex('swmmoutf', 'geom');


-- TOLSPATIAL.DAT

CREATE TABLE "tolspatial" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "tol" REAL -- TOL, tollerance for grid cells contained in the polygon. A grid cell is considered contained in a polygon if its centroid is contained in it.
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('tolspatial', 'features', 4326);
SELECT gpkgAddGeometryColumn('tolspatial', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('tolspatial', 'geom');
-- SELECT gpkgAddSpatialIndex('tolspatial', 'geom');

CREATE TABLE "tolspatial_cells" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "area_fid" INTEGER, -- fid of a polygon from tolspatial table
    "grid_fid" INTEGER -- IDUM, fid of grid cell contained in a fpxsection
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('tolspatial_cells', 'aspatial');


-- WSURF.DAT

CREATE TABLE "wsurf" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "grid_fid" INTEGER, -- IGRIDXSEC, fid of grid cell containing WSEL data
    "wselev" REAL -- WSELEV, water surface elevation for comparison
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('wsurf', 'features', 4326);
SELECT gpkgAddGeometryColumn('wsurf', 'geom', 'POINT', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('wsurf', 'geom');
-- SELECT gpkgAddSpatialIndex('wsurf', 'geom');


-- WSTIME.DAT

CREATE TABLE "wstime" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "grid_fid" INTEGER, -- IGRIDXSEC, fid of grid cell containing WSEL data
    "wselev" REAL, -- WSELEVTIME, water surface elevation for comparison
    "wstime" REAL -- WSTIME, time of known watersurface elevation
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('wstime', 'features', 4326);
SELECT gpkgAddGeometryColumn('wstime', 'geom', 'POINT', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('wstime', 'geom');
-- SELECT gpkgAddSpatialIndex('wstime', 'geom');


-- BREACH.DAT

CREATE TABLE "breach_global" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "ibreachsedeqn" INTEGER, -- IBREACHSEDEQN, sediment transport equation number
    "gbratio" REAL, -- GBRATIO, global ratio of the initial breach width to breach depth
    "gweircoef" REAL, -- GWEIRCOEF, global weir coefficient for piping or breach channel weir for an unspecified failure location
    "gbreachtime" REAL, -- GBREACHTIME, cumulative duration (hrs) that the levee erosion will initiate after the water surface exceeds the specified pipe elevation BRBOTTOMEL
    "gzu" REAL, -- GZU, global slope of the upstream face of the levee or dam for an unspecified failure location
    "gzd" REAL, -- GZD, global slope of the downstream face of the levee or dam
    "gzc" REAL, -- GZC, global average slope of the upstream and downstream face of the levee or dam core material
    "gcrestwidth" REAL, -- GCRESTWIDTH, global crest length of the levee or dam
    "gcrestlength" REAL, -- GCRESTLENGTH, global crest length of the levee or dam
    "gbrbotwidmax" REAL, -- GBRBOTWIDMAX, maximum allowable global breach bottom width (ft or m) as constrained by the valley cross section
    "gbrtopwidmax" REAL, -- GBRTOPWIDMAX, maximum allowable global breach top width (ft or m) as constrained by the valley cross section
    "gbrbottomel" REAL, -- GBRBOTTOMEL, initial global breach or pipe bottom elevation (ft or m)
    "gd50c" REAL, -- GD50C, mean sediment size (D50 in mm) of the levee or dam core material
    "gporc" REAL, -- GPORC, global porosity of the levee or dam core material
    "guwc" REAL, -- GUWC, global unit weight (lb/ft 3 or N/m 3 ) of the levee or dam core material
    "gcnc" REAL, -- GCNC, global Manning’s n-value of the levee or dam core material
    "gafrc" REAL, -- GAFRC, global angle (degrees) of internal friction of the core material for the entire levee or dam, 0 for no core
    "gcohc" REAL, -- GCOHC, global cohesive strength (lb/ft 2 or N/m 2 ) of the levee or dam core material
    "gunfcc" REAL, -- GUNFCC, global sediment gradient, ratio of D90 to D30 of the levee or dam core material
    "gd50s" REAL, -- GD50S, mean sediment size (D50 in mm) of the levee or dam shell material
    "gpors" REAL, -- GPORS, global porosity of the levee or dam shell material
    "guws" REAL, -- GUWS, global unit weight (lb/ft 3 or N/m 3 ) of the levee or dam shell material
    "gcns" REAL, -- GCNS, global Manning’s n-value of the levee or dam shell material
    "gafrs" REAL, -- GAFRS, global angle (degrees) of internal friction of the shell material for the entire levee or dam, 0 for no core
    "gcohs" REAL, -- GCOHS, global cohesive strength (lb/ft 2 or N/m 2 ) of the levee or dam shell material
    "gunfcs" REAL, -- GUNFCS, global sediment gradient, ratio of D90 to D30 of the levee or dam shell material
    "ggrasslength" REAL, -- GGRASSLENGTH, global average length of grass (inches or mm) on downstream face
    "ggrasscond" REAL, -- GGRASSCOND, condition of the grass on the downstream face
    "ggrassvmaxp" REAL, -- GGRASSVMAXP, global maximum permissible velocity (fps or mps) for a grass-lined downstream face before the grass is eroded
    "gsedconmax" REAL, -- GSEDCONMAX, global maximum sediment concentration by volume in the breach discharge
    "d50df" REAL, -- D50DF, mean sediment size (D50 in mm) of the top one foot (0.3 m) of the downstream face (riprap material)
    "gunfcdf" REAL -- GUNFCDF, global sediment gradient, ratio of D 90 to D 30 of the downstream face upper one foot of material (riprap)
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('breach_global', 'aspatial');

CREATE TABLE "breach" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "ibreachdir" INTEGER, -- IBREACHDIR, direction of breach
    "zu" REAL, -- ZU, slope of the upstream face of the levee or dam
    "zd" REAL, -- ZD, slope of the downstream face of the levee or dam
    "zc" REAL, -- ZC, average slope of the upstream and downstream face of the levee or dam core material
    "crestwidth" REAL, -- CRESTWIDTH, crest width of the levee or dam
    "crestlength" REAL, -- CRESTLENGTH, length of the crest of the levee or dam
    "brbotwidmax" REAL, -- BRBOTWIDMAX, maximum allowable breach bottom width (ft or m) as constrained by the valley cross section
    "brtopwidmax" REAL, -- BRTOPWIDMAX, maximum allowable breach top width (ft or m) as constrained by the valley cross section
    "brbottomel" REAL, -- BRBOTTOMEL, initial breach or pipe bottom elevation (ft or m)
    "weircoef" REAL, -- WEIRCOEF, weir coefficient for piping or breach channel weir
    "d50c" REAL, -- D50C, mean sediment size (D50 in mm) of the levee or dam core material
    "porc" REAL, -- PORC, porosity of the levee or dam core material
    "uwc" REAL, -- UWC, unit weight (lb/ft 3 or N/m 3 ) of the levee or dam core material
    "cnc" REAL, -- CNC, global Manning’s n-value of the levee or dam core material
    "afrc" REAL, -- AFRC, angle (degrees) of internal friction of the core material for the entire levee or dam, 0 for no core
    "cohc" REAL, -- COHC, cohesive strength (lb/ft 2 or N/m 2 ) of the levee or dam core material
    "unfcc" REAL, -- UNFCC, sediment gradient, ratio of D90 to D30 of the levee or dam core material
    "d50s" REAL, -- D50S, mean sediment size (D50 in mm) of the levee or dam shell material
    "pors" REAL, -- PORS, porosity of the levee or dam shell material
    "uws" REAL, -- UWS, unit weight (lb/ft 3 or N/m 3 ) of the levee or dam shell material
    "cns" REAL, -- CNS, Manning’s n-value of the levee or dam shell material
    "afrs" REAL, -- AFRS, angle (degrees) of internal friction of the shell material for the entire levee or dam, 0 for no core
    "cohs" REAL, -- COHS, cohesive strength (lb/ft 2 or N/m 2 ) of the levee or dam shell material
    "unfcs" REAL, -- UNFCS, sediment gradient, ratio of D90 to D30 of the levee or dam shell material
    "bratio" REAL, -- BRATIO, ratio of the initial breach width to breach depth
    "grasslength" REAL, -- GRASSLENGTH, average length of grass (inches or mm) on downstream face
    "grasscond" REAL, -- GRASSCOND, condition of the grass on the downstream face
    "grassvmaxp" REAL, -- GRASSVMAXP, maximum permissible velocity (fps or mps) for a grass-lined downstream face before the grass is eroded
    "sedconmax" REAL, -- maximum sediment concentration by volume in the breach discharge
    "d50df" REAL, -- D50DF, mean sediment size (D50 in mm) of the top one foot (0.3 m) of the downstream face (riprap material)
    "unfcdf" REAL, -- UNFCDF, sediment gradient, ratio of D 90 to D 30 of the downstream face upper one foot of material (riprap)
    "breachtime" REAL -- BREACHTIME, cumulative duration (hrs) that the levee erosion will initiate after the water surface exceeds the specified pipe elevation BRBOTTOMEL
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('breach', 'features', 4326);
SELECT gpkgAddGeometryColumn('breach', 'geom', 'POINT', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('breach', 'geom');
-- SELECT gpkgAddSpatialIndex('breach', 'geom');

CREATE TABLE "breach_cells" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "breach_fid" INTEGER, -- fid of a breach from breach table
    "grid_fid" INTEGER -- IBREACHGRID, grid element fid for which an individual breach parameters are defined
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('breach_cells', 'aspatial');

CREATE TABLE "breach_fragility_curves" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "fragchar" TEXT, -- FRAGCHAR, fragility curve ID - one letter and a number
    "prfail" REAL, -- PRFAIL, levee fragility curve point of failure probability
    "prdepth" REAL -- PRDEPTH, point of failure on the levee as defined by the distance or height below the levee crest
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('breach_fragility_curves', 'aspatial');


-- SED.DAT

CREATE TABLE "mud" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "va" REAL, -- VA, coefficient in the viscosity versus sediment concentration by volume relationship
    "vb" REAL, -- VB, exponent in the viscosity versus sediment concentration by volume relationship
    "ysa" REAL, -- YSA, coefficient of the yield stress versus sediment concentration
    "ysb" REAL, -- YSB, exponent of yield stress versus sediment concentration
    "sgsm" REAL, -- SGSM, mudflow mixtures specific gravity
    "xkx" REAL -- XKX, the laminar flow resistance parameter for overland flow
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('mud', 'aspatial');

CREATE TABLE "mud_areas" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "debrisv" REAL -- DEBRISV, volume of the debris basin
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('mud_areas', 'features', 4326);
SELECT gpkgAddGeometryColumn('mud_areas', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('mud_areas', 'geom');
-- SELECT gpkgAddSpatialIndex('mud_areas', 'geom');

CREATE TABLE "mud_cells" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "grid_fid" INTEGER, -- JDEBNOD, grid element fid with debris basin
    "area_fid" INTEGER -- fid of area from mud_areas table, where the cell belongs to
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('mud_cells', 'aspatial');

CREATE TABLE "sed" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "isedeqg" INTEGER, -- ISEDEQG, transport equation number used in sediment routing for overland flow
    "isedsizefrac" INTEGER, -- ISEDSIZEFRAC, switch, if 1 sediment routing will be performed by size fraction, 0 for sed routing not by size fraction
    "dfifty" REAL, -- DFIFTY, sediment size (D50) in mm for sediment routing
    "sgrad" REAL, -- SGRAD, sediment gradation coefficient (non-dimensional)
    "sgst" REAL, -- SGST, sediment specific gravity
    "dryspwt" REAL, -- DRYSPWT, dry specific weight of the sediment
    "cvfg" REAL, -- CVFG, fine sediment volumetric concentration for overland, channel, and streets
    "isedsupply" INTEGER, -- ISEDSUPPLY, if 1 sediment rating curve will be used to define the sediment supply to a channel reach or floodplain area, otherwise 0
    "isedisplay" INTEGER, -- ISEDISPLAY, grid element number for which the sediment transport capacity for all the sediment transport equations will be listed by output
    "scourdep" REAL -- maximum allowable scour depth for all floodplain elements
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('sed', 'aspatial');

CREATE TABLE "sed_groups" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "isedeqi" INTEGER, -- ISEDEQI, sediment transport equation used for sediment routing by size fraction
    "bedthick" REAL, -- BEDTHICK, sediment bed thickness for sediment routing by size fraction
    "cvfi" REAL, -- CVFI, fine sediment volumetric concentration for an individual channel segment(s)
    "name" TEXT, -- name of the sediment transport parameters group
    "dist_fid" INTEGER -- fraction distribution number (from sed_group_frac table) for that group
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('sed_groups', 'aspatial');

CREATE TABLE "sed_group_areas" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "group_fid" INTEGER -- sediment group fid for area (from sed_groups table)
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('sed_group_areas', 'features', 4326);
SELECT gpkgAddGeometryColumn('sed_group_areas', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('sed_group_areas', 'geom');
-- SELECT gpkgAddSpatialIndex('sed_group_areas', 'geom');

CREATE TABLE "sed_group_frac" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "name" TEXT -- name of the fraction distribution
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('sed_group_frac', 'aspatial');

CREATE TABLE "sed_group_frac_data" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "dist_fid" INTEGER, -- fraction distribution number, equal to dist_fid from sed_groups table
    "sediam" REAL, -- SEDIAM, representative sediment diameter (mm) for sediment routing by size fraction
    "sedpercent" REAL -- SEDPERCENT, sediment size distribution percentage
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('sed_group_frac_data', 'aspatial');

CREATE TABLE "sed_group_cells" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "grid_fid" INTEGER, -- ISEDUM, grid element fid for which a sediment group is defined
    "area_fid" INTEGER -- fid of area from sed_group_areas table, where the cell belongs to
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('sed_group_cells', 'aspatial');

CREATE TABLE "sed_rigid_areas" (
    "fid" INTEGER NOT NULL PRIMARY KEY
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('sed_rigid_areas', 'features', 4326);
SELECT gpkgAddGeometryColumn('sed_rigid_areas', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('sed_rigid_areas', 'geom');
-- SELECT gpkgAddSpatialIndex('sed_rigid_areas', 'geom');

CREATE TABLE "sed_rigid_cells" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "grid_fid" INTEGER, -- ICRETIN, grid element fid for which the rigid bed is defined
    "area_fid" INTEGER-- area fid with rigid bed defined (from sed_rigid_areas)
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('sed_rigid_cells', 'aspatial');

CREATE TABLE "sed_supply_areas" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "isedcfp" INTEGER, -- ISEDCFP, switch, 0 for floodplain sediment supply rating curve, 1 for channel
    "ased" REAL, -- ASED, sediment rating curve coefficient
    "bsed" REAL, -- BSED, sediment rating curve exponent, Qs = ASED * Qw ^ BSED
    "dist_fid" INTEGER -- named sediment supply fraction distribution fid from sed_supply_frac table
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('sed_supply_areas', 'features', 4326);
SELECT gpkgAddGeometryColumn('sed_supply_areas', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('sed_supply_areas', 'geom');
-- SELECT gpkgAddSpatialIndex('sed_supply_areas', 'geom');

CREATE TABLE "sed_supply_cells" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "grid_fid" INTEGER, -- ISEDGRID, grid element fid for which sediment supply is defined
    "area_fid" INTEGER -- area fid with a sediment supply defined (from sed_supply_areas)
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('sed_supply_cells', 'aspatial');

CREATE TABLE "sed_supply_frac" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "name" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('sed_supply_frac', 'aspatial');

CREATE TABLE "sed_supply_frac_data" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "dist_fid" INTEGER, -- nr of distribution the fraction belongs to, from sed_supply_frac table
    "ssediam" REAL, -- SSEDIAM, representative sediment supply diameter (mm) for sediment routing by size fraction
    "ssedpercent" REAL -- SSEDPERCENT, sediment supply size distribution percentage
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('sed_supply_frac_data', 'aspatial');

-- USERS Layers
CREATE TABLE "user_fpxsec" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "iflo" INTEGER, -- IFLO, general direction that the flow is expected to cross the floodplain cross section
    "name" TEXT -- name of fpxsec
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('user_fpxsec', 'features', 4326);
SELECT gpkgAddGeometryColumn('user_fpxsec', 'geom', 'LINESTRING', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('user_fpxsec', 'geom');

CREATE TABLE "user_model_boundary" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "cell_size" REAL
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('user_model_boundary', 'features', 4326);
SELECT gpkgAddGeometryColumn('user_model_boundary', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('user_model_boundary', 'geom');
-- SELECT gpkgAddSpatialIndex('user_model_boundary', 'geom');

CREATE TABLE "user_1d_domain" (
    "fid" INTEGER PRIMARY KEY NOT NULL
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('user_1d_domain', 'features', 4326);
SELECT gpkgAddGeometryColumn('user_1d_domain', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('user_1d_domain', 'geom');

CREATE TABLE "user_left_bank" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "name" TEXT, -- name of segment (optional)
    "depinitial" REAL, -- DEPINITIAL, initial channel flow depth
    "froudc" REAL, -- FROUDC, max Froude channel number
    "roughadj" REAL, -- ROUGHADJ, coefficient for depth adjustment
    "isedn" INTEGER, -- ISEDN, sediment transport equation or data
    "rank" INTEGER,
    "notes" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('user_left_bank', 'features', 4326);
SELECT gpkgAddGeometryColumn('user_left_bank', 'geom', 'LINESTRING', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('user_left_bank', 'geom');

-- USER XSECTIONS

CREATE TABLE "user_xsections" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "fcn" REAL, -- FCN, average Manning's n in the grid element
    "type" TEXT, -- SHAPE, type of cross-section shape definition
    "name" TEXT,
    "notes" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('user_xsections', 'features', 4326);
SELECT gpkgAddGeometryColumn('user_xsections', 'geom', 'LINESTRING', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('user_xsections', 'geom');
-- SELECT gpkgAddSpatialIndex('user_xsections', 'geom');

CREATE TABLE chan_elems_interp (
    "id" INTEGER PRIMARY KEY,
    "fid" INTEGER,
    "seg_fid" INTEGER,
    "up_fid" INTEGER, -- fid of upper user-based (not interpolated) chan_elem
    "lo_fid" INTEGER, -- fid of lower user-based chan_elem
    "up_lo_dist_left" REAL, -- distance between upper and lower user-based chan elems along left bank
    "up_lo_dist_right" REAL, -- distance between upper and lower user-based chan elems along right bank
    "up_dist_left" REAL, -- distance from the chan_elem along left bank
    "up_dist_right" REAL -- distance from the chan_elem along right bank
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('chan_elems_interp', 'aspatial');

CREATE TABLE "user_chan_r" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "user_xs_fid" INTEGER UNIQUE ON CONFLICT REPLACE, -- fid of the user cross-section
    "bankell" REAL, -- BANKELL, left bank elevation
    "bankelr" REAL, -- BANKELR, right bank elevation
    "fcw" REAL, -- FCW, channel width
    "fcd" REAL -- channel channel thalweg depth (deepest part measured from the lowest bank)

);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('user_chan_r', 'aspatial');

CREATE TABLE "user_chan_v" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "user_xs_fid" INTEGER UNIQUE ON CONFLICT REPLACE, -- fid of the user cross-section
    "bankell" REAL, -- BANKELL, left bank elevation
    "bankelr" REAL, -- BANKELR, right bank elevation
    "fcd" REAL, -- channel channel thalweg depth (deepest part measured from the lowest bank)
    "a1" REAL, -- A1,
    "a2" REAL, -- A2,
    "b1" REAL, -- B1,
    "b2" REAL, -- B2,
    "c1" REAL, -- C1,
    "c2" REAL, -- C2,
    "excdep" REAL, -- EXCDEP, channel depth above which second variable area relationship will be applied
    "a11" REAL, -- A11,
    "a22" REAL, -- A22,
    "b11" REAL, -- B11,
    "b22" REAL, -- B22,
    "c11" REAL, -- C11,
    "c22" REAL -- C22,
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('user_chan_v', 'aspatial');

CREATE TABLE "user_chan_t" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "user_xs_fid" INTEGER UNIQUE ON CONFLICT REPLACE, -- fid of the user cross-section
    "bankell" REAL, -- BANKELL, left bank elevation
    "bankelr" REAL, -- BANKELR, right bank elevation
    "fcw" REAL, -- FCW, channel width
    "fcd" REAL, -- channel channel thalweg depth (deepest part measured from the lowest bank)
    "zl" REAL, -- ZL left side slope
    "zr" REAL --ZR right side slope
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('user_chan_t', 'aspatial');

CREATE TABLE "user_chan_n" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "user_xs_fid" INTEGER UNIQUE ON CONFLICT REPLACE, -- fid of the user cross-section
    "nxsecnum" INTEGER, -- NXSECNUM, surveyed cross section number assigned in XSEC.DAT
    "xsecname" TEXT -- xsection name
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('user_chan_n', 'aspatial');

CREATE TABLE "user_xsec_n_data" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "chan_n_nxsecnum" INTEGER, -- NXSECNUM, fid of cross-section in chan_n
    "xi" REAL, -- XI, station - distance from left point
    "yi" REAL -- YI, elevation
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('user_xsec_n_data', 'aspatial');

-- USER LEVEES

CREATE TABLE "user_levee_points" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "name" TEXT,
    "elev" REAL,
    "correction" REAL
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('user_levee_points', 'features', 4326);
SELECT gpkgAddGeometryColumn('user_levee_points', 'geom', 'POINT', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('user_levee_points', 'geom');
-- SELECT gpkgAddSpatialIndex('user_levee_points', 'geom');

CREATE TABLE "user_levee_lines" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "name" TEXT,
    "elev" REAL,
    "correction" REAL
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('user_levee_lines', 'features', 4326);
SELECT gpkgAddGeometryColumn('user_levee_lines', 'geom', 'LINESTRING', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('user_levee_lines', 'geom');
-- SELECT gpkgAddSpatialIndex('user_levee_lines', 'geom');

CREATE TABLE "user_levee_polygons" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "name" TEXT,
    "elev" REAL,
    "correction" REAL
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('user_levee_polygons', 'features', 4326);
SELECT gpkgAddGeometryColumn('user_levee_polygons', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('user_levee_polygons', 'geom');
-- SELECT gpkgAddSpatialIndex('user_levee_polygons', 'geom');

CREATE TABLE "user_streets" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "name" TEXT DEFAULT '',
    "n_value" REAL DEFAULT 0, -- STMAN(L), optional spatially variable street n-value within a given grid element. 0 for global
    "elevation" REAL DEFAULT 0, -- ELSTR(L), optional street elevation. If 0, the model will assign the street elevation as grid element elevation
    "curb_height" REAL DEFAULT 0, -- DEPX(L) or DEPEX(L), optional curb height, 0 to use global DEPX
    "street_width" REAL DEFAULT 0, -- WIDR, optional grid element street width in the ISTDIR direction
    "notes" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('user_streets', 'features', 4326);
SELECT gpkgAddGeometryColumn('user_streets', 'geom', 'LINESTRING', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('user_streets', 'geom');
-- SELECT gpkgAddSpatialIndex('user_streets', 'geom');

CREATE TABLE "user_roughness" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "n" REAL,
    "code" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('user_roughness', 'features', 4326);
SELECT gpkgAddGeometryColumn('user_roughness', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('user_roughness', 'geom');
-- SELECT gpkgAddSpatialIndex('user_roughness', 'geom');

CREATE TABLE "user_elevation_polygons" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "elev" REAL,
    "correction" REAL
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('user_elevation_polygons', 'features', 4326);
SELECT gpkgAddGeometryColumn('user_elevation_polygons', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('user_elevation_polygons', 'geom');
-- SELECT gpkgAddSpatialIndex('user_elevation_polygons', 'geom');

CREATE TABLE "user_bc_points" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "type" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('user_bc_points', 'features', 4326);
SELECT gpkgAddGeometryColumn('user_bc_points', 'geom', 'POINT', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('user_bc_points', 'geom');
-- SELECT gpkgAddSpatialIndex('user_bc_points', 'geom');

-- START user_bc_points TRIGGERS

-- trigger for a new POINT INFLOW boundary
INSERT INTO trigger_control (name, enabled) VALUES ('update_inflow_on_bc_pts_insert', 1); -- enabled by default
CREATE TRIGGER "update_inflow_on_bc_pts_insert"
    AFTER INSERT ON "user_bc_points"
    WHEN (
        SELECT enabled FROM trigger_control WHERE name = 'update_inflow_on_bc_pts_insert' AND
        NEW."geom" NOT NULL AND NEW."type" = 'inflow'
    )
    BEGIN
        INSERT INTO "inflow" (geom_type, bc_fid) SELECT 'point', NEW."fid";
    END;

-- trigger for a new POINT OUTFLOW boundary
INSERT INTO trigger_control (name, enabled) VALUES ('update_outflow_on_bc_pts_insert', 1);
CREATE TRIGGER "update_outflow_on_bc_pts_insert"
    AFTER INSERT ON "user_bc_points"
    WHEN (
        SELECT enabled FROM trigger_control WHERE name = 'update_outflow_on_bc_pts_insert' AND
        NEW."geom" NOT NULL AND NEW."type" = 'outflow'
    )
    BEGIN
        INSERT INTO "outflow" (geom_type, bc_fid) SELECT 'point', NEW."fid";
    END;

-- point boundary updated - type: inflow
INSERT INTO trigger_control (name, enabled) VALUES ('update_inflow_on_bc_pts_update', 1);
CREATE TRIGGER "update_inflow_on_bc_pts_update"
    AFTER UPDATE ON "user_bc_points"
    WHEN (
        SELECT enabled FROM trigger_control WHERE name = 'update_inflow_on_bc_pts_update' AND
        NEW."type" = 'inflow'
    )
    BEGIN
        -- delete this bc from other tables
        DELETE FROM outflow WHERE bc_fid = NEW.fid AND geom_type = 'point';
        -- try to insert to the inflow table, ignore on fail (there is a unique constraint on inflow.bc_fid)
        INSERT OR IGNORE INTO inflow (geom_type, bc_fid) SELECT 'point', NEW."fid";
        -- update existing (includes geometry changes)
        UPDATE inflow SET geom_type = 'point' WHERE bc_fid = NEW.fid;
    END;

-- point boundary updated - type: outflow
INSERT INTO trigger_control (name, enabled) VALUES ('update_outflow_on_bc_pts_update', 1);
CREATE TRIGGER "update_outflow_on_bc_pts_update"
    AFTER UPDATE ON "user_bc_points"
    WHEN (
        SELECT enabled FROM trigger_control WHERE name = 'update_outflow_on_bc_pts_update' AND
        NEW."type" = 'outflow'
    )
    BEGIN
        -- delete this bc from other tables
        DELETE FROM inflow WHERE bc_fid = NEW.fid AND geom_type = 'point';
        -- try to insert to the inflow table, ignore on fail
        INSERT OR IGNORE INTO outflow (geom_type, bc_fid) SELECT 'point', NEW."fid";
        -- update existing (includes geometry changes)
        UPDATE outflow SET geom_type = 'point' WHERE bc_fid = NEW.fid;
    END;

-- inflow point boundary deleted
INSERT INTO trigger_control (name, enabled) VALUES ('update_inflow_on_bc_pts_delete', 1);
CREATE TRIGGER "update_inflow_on_bc_pts_delete"
    AFTER DELETE ON "user_bc_points"
    WHEN (
        SELECT enabled FROM trigger_control WHERE name = 'update_inflow_on_bc_pts_delete'
    )
    BEGIN
        DELETE FROM "inflow" WHERE bc_fid = OLD."fid" AND geom_type = 'point';
    END;

-- outflow point boundary deleted
INSERT INTO trigger_control (name, enabled) VALUES ('update_outflow_on_bc_pts_delete', 1);
CREATE TRIGGER "update_outflow_on_bc_pts_delete"
    AFTER DELETE ON "user_bc_points"
    WHEN (
        SELECT enabled FROM trigger_control WHERE name = 'update_outflow_on_bc_pts_delete'
    )
    BEGIN
        DELETE FROM "outflow" WHERE bc_fid = OLD."fid" AND geom_type = 'point';
    END;

-- END user_bc_points TRIGGERS


CREATE TABLE "user_bc_lines" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "type" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('user_bc_lines', 'features', 4326);
SELECT gpkgAddGeometryColumn('user_bc_lines', 'geom', 'LINESTRING', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('user_bc_lines', 'geom');
-- SELECT gpkgAddSpatialIndex('user_bc_lines', 'geom');

-- START user_bc_lines TRIGGERS

-- trigger for a new LINE INFLOW boundary
INSERT INTO trigger_control (name, enabled) VALUES ('update_inflow_on_bc_lines_insert', 1); -- enabled by default
CREATE TRIGGER "update_inflow_on_bc_lines_insert"
    AFTER INSERT ON "user_bc_lines"
    WHEN (
        SELECT enabled FROM trigger_control WHERE name = 'update_inflow_on_bc_lines_insert' AND
        NEW."geom" NOT NULL AND NEW."type" = 'inflow'
    )
    BEGIN
        INSERT INTO "inflow" (geom_type, bc_fid) SELECT 'line', NEW."fid";
    END;

-- trigger for a new LINE OUTFLOW boundary
INSERT INTO trigger_control (name, enabled) VALUES ('update_outflow_on_bc_lines_insert', 1);
CREATE TRIGGER "update_outflow_on_bc_lines_insert"
    AFTER INSERT ON "user_bc_lines"
    WHEN (
        SELECT enabled FROM trigger_control WHERE name = 'update_outflow_on_bc_lines_insert' AND
        NEW."geom" NOT NULL AND NEW."type" = 'outflow'
    )
    BEGIN
        INSERT INTO "outflow" (geom_type, bc_fid) SELECT 'line', NEW."fid";
    END;

-- line boundary updated - type: inflow
INSERT INTO trigger_control (name, enabled) VALUES ('update_inflow_on_bc_lines_update', 1);
CREATE TRIGGER "update_inflow_on_bc_lines_update"
    AFTER UPDATE ON "user_bc_lines"
    WHEN (
        SELECT enabled FROM trigger_control WHERE name = 'update_inflow_on_bc_lines_update' AND
        NEW."type" = 'inflow'
    )
    BEGIN
        -- delete this bc from other tables
        DELETE FROM outflow WHERE bc_fid = NEW.fid AND geom_type = 'line';
        -- try to insert to the inflow table, ignore on fail (there is a unique constraint on inflow.bc_fid)
        INSERT OR IGNORE INTO inflow (geom_type, bc_fid) SELECT 'line', NEW."fid";
        -- update existing (includes geometry changes)
        UPDATE inflow SET geom_type = 'line' WHERE bc_fid = NEW.fid;
    END;

-- line boundary updated - type: outflow
INSERT INTO trigger_control (name, enabled) VALUES ('update_outflow_on_bc_lines_update', 1);
CREATE TRIGGER "update_outflow_on_bc_lines_update"
    AFTER UPDATE ON "user_bc_lines"
    WHEN (
        SELECT enabled FROM trigger_control WHERE name = 'update_outflow_on_bc_lines_update' AND
        NEW."type" = 'outflow'
    )
    BEGIN
        -- delete this bc from other tables
        DELETE FROM inflow WHERE bc_fid = NEW.fid AND geom_type = 'line';
        -- try to insert to the inflow table, ignore on fail
        INSERT OR IGNORE INTO outflow (geom_type, bc_fid) SELECT 'line', NEW."fid";
        -- update existing (includes geometry changes)
        UPDATE outflow SET geom_type = 'line' WHERE bc_fid = NEW.fid;
    END;

-- inflow line boundary deleted
INSERT INTO trigger_control (name, enabled) VALUES ('update_inflow_on_bc_lines_delete', 1);
CREATE TRIGGER "update_inflow_on_bc_lines_delete"
    AFTER DELETE ON "user_bc_lines"
    WHEN (
        SELECT enabled FROM trigger_control WHERE name = 'update_inflow_on_bc_lines_delete'
    )
    BEGIN
        DELETE FROM "inflow" WHERE bc_fid = OLD."fid" AND geom_type = 'line';
    END;

-- outflow line boundary deleted
INSERT INTO trigger_control (name, enabled) VALUES ('update_outflow_on_bc_lines_delete', 1);
CREATE TRIGGER "update_outflow_on_bc_lines_delete"
    AFTER DELETE ON "user_bc_lines"
    WHEN (
        SELECT enabled FROM trigger_control WHERE name = 'update_outflow_on_bc_lines_delete'
    )
    BEGIN
        DELETE FROM "outflow" WHERE bc_fid = OLD."fid" AND geom_type = 'line';
    END;

-- END user_bc_lines TRIGGERS

CREATE TABLE "user_bc_polygons" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "type" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('user_bc_polygons', 'features', 4326);
SELECT gpkgAddGeometryColumn('user_bc_polygons', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('user_bc_polygons', 'geom');
-- SELECT gpkgAddSpatialIndex('user_bc_polygons', 'geom');

-- START user_bc_polygons TRIGGERS

-- trigger for a new POLYGON INFLOW boundary
INSERT INTO trigger_control (name, enabled) VALUES ('update_inflow_on_bc_polygons_insert', 1); -- enabled by default
CREATE TRIGGER "update_inflow_on_bc_polygons_insert"
    AFTER INSERT ON "user_bc_polygons"
    WHEN (
        SELECT enabled FROM trigger_control WHERE name = 'update_inflow_on_bc_polygons_insert' AND
        NEW."geom" NOT NULL AND NEW."type" = 'inflow'
    )
    BEGIN
        INSERT INTO "inflow" (geom_type, bc_fid) SELECT 'polygon', NEW."fid";
    END;

-- trigger for a new POLYGON OUTFLOW boundary
INSERT INTO trigger_control (name, enabled) VALUES ('update_outflow_on_bc_polygons_insert', 1);
CREATE TRIGGER "update_outflow_on_bc_polygons_insert"
    AFTER INSERT ON "user_bc_polygons"
    WHEN (
        SELECT enabled FROM trigger_control WHERE name = 'update_outflow_on_bc_polygons_insert' AND
        NEW."geom" NOT NULL AND NEW."type" = 'outflow'
    )
    BEGIN
        INSERT INTO "outflow" (geom_type, bc_fid) SELECT 'polygon', NEW."fid";
    END;

-- polygon boundary updated - type: inflow
INSERT INTO trigger_control (name, enabled) VALUES ('update_inflow_on_bc_polygons_update', 1);
CREATE TRIGGER "update_inflow_on_bc_polygons_update"
    AFTER UPDATE ON "user_bc_polygons"
    WHEN (
        SELECT enabled FROM trigger_control WHERE name = 'update_inflow_on_bc_polygons_update' AND
        NEW."type" = 'inflow'
    )
    BEGIN
        -- delete this bc from other tables
        DELETE FROM outflow WHERE bc_fid = NEW.fid AND geom_type = 'polygon';
        -- try to insert to the inflow table, ignore on fail (there is a unique constraint on inflow.bc_fid)
        INSERT OR IGNORE INTO inflow (geom_type, bc_fid) SELECT 'polygon', NEW."fid";
        -- update existing (includes geometry changes)
        UPDATE inflow SET geom_type = 'polygon' WHERE bc_fid = NEW.fid;
    END;

-- line boundary updated - type: outflow
INSERT INTO trigger_control (name, enabled) VALUES ('update_outflow_on_bc_polygons_update', 1);
CREATE TRIGGER "update_outflow_on_bc_polygons_update"
    AFTER UPDATE ON "user_bc_polygons"
    WHEN (
        SELECT enabled FROM trigger_control WHERE name = 'update_outflow_on_bc_polygons_update' AND
        NEW."type" = 'outflow'
    )
    BEGIN
        -- delete this bc from other tables
        DELETE FROM inflow WHERE bc_fid = NEW.fid AND geom_type = 'polygon';
        -- try to insert to the inflow table, ignore on fail
        INSERT OR IGNORE INTO outflow (geom_type, bc_fid) SELECT 'polygon', NEW."fid";
        -- update existing (includes geometry changes)
        UPDATE outflow SET geom_type = 'polygon' WHERE bc_fid = NEW.fid;
    END;

-- inflow polygon boundary deleted
INSERT INTO trigger_control (name, enabled) VALUES ('update_inflow_on_bc_polygons_delete', 1);
CREATE TRIGGER "update_inflow_on_bc_polygons_delete"
    AFTER DELETE ON "user_bc_polygons"
    WHEN (
        SELECT enabled FROM trigger_control WHERE name = 'update_inflow_on_bc_polygons_delete'
    )
    BEGIN
        DELETE FROM "inflow" WHERE bc_fid = OLD."fid" AND geom_type = 'polygon';
    END;

-- outflow line boundary deleted
INSERT INTO trigger_control (name, enabled) VALUES ('update_outflow_on_bc_polygons_delete', 1);
CREATE TRIGGER "update_outflow_on_bc_polygons_delete"
    AFTER DELETE ON "user_bc_polygons"
    WHEN (
        SELECT enabled FROM trigger_control WHERE name = 'update_outflow_on_bc_polygons_delete'
    )
    BEGIN
        DELETE FROM "outflow" WHERE bc_fid = OLD."fid" AND geom_type = 'polygon';
    END;

-- END user_bc_polygons TRIGGERS

CREATE VIEW all_user_bc AS
SELECT type, 'point' as "geom_type", fid AS bc_fid, geom FROM user_bc_points
UNION ALL
SELECT type, 'line' as "geom_type", fid AS bc_fid, geom FROM user_bc_lines
UNION ALL
SELECT type, 'polygon' as "geom_type", fid AS bc_fid, geom FROM user_bc_polygons;

CREATE VIEW in_and_outflows AS
SELECT 'inflow' as type, fid, geom_type, bc_fid FROM inflow
UNION ALL
SELECT 'outflow' as type, fid, geom_type, bc_fid FROM outflow;

--
--CREATE VIEW all_user_inflows AS
--SELECT 'point' as "geom_type", fid, geom FROM user_bc_points WHERE type = 'inflow'
--UNION ALL
--SELECT 'line' as "geom_type", fid, geom FROM user_bc_lines WHERE type = 'inflow'
--UNION ALL
--SELECT 'polygon' as "geom_type", fid, geom FROM user_bc_polygons WHERE type = 'inflow';
--
--CREATE VIEW all_user_outflows AS
--SELECT 'point' as "geom_type", fid, geom FROM user_bc_points WHERE type = 'outflow'
--UNION ALL
--SELECT 'line' as "geom_type", fid, geom FROM user_bc_lines WHERE type = 'outflow'
--UNION ALL
--SELECT 'polygon' as "geom_type", fid, geom FROM user_bc_polygons WHERE type = 'outflow';

CREATE TABLE "all_schem_bc" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "type" TEXT,
    "tab_bc_fid" INTEGER,
    "grid_fid" INTEGER
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('all_schem_bc', 'features', 4326);
SELECT gpkgAddGeometryColumn('all_schem_bc', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('all_schem_bc', 'geom');

--INSERT INTO trigger_control (name, enabled) VALUES ('update_inflow_on_bc_polygons_insert', 1); -- enabled by default
CREATE TRIGGER "update_all_schem_bc_on_inflow_cell_insert"
    AFTER INSERT ON "inflow_cells"
    BEGIN
        INSERT INTO "all_schem_bc" (type, tab_bc_fid, grid_fid, geom)
        SELECT 'inflow', NEW."fid", NEW."grid_fid", (SELECT geom from grid WHERE fid = NEW.grid_fid);
    END;

CREATE TRIGGER "update_all_schem_bc_on_outflow_cell_insert"
    AFTER INSERT ON "outflow_cells"
    BEGIN
        INSERT INTO "all_schem_bc" (type, tab_bc_fid, grid_fid, geom)
        SELECT 'outflow', NEW."fid", NEW."grid_fid", (SELECT geom from grid WHERE fid = NEW.grid_fid);
    END;

CREATE TRIGGER "update_all_schem_bc_on_inflow_cell_delete"
    AFTER DELETE ON "inflow_cells"
    BEGIN
        DELETE FROM all_schem_bc WHERE type = 'inflow' AND grid_fid = OLD.grid_fid;
    END;

CREATE TRIGGER "update_all_schem_bc_on_outflow_cell_delete"
    AFTER DELETE ON "outflow_cells"
    BEGIN
        DELETE FROM all_schem_bc WHERE type = 'outflow' AND grid_fid = OLD.grid_fid;
    END;

CREATE TABLE "user_reservoirs" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "name" TEXT,
    "wsel" REAL,
    "notes" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('user_reservoirs', 'features', 4326);
SELECT gpkgAddGeometryColumn('user_reservoirs', 'geom', 'POINT', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('user_reservoirs', 'geom');

CREATE VIEW struct_types AS
SELECT DISTINCT 'C' as type, struct_fid FROM rat_curves
UNION ALL
SELECT DISTINCT 'R' as type, struct_fid FROM repl_rat_curves
UNION ALL
SELECT DISTINCT 'T' as type, struct_fid FROM rat_table
UNION ALL
SELECT DISTINCT 'F' as type, struct_fid FROM culvert_equations
UNION ALL
SELECT DISTINCT 'D' as type, struct_fid FROM storm_drains;
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('struct_data_tables', 'aspatial');