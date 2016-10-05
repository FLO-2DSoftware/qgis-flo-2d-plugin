
# GeoPackage Structure Documentation

## List of supported DAT files

The following files are supported by the import/export tool:

- [ARF.DAT](arf.md)
- [BATCHCYCLE.DAT](batchcycle.md)
- [BREACH.DAT](breach.md)
-  **[CADPTS.DAT](cadpts.md)** *
- [CADPTS_DSx.DAT x = 1,9](cadpts.md)
- [CHAN.DAT](chan.md)
- [CHANBANK.DAT](chanbank.md)
- **[CONT.DAT](cont.md)**
- [EVAPOR.DAT](evapor.md)
- [FPFROUDE.DAT](fpfroude.md)
- **[FPLAIN.DAT](fplain.md)** *
- [FPXSEC.DAT](fpxsec.md)
- [HYSTRUC.DAT](hydrostruc.md)
- [INFIL.DAT](infil.md)
- **[INFLOW.DAT](inflow.md)**
- [INFLOWx_DS.DAT x = 1,9](inflow.md)
- [LEVEE.DAT](levee.md)
- **[MANNINGS_N.DAT](topo.md)** *
- [MULT.DAT](mult.md)
- [OUTFLOW.DAT](outflow.md)
- [RAIN.DAT](rain.md)
- [RAINCELL.DAT](rain.md)
- [SED.DAT](sed.md)
- [STREET.DAT](street.md)
- [SWMMFLO.DAT](swmm.md)
- [SWMMFLORT.DAT](swmm.md#swmmflortdat)
- [SWMMOUTF.DAT](swmm.md#swmmoutfdat)
- **[TOLER.DAT](toler.md)**
- [TOLSPATIAL.DAT](toler.md)
- **[TOPO.DAT](topo.md)** *
- [WSTIME.DAT](wstime.md)
- [XSEC.DAT](chan.md#xsecdat)


Files required for FLO-2D solver are given in bold.

\* If FPLAIN and CADPTS exist TOPO and MANNINGS_N are created automatically. Conversely, when TOPO and MANNINGS_N exist FPLAIN and CADPTS are created by GDS.


## Creating Database Schema Graphs

TODO
