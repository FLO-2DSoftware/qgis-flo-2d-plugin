-- Create GeoPackage triggers

-- Inflow - INFLOW.DAT

CREATE TRIGGER IF NOT EXISTS "find_inflow_cells_insert"
    AFTER INSERT ON "inflow"
    WHEN (new."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "inflow_cells" WHERE inflow_fid = NEW."fid";
        INSERT INTO "inflow_cells" (inflow_fid, grid_fid) SELECT NEW.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_inflow_cells_update"
    AFTER UPDATE ON "inflow"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "inflow_cells" WHERE inflow_fid = OLD."fid";
        INSERT INTO "inflow_cells" (inflow_fid, grid_fid) SELECT OLD.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_inflow_cells_delete"
    AFTER DELETE ON "inflow"
--     WHEN (OLD."geom" NOT NULL AND NOT ST_IsEmpty(OLD."geom"))
    BEGIN
        DELETE FROM "inflow_cells" WHERE inflow_fid = OLD."fid";
    END;


-- Outflows

CREATE TRIGGER IF NOT EXISTS "find_outflow_cells_insert"
    AFTER INSERT ON "outflow"
    WHEN (new."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom") AND NEW."ident" = 'N')
    BEGIN
        DELETE FROM "outflow_cells" WHERE outflow_fid = NEW."fid";
        INSERT INTO "outflow_cells" (outflow_fid, grid_fid, area_factor)
        SELECT NEW.fid, g.fid, ST_Area(ST_Intersection(CastAutomagic(g.geom), CastAutomagic(NEW.geom)))/ST_Area(NEW.geom) FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_outflow_chan_elems_insert"
    AFTER INSERT ON "outflow"
    WHEN (new."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom") AND NEW."ident" = 'K')
    BEGIN
        DELETE FROM "outflow_chan_elems" WHERE outflow_fid = NEW."fid";
        INSERT INTO "outflow_chan_elems" (outflow_fid, elem_fid) SELECT NEW.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_outflow_cells_update"
    AFTER UPDATE ON "outflow"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom") AND NOT NULL)
    BEGIN
        DELETE FROM "outflow_cells" WHERE outflow_fid = OLD."fid" AND NEW."ident" = 'N';
        INSERT INTO "outflow_cells" (outflow_fid, grid_fid) SELECT OLD.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom)) AND NEW."ident" = 'N';
    END;

CREATE TRIGGER IF NOT EXISTS "find_outflow_chan_elems_update"
    AFTER UPDATE ON "outflow"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom") AND NOT NULL)
    BEGIN
        DELETE FROM "outflow_chan_elems" WHERE outflow_fid = OLD."fid" AND NEW."ident" = 'K';
        INSERT INTO "outflow_chan_elems" (outflow_fid, elem_fid) SELECT OLD.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom)) AND NEW."ident" = 'K';
    END;

CREATE TRIGGER IF NOT EXISTS "find_outflow_cells_delete"
    AFTER DELETE ON "outflow"
    WHEN (OLD."ident" = 'N')
    BEGIN
        DELETE FROM "outflow_cells" WHERE outflow_fid = OLD."fid";
    END;

CREATE TRIGGER IF NOT EXISTS "find_outflow_chan_elems_delete"
    AFTER DELETE ON "outflow"
    WHEN (OLD."ident" = 'K')
    BEGIN
        DELETE FROM "outflow_chan_elems" WHERE outflow_fid = OLD."fid";
    END;


-- RAIN.DAT

CREATE TRIGGER IF NOT EXISTS "find_rain_arf_cells_insert"
    AFTER INSERT ON "rain_arf_areas"
    WHEN (new."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "rain_arf_cells" WHERE rain_arf_area_fid = NEW."fid";
        INSERT INTO "rain_arf_cells" (rain_arf_area_fid, grid_fid, arf)
        SELECT NEW.fid, g.fid, NEW.arf FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_rain_arf_cells_update"
    AFTER UPDATE ON "rain_arf_areas"
    WHEN (new."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "rain_arf_cells" WHERE rain_arf_area_fid = NEW."fid";
        INSERT INTO "rain_arf_cells" (rain_arf_area_fid, grid_fid, arf)
        SELECT NEW.fid, g.fid, NEW.arf FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_rain_arf_cells_delete"
    AFTER DELETE ON "rain_arf_areas"
    BEGIN
        DELETE FROM "rain_arf_cells" WHERE rain_arf_area_fid = OLD."fid";
    END;


-- CHAN.DAT

CREATE TRIGGER IF NOT EXISTS "find_user_chan_n_delete"
    AFTER DELETE ON "user_xsections"
    BEGIN
        DELETE FROM "user_chan_n" WHERE user_xs_fid = OLD."fid";
    END;

-- TODO: create triggers for geometry INSERT and UPDATE
-- use notes column to flag features created by user!

-- -- create geometry when rightbank and leftbank are given
-- CREATE TRIGGER IF NOT EXISTS "chan_n_geom_insert"
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
-- CREATE TRIGGER IF NOT EXISTS "chan_n_banks_update_geom_changed"
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
-- CREATE TRIGGER IF NOT EXISTS "chan_n_geom_update_banks_changed"
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


-- RIGHTBANKS

-- CREATE TRIGGER IF NOT EXISTS "find_rbank_n_insert"
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
-- CREATE TRIGGER IF NOT EXISTS "find_rbank_n_update"
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
-- CREATE TRIGGER IF NOT EXISTS "find_rbank_n_delete"
--     AFTER DELETE ON "chan_n"
--     BEGIN
--         DELETE FROM "rightbanks" WHERE seg_fid = OLD."seg_fid";
--     END;

-- automatically create/modify geometry of confluences on iconflo1/2 insert/update

CREATE TRIGGER IF NOT EXISTS "confluence_geom_insert"
    AFTER INSERT ON "chan_confluences"
    WHEN (NEW."chan_elem_fid" NOT NULL)
    BEGIN
        UPDATE "chan_confluences"
            SET geom = (SELECT AsGPB(ST_Centroid(CastAutomagic(g.geom))) FROM grid AS g WHERE g.fid = chan_elem_fid);
        -- TODO: set also seg_fid
    END;

CREATE TRIGGER IF NOT EXISTS "confluence_geom_update"
    AFTER UPDATE ON "chan_confluences"
    WHEN (NEW."chan_elem_fid" NOT NULL)
    BEGIN
        UPDATE "chan_confluences"
            SET geom = (SELECT AsGPB(ST_Centroid(CastAutomagic(g.geom))) FROM grid AS g WHERE g.fid = chan_elem_fid);
        -- TODO: set also seg_fid
    END;

CREATE TRIGGER IF NOT EXISTS "find_noexchange_cells_insert"
    AFTER INSERT ON "user_noexchange_chan_areas"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "noexchange_chan_cells" WHERE noex_fid = NEW."fid";
        INSERT INTO "noexchange_chan_cells" (noex_fid, grid_fid)
        SELECT NEW.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_noexchange_cells_update"
    AFTER UPDATE ON "user_noexchange_chan_areas"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "noexchange_chan_cells" WHERE noex_fid = NEW."fid";
        INSERT INTO "noexchange_chan_cells" (noex_fid, grid_fid)
        SELECT NEW.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_noexchange_cells_delete"
    AFTER DELETE ON "user_noexchange_chan_areas"
    BEGIN
        DELETE FROM "noexchange_chan_cells" WHERE noex_fid = OLD."fid";
    END;


-- INFIL.DAT

    -- Green Ampt

CREATE TRIGGER IF NOT EXISTS "find_infil_cells_green_insert"
    AFTER INSERT ON "infil_areas_green"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "infil_cells_green" WHERE infil_area_fid = NEW."fid";
        INSERT INTO "infil_cells_green" (infil_area_fid, grid_fid)
            SELECT NEW.fid, g.fid FROM grid as g
            WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_infil_cells_green_update"
    AFTER UPDATE ON "infil_areas_green"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "infil_cells_green" WHERE infil_area_fid = NEW."fid";
        INSERT INTO "infil_cells_green" (infil_area_fid, grid_fid)
        SELECT NEW.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_infil_cells_green_delete"
    AFTER DELETE ON "infil_areas_green"
    BEGIN
        DELETE FROM "infil_cells_green" WHERE infil_area_fid = OLD."fid";
    END;

    -- SCS

CREATE TRIGGER IF NOT EXISTS "find_infil_cells_scs_insert"
    AFTER INSERT ON "infil_areas_scs"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "infil_cells_scs" WHERE infil_area_fid = NEW."fid";
        INSERT INTO "infil_cells_scs" (infil_area_fid, grid_fid)
            SELECT NEW.fid, g.fid FROM grid as g
            WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_infil_cells_scs_update"
    AFTER UPDATE ON "infil_areas_scs"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "infil_cells_scs" WHERE infil_area_fid = NEW."fid";
        INSERT INTO "infil_cells_scs" (infil_area_fid, grid_fid)
        SELECT NEW.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_infil_cells_scs_delete"
    AFTER DELETE ON "infil_areas_scs"
    BEGIN
        DELETE FROM "infil_cells_scs" WHERE infil_area_fid = OLD."fid";
    END;

    -- HORTON

CREATE TABLE "infil_cells_horton" (
    "fid" INTEGER NOT NULL PRIMARY KEY,
    "grid_fid" INTEGER, -- grid element number from grid table
    "infil_area_fid" INTEGER -- polygon fid from infil_areas_horton table
);
INSERT INTO gpkg_contents (table_name, data_type) VALUES ('infil_cells_horton', 'aspatial');

CREATE TRIGGER IF NOT EXISTS "find_infil_cells_horton_insert"
    AFTER INSERT ON "infil_areas_horton"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "infil_cells_horton" WHERE infil_area_fid = NEW."fid";
        INSERT INTO "infil_cells_horton" (infil_area_fid, grid_fid)
            SELECT NEW.fid, g.fid FROM grid as g
            WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_infil_cells_horton_update"
    AFTER UPDATE ON "infil_areas_horton"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "infil_cells_horton" WHERE infil_area_fid = NEW."fid";
        INSERT INTO "infil_cells_horton" (infil_area_fid, grid_fid)
        SELECT NEW.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_infil_cells_horton_delete"
    AFTER DELETE ON "infil_areas_horton"
    BEGIN
        DELETE FROM "infil_cells_horton" WHERE infil_area_fid = OLD."fid";
    END;

    -- CHANNELS

CREATE TRIGGER IF NOT EXISTS "find_infil_chan_elems_insert"
    AFTER INSERT ON "infil_areas_chan"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "infil_chan_elems" WHERE infil_area_fid = NEW."fid";
        INSERT INTO "infil_chan_elems" (infil_area_fid, grid_fid)
            SELECT NEW.fid, g.fid FROM grid as g
            WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_infil_chan_elems_update"
    AFTER UPDATE ON "infil_areas_chan"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "infil_chan_elems" WHERE infil_area_fid = NEW."fid";
        INSERT INTO "infil_chan_elems" (infil_area_fid, grid_fid)
        SELECT NEW.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_infil_chan_elems_delete"
    AFTER DELETE ON "infil_areas_chan"
    BEGIN
        DELETE FROM "infil_chan_elems" WHERE infil_area_fid = OLD."fid";
    END;


-- HYSTRUC.DAT

-- TODO: triggers for creating the struct geom based on in- and outflonod



-- STREET.DAT

-- TODO: geometry triggers for streets


-- ARF.DAT

CREATE TRIGGER IF NOT EXISTS "find_cells_arf_tot_insert"
    AFTER INSERT ON "blocked_areas_tot"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "blocked_cells_tot" WHERE area_fid = NEW."fid";
        INSERT INTO "blocked_cells_tot" (area_fid, grid_fid)
            SELECT NEW.fid, g.fid FROM grid as g
            WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_cells_arf_tot_update"
    AFTER UPDATE ON "blocked_areas_tot"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "blocked_cells_tot" WHERE area_fid = NEW."fid";
        INSERT INTO "blocked_cells_tot" (area_fid, grid_fid)
        SELECT NEW.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_cells_arf_tot_delete"
    AFTER DELETE ON "blocked_areas_tot"
    BEGIN
        DELETE FROM "blocked_cells_tot" WHERE area_fid = OLD."fid";
    END;


CREATE TRIGGER IF NOT EXISTS "find_cells_arf_insert"
    AFTER INSERT ON "user_blocked_areas"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "blocked_cells" WHERE area_fid = NEW."fid";
        INSERT INTO "blocked_cells" (area_fid, grid_fid)
            SELECT NEW.fid, g.fid FROM grid as g
            WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_cells_arf_update"
    AFTER UPDATE ON "user_blocked_areas"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "blocked_cells" WHERE area_fid = NEW."fid";
        INSERT INTO "blocked_cells" (area_fid, grid_fid)
        SELECT NEW.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_cells_arf_delete"
    AFTER DELETE ON "user_blocked_areas"
    BEGIN
        DELETE FROM "blocked_cells" WHERE area_fid = OLD."fid";
    END;


-- MULT.DAT

CREATE TRIGGER IF NOT EXISTS "find_cells_mult_insert"
    AFTER INSERT ON "mult_areas"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "mult_cells" WHERE area_fid = NEW."fid";
        INSERT INTO "mult_cells" (area_fid, grid_fid)
            SELECT NEW.fid, g.fid FROM grid as g
            WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_cells_mult_update"
    AFTER UPDATE ON "mult_areas"
    WHEN (NEW."geom" NOT NULL AND NOT ST_IsEmpty(NEW."geom"))
    BEGIN
        DELETE FROM "mult_cells" WHERE area_fid = NEW."fid";
        INSERT INTO "mult_cells" (area_fid, grid_fid)
        SELECT NEW.fid, g.fid FROM grid as g
        WHERE ST_Intersects(CastAutomagic(g.geom), CastAutomagic(NEW.geom));
    END;

CREATE TRIGGER IF NOT EXISTS "find_cells_mult_delete"
    AFTER DELETE ON "mult_areas"
    BEGIN
        DELETE FROM "mult_cells" WHERE area_fid = OLD."fid";
    END;


-- LEVEE.DAT




-- FPXSEC.DAT



-- SWMMFLO.DAT



-- SWMMOUTF.DAT



-- TOLSPATIAL.DAT



-- WSURF.DAT



-- WSTIME.DAT

