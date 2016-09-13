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

CREATE TABLE cont (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL,
    "value" TEXT,
    "note" TEXT
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('cont', 'aspatial');

CREATE TABLE "grid" ( `fid` INTEGER PRIMARY KEY AUTOINCREMENT,
   "cell_north" INTEGER,
   "cell_east" INTEGER,
   "cell_south" INTEGER,
   "cell_west" INTEGER,
   "n_value" REAL,
   "elevation" REAL,
   "version" INTEGER
);
INSERT INTO gpkg_contents (table_name, data_type, srs_id) VALUES ('grid', 'features', 4326);
SELECT gpkgAddGeometryColumn('grid', 'geom', 'POLYGON', 0, 0, 0);
SELECT gpkgAddGeometryTriggers('grid', 'geom');
SELECT gpkgAddSpatialIndex('grid', 'geom');

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
    WHEN (OLD."geom" NOT NULL AND NOT ST_IsEmpty(OLD."geom"))
    BEGIN
        DELETE FROM "inflow_cells" WHERE inflow_fid = OLD."fid";
    END;


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
    "grid_fid" INTEGER NOT NULL
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
        INSERT INTO "outflow_cells" (outflow_fid, grid_fid) SELECT NEW.fid, g.fid FROM grid as g
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
    WHEN (OLD."geom" NOT NULL AND NOT ST_IsEmpty(OLD."geom") AND OLD."ident" = 'N')
    BEGIN
        DELETE FROM "outflow_cells" WHERE outflow_fid = OLD."fid";
    END;

CREATE TRIGGER "find_outflow_chan_elems_delete"
    AFTER DELETE ON "outflow"
    WHEN (OLD."geom" NOT NULL AND NOT ST_IsEmpty(OLD."geom") AND OLD."ident" = 'K')
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
    "grid_fid" INTEGER NOT NULL REFERENCES "grid"("fid")
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