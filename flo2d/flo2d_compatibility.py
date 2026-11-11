

FLO2009 = "FLO2009"
FLOPRO = "FLOPRO"

SUPPORTED_ENGINES = (FLO2009, FLOPRO)

class EngineCompatibility:
    """
    Central compatibility layer between FLO-2D engines.
    This class never modifies the geopackage. It only described how
    the selected engine should interpret and export the project
    """
    def __init__(self, flo2d):
        self.flo2d = flo2d

    @property
    def engine(self):
        if not self.flo2d.gutils:
            return FLOPRO
        engine = self.flo2d.gutils.get_cont_par("ENGINE")
        if engine in SUPPORTED_ENGINES:
            return engine
        return FLOPRO

    def set_engine(self, engine):
        if engine not in SUPPORTED_ENGINES:
            raise ValueError(f"Unsupported engine: {engine}")
        if self.flo2d.gutils:
            self.flo2d.gutils.set_cont_par("ENGINE", engine)

    @property
    def is_flopro(self):
        return self.engine == FLOPRO

    @property
    def is_flo2009(self):
        return self.engine == FLO2009

    CONT_LAYOUT = {
        FLOPRO: (
            ("SIMUL", "TOUT", "LGPLOT", "METRIC", "IBACKUP"),
            ("ICHANNEL", "MSTREET", "LEVEE", "IWRFS", "IMULTC"),
            ("IRAIN", "INFIL", "IEVAP", "MUD", "ISED", "IMODFLOW", "SWMM"),
            ("IHYDRSTRUCT", "IFLOODWAY", "IDEBRV"),
            ("AMANN", "DEPTHDUR", "XCONC", "XARF", "FROUDL", "SHALLOWN", "ENCROACH"),
            ("NOPRTFP", "DEPRESSDEPTH"),
            ("NOPRTC",),
            ("ITIMTEP", "TIMTEP", "STARTTIMTEP", "ENDTIMTEP"),
            ("GRAPTIM",),
        ),

        FLO2009: (
            ("SIMUL", "TOUT", "LGPLOT", "METRIC", "IBACKUP"),
            ("ICHANNEL", "MSTREET", "LEVEE", "IWRFS", "IMULTC"),
            ("IRAIN", "INFIL", "IEVAP", "MUD", "ISED", "IMODFLOW"),
            ("IHYDRSTRUCT", "IFLOODWAY", "IDEBRV"),
            ("AMANN", "DEPTHDUR", "XCONC", "XARF", "FROUDL", "SHALLOWN", "ENCROACH"),
            ("NOPRTFP", "SUPER"),
            ("NOPRTC",),
            ("ITIMTEP", "TIMTEP"),
            ("GRAPTIM",),
        ),
    }

    FEATURE_SUPPORT = {
        "SWMM":{
            FLOPRO: True,
            FLO2009: False,
        },
        "STARTTIMTEP":{
            FLOPRO: True,
            FLO2009: False,
        },
        "ENDTIMTEP": {
            FLOPRO: True,
            FLO2009: False,
        },
        "DEPRESSDEPTH": {
            FLOPRO: True,
            FLO2009: False,
        },
        "SUPER": {
            FLOPRO: False,
            FLO2009: True,
        },
        "EXPORT_MANNINGS_N_TOPO": {
            FLOPRO: True,
            FLO2009: False,
        },
    }

    def supports(self, feature):
        return self.FEATURE_SUPPORT.get(feature, {}).get(self.engine, True)

    @property
    def cont_layout(self):
        return self.CONT_LAYOUT[self.engine]
