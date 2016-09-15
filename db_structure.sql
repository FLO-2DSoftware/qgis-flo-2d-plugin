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


-- FLO-2D tables definitions

-- The main table with model control parameters (from CONT.DAT and others)

CREATE TABLE cont (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL,
    "value" TEXT,
    "note" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('cont', 'aspatial');


-- Grid table - data from FPLAIN.DAT, CADPTS.DAT, TOPO.DAT, MANNINGS_N.DAT

CREATE TABLE "grid" ( `fid` INTEGER PRIMARY KEY AUTOINCREMENT,
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
    "ident" TEXT NOT NULL,
    "inoutfc" INTEGER NOT NULL,
    "note" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('inflow', 'features', 4326);
SELECT gpkgAddGeometryColumn('inflow', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('inflow', 'geom');
SELECT gpkgAddSpatialIndex('inflow', 'geom');

CREATE TABLE "inflow_cells" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "inflow_fid" INTEGER NOT NULL,
    "grid_fid" INTEGER NOT NULL,
    "area_factor" REAL
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('inflow_cells', 'aspatial');

CREATE TRIGGER "find_inflow_cells_insert"
    AFTER INSERT ON "inflow"
    WHEN (new."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "inflow_cells" WHERE inflow_fid = NEW."fid";
        INSERT INTO "inflow_cells" (inflow_fid, grid_fid) SELECT NEW.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER "find_inflow_cells_update"
    AFTER UPDATE ON "inflow"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "inflow_cells" WHERE inflow_fid = OLD."fid";
        INSERT INTO "inflow_cells" (inflow_fid, grid_fid) SELECT OLD.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER "find_inflow_cells_delete"
    AFTER DELETE ON "inflow"
--     WHEN (OLD."geom" NOT NULL AND NOT ST_IsEmpty(OLD."geom"))
    BEGIN
        DELETE FROM "inflow_cells" WHERE inflow_fid = OLD."fid";
    END;

-- Outflows

CREATE TABLE "outflow" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "name" TEXT,
    "ident" TEXT,
    "nostacfp" INTEGER,
    "time_series_fid" INTEGER,
    "qh_params_fid" INTEGER,
    "note" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('outflow', 'features', 4326);
SELECT gpkgAddGeometryColumn('outflow', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('outflow', 'geom');
SELECT gpkgAddSpatialIndex('outflow', 'geom');

CREATE TABLE "outflow_cells" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "outflow_fid" INTEGER NOT NULL,
    "grid_fid" INTEGER NOT NULL,
    "area_factor" REAL
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('outflow_cells', 'aspatial');

CREATE TABLE "outflow_chan_elems" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "outflow_fid" INTEGER NOT NULL,
    "elem_fid" INTEGER NOT NULL
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('outflow_chan_elems', 'aspatial');

CREATE TRIGGER "find_outflow_cells_insert"
    AFTER INSERT ON "outflow"
    WHEN (new."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom") AND NEW."ident" = 'N')
    BEGIN
        DELETE FROM "outflow_cells" WHERE outflow_fid = NEW."fid";
        INSERT INTO "outflow_cells" (outflow_fid, grid_fid, area_factor) 
        SELECT NEW.fid, g.fid, ST_Area(ST_Intersection(CastAutomagic(g.geom), CastAutomagic(NEW.geom)))/ST_Area(NEW.geom) FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER "find_outflow_chan_elems_insert"
    AFTER INSERT ON "outflow"
    WHEN (new."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom") AND NEW."ident" = 'K')
    BEGIN
        DELETE FROM "outflow_chan_elems" WHERE outflow_fid = NEW."fid";
        INSERT INTO "outflow_chan_elems" (outflow_fid, elem_fid) SELECT NEW.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER "find_outflow_cells_update"
    AFTER UPDATE ON "outflow"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom") AND NOT NULL)
    BEGIN
        DELETE FROM "outflow_cells" WHERE outflow_fid = OLD."fid" AND NEW."ident" = 'N';
        INSERT INTO "outflow_cells" (outflow_fid, grid_fid) SELECT OLD.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom)) AND NEW."ident" = 'N';
    END;

CREATE TRIGGER "find_outflow_chan_elems_update"
    AFTER UPDATE ON "outflow"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom") AND NOT NULL)
    BEGIN
        DELETE FROM "outflow_chan_elems" WHERE outflow_fid = OLD."fid" AND NEW."ident" = 'K';
        INSERT INTO "outflow_chan_elems" (outflow_fid, elem_fid) SELECT OLD.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom)) AND NEW."ident" = 'K';
    END;

CREATE TRIGGER "find_outflow_cells_delete"
    AFTER DELETE ON "outflow"
    WHEN (OLD."ident" = 'N')
    BEGIN
        DELETE FROM "outflow_cells" WHERE outflow_fid = OLD."fid";
    END;

CREATE TRIGGER "find_outflow_chan_elems_delete"
    AFTER DELETE ON "outflow"
    WHEN (OLD."ident" = 'K')
    BEGIN
        DELETE FROM "outflow_chan_elems" WHERE outflow_fid = OLD."fid";
    END;

CREATE TABLE "qh_params" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "max" REAL,
    "coef" REAL,
    "exponent" REAL
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('qh_params', 'aspatial');

CREATE TABLE "outflow_hydrographs" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "hydro_fid" TEXT NOT NULL,
    "grid_fid" INTEGER NOT NULL
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('outflow_hydrographs', 'aspatial');

CREATE TABLE "reservoirs" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "name" TEXT,
    "grid_fid" INTEGER,
    "wsel" REAL,
    "note" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('reservoirs', 'features', 4326);
SELECT gpkgAddGeometryColumn('reservoirs', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('reservoirs', 'geom');
SELECT gpkgAddSpatialIndex('reservoirs', 'geom');

CREATE TABLE "time_series" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "name" TEXT,
    "type" TEXT,
    "hourdaily" INTEGER
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('time_series', 'aspatial');

CREATE TABLE "time_series_data" (
    "fid" INTEGER PRIMARY KEY NOT NULL,
    "series_fid" INTEGER NOT NULL,
    "time" REAL NOT NULL,
    "value" REAL NOT NULL,
    "value2" REAL,
    "value3" REAL
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('time_series_data', 'aspatial');


-- RAIN.DAT

CREATE TABLE "rain" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "name" TEXT, -- name of rain
    "irainreal" INTEGER, -- IRAINREAL switch for real-time rainfall (NEXRAD)
    "ireainbuilding" INTEGER, -- IRAINBUILDING, switch, if 1 rainfall on ARF portion of grid will be contributed to surface runoff
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
SELECT gpkgAddSpatialIndex('rain_arf_areas', 'geom');

CREATE TABLE "rain_arf_cells" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "rain_arf_area_fid" INTEGER, -- fid of area with ARF defined
    "grid_fid" INTEGER, -- IRGRID(I), nr of grid element
    "arf" REAL -- RAINARF(I), ARF value for a grid elemen
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('rain_arf_cells', 'aspatial');

CREATE TRIGGER "find_rain_arf_cells_insert"
    AFTER INSERT ON "rain_arf_areas"
    WHEN (new."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "rain_arf_cells" WHERE rain_arf_area_fid = NEW."fid";
        INSERT INTO "rain_arf_cells" (rain_arf_area_fid, grid_fid, arf) 
        SELECT NEW.fid, g.fid, NEW.arf FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER "find_rain_arf_cells_update"
    AFTER UPDATE ON "rain_arf_areas"
    WHEN (new."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "rain_arf_cells" WHERE rain_arf_area_fid = NEW."fid";
        INSERT INTO "rain_arf_cells" (rain_arf_area_fid, grid_fid, arf) 
        SELECT NEW.fid, g.fid, NEW.arf FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER "find_rain_arf_cells_delete"
    AFTER DELETE ON "rain_arf_areas"
    BEGIN
        DELETE FROM "rain_arf_cells" WHERE rain_arf_area_fid = OLD."fid";
    END;


-- CHAN.DAT

CREATE TABLE "chan" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "name" TEXT, -- name of segment (optional)
    "depinitial" REAL, -- DEPINITIAL, initial channel flow depth
    "froudc" REAL, -- FROUDC, max Froude channel number
    "roughadj" REAL, -- ROUGHADJ, coefficient for depth adjustment
    "isedn" INTEGER, -- ISEDN, sediment transport equation or data
    "notes" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('chan', 'features', 4326);
SELECT gpkgAddGeometryColumn('chan', 'geom', 'POLYLINE', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('chan', 'geom');
SELECT gpkgAddSpatialIndex('chan', 'geom');

CREATE TABLE "chan_r" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "seg_fid" INTEGER, -- fid of cross-section's segment
    "nr_in_seg" INTEGER, -- cross-section number in segment
    "ichangrid" INTEGER, -- ICHANGRID, grid element number for left bank
    "bankell" REAL, -- BANKELL, left bank elevation
    "bankelr" REAL, -- BANKELR, right bank elevation
    "fcn" REAL, -- FCN, average Manning's n in the grid element
    "fcw" REAL, -- FCW, channel width
    "fcd" REAL, -- channel channel thalweg depth (deepest part measured from the lowest bank)
    "xlen" REAL, -- channel length contained within the grid element ICHANGRID
    "notes" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('chan_r', 'features', 4326);
SELECT gpkgAddGeometryColumn('chan_r', 'geom', 'POLYLINE', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('chan_r', 'geom');
SELECT gpkgAddSpatialIndex('chan_r', 'geom');

CREATE TABLE "chan_v" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "seg_fid" INTEGER, -- fid of cross-section's segment
    "nr_in_seg" INTEGER, -- cross-section number in segment
    "ichangrid" INTEGER, -- ICHANGRID, grid element number for left bank
    "bankell" REAL, -- BANKELL, left bank elevation
    "bankelr" REAL, -- BANKELR, right bank elevation
    "fcn" REAL, -- FCN, average Manning's n in the grid element
    "fcd" REAL, -- channel channel thalweg depth (deepest part measured from the lowest bank)
    "xlen" REAL, -- channel length contained within the grid element ICHANGRID
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
    "c22" REAL, -- C22,
    "notes" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('chan_v', 'features', 4326);
SELECT gpkgAddGeometryColumn('chan_v', 'geom', 'POLYLINE', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('chan_v', 'geom');
SELECT gpkgAddSpatialIndex('chan_v', 'geom');

CREATE TABLE "chan_t" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "seg_fid" INTEGER, -- fid of cross-section's segment
    "nr_in_seg" INTEGER, -- cross-section number in segment
    "ichangrid" INTEGER, -- ICHANGRID, grid element number for left bank
    "bankell" REAL, -- BANKELL, left bank elevation
    "bankelr" REAL, -- BANKELR, right bank elevation
    "fcn" REAL, -- FCN, average Manning's n in the grid element
    "fcw" REAL, -- FCW, channel width
    "fcd" REAL, -- channel channel thalweg depth (deepest part measured from the lowest bank)
    "xlen" REAL, -- channel length contained within the grid element ICHANGRID
    "zl" REAL, -- ZL left side slope
    "zr" REAL, --ZR right side slope
    "notes" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('chan_t', 'features', 4326);
SELECT gpkgAddGeometryColumn('chan_t', 'geom', 'POLYLINE', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('chan_t', 'geom');
SELECT gpkgAddSpatialIndex('chan_t', 'geom');

CREATE TABLE "chan_n" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "seg_fid" INTEGER, -- fid of cross-section's segment
    "nr_in_seg" INTEGER, -- cross-section number in segment
    "ichangrid" INTEGER, -- ICHANGRID, grid element number for left bank
    "fcn" REAL, -- FCN, average Manning's n in the grid element
    "xlen" REAL, -- channel length contained within the grid element ICHANGRID
    "nxecnum" INTEGER, -- NXSECNUM, surveyed cross section number assigned in XSEC.DAT
    "notes" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('chan_n', 'features', 4326);
SELECT gpkgAddGeometryColumn('chan_n', 'geom', 'POLYLINE', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('chan_n', 'geom');
SELECT gpkgAddSpatialIndex('chan_n', 'geom');

CREATE TABLE "chan_confluences" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "iconflo1" INTEGER, -- ICONFLO1, tributary channel element at confluence
    "iconflo2" INTEGER, -- ICONFLO2, main channel element at confluence
    "nr_in_seg" INTEGER, -- cross-section number in segment
    "ichangrid" INTEGER, -- ICHANGRID, grid element number for left bank
    "notes" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('chan_confluences', 'features', 4326);
SELECT gpkgAddGeometryColumn('chan_confluences', 'geom', 'MULTIPOINT', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('chan_confluences', 'geom');
SELECT gpkgAddSpatialIndex('chan_confluences', 'geom');

CREATE TABLE "noexchange_chan_areas" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "notes" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('noexchange_chan_areas', 'features', 4326);
SELECT gpkgAddGeometryColumn('noexchange_chan_areas', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('noexchange_chan_areas', 'geom');
SELECT gpkgAddSpatialIndex('noexchange_chan_areas', 'geom');

-- TODO: trigger

CREATE TABLE "noexchange_chan_elems" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "chan_elem_fid" INTEGER -- NOEXCHANGE, channel element number not exchanging flow. Filled in by a geoprocessing trigger
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('noexchange_chan_areas', 'aspatial');

CREATE TABLE "chan_wsel" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "seg_fid" INTEGER, -- found by geoprocessing trigger, channel segment for which the WSELs are specified
    "istart" INTEGER, -- ISTART, first channel element with a starting WSEL specified
    "wselstart" REAL, -- WSELSTART, first channel element starting WSEL
    "iend" INTEGER, -- IEND, last channel element with a starting WSEL specified
    "wselend" REAL -- WSELEND, last channel element starting WSEL
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('chan_wsel', 'aspatial');