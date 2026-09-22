import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AppBar, Box, CssBaseline, Dialog, DialogContent, DialogTitle,
  Divider, Drawer, IconButton, Link, Paper, Stack, ThemeProvider, Toolbar,
  Tooltip, Typography,
} from "@mui/material";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import GitHubIcon from "@mui/icons-material/GitHub";
import LightModeIcon from "@mui/icons-material/LightMode";
import { api } from "./api/client";
import {
  CLASSIFICATIONS, type ChangeDetail, type Changeset, type Classification,
  type FeatureHistory,
} from "./api/types";
import { buildTheme, CLASSIFICATION_COLORS, type BasemapChoice } from "./theme";
import { useColorMode } from "./hooks/useColorMode";
import { MapView } from "./components/MapView";
import { BasemapToggle } from "./components/BasemapToggle";
import { ChangesetTimeline } from "./components/ChangesetTimeline";
import { ClassificationFilter } from "./components/ClassificationFilter";
import { FeatureDetailPanel } from "./components/FeatureDetailPanel";

const DRAWER_WIDTH = 380;

export default function App() {
  const { mode, toggle } = useColorMode();
  const theme = useMemo(() => buildTheme(mode), [mode]);

  const [aboutOpen, setAboutOpen] = useState(false);
  const [basemap, setBasemap] = useState<BasemapChoice>("map");
  const [changesets, setChangesets] = useState<Changeset[]>([]);
  const [selectedChangesetId, setSelectedChangesetId] = useState<number | null>(null);
  const [visible, setVisible] = useState<Classification[]>([...CLASSIFICATIONS]);
  const [change, setChange] = useState<ChangeDetail | null>(null);
  const [history, setHistory] = useState<FeatureHistory | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listChangesets()
      .then((list) => {
        setChangesets(list);
        // Default to the longest computed span -- most data on screen at
        // first paint. Falls back to whatever the API returns first if a
        // "5 years" interval doesn't exist (e.g. a smaller/test dataset).
        const longest = list.find((cs) => cs.span_label === "5 years") ?? list[0];
        if (longest) setSelectedChangesetId(longest.id);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const selectedChangeset = useMemo(
    () => changesets.find((c) => c.id === selectedChangesetId) ?? null,
    [changesets, selectedChangesetId],
  );

  const handleSelectChange = useCallback(async (changeFeatureId: number) => {
    setLoadingDetail(true);
    setError(null);
    setHistory(null);
    try {
      const detail = await api.getChange(changeFeatureId);
      setChange(detail);
      // The timeline needs a single building; a multi-candidate ambiguous
      // group has no single subject, so it is shown without one.
      const osmId = detail.osm_ids_b[0] ?? detail.osm_ids_a[0];
      if (osmId && detail.osm_ids_a.length <= 1 && detail.osm_ids_b.length <= 1) {
        setHistory(await api.getHistory(osmId));
      }
    } catch (e) {
      setError((e as Error).message);
      setChange(null);
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  const toggleClassification = useCallback((c: Classification) => {
    setVisible((current) =>
      current.includes(c) ? current.filter((x) => x !== c) : [...current, c],
    );
  }, []);

  // Clear the selection when switching interval: a change record belongs to
  // one changeset, so keeping it visible would misattribute it.
  useEffect(() => {
    setChange(null);
    setHistory(null);
  }, [selectedChangesetId]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ display: "flex", height: "100vh" }}>
        <AppBar
          position="fixed"
          sx={{
            zIndex: (t) => t.zIndex.drawer + 1,
            backgroundImage: (t) =>
              `linear-gradient(90deg, ${t.palette.primary.dark}, ${t.palette.primary.main})`,
          }}
        >
          <Toolbar variant="dense">
            <Typography variant="h6" sx={{ flexGrow: 1 }}>
              GIS Vector Map Changes — Tel Aviv-Yafo
            </Typography>
            <Tooltip title="About">
              <IconButton
                color="inherit"
                onClick={() => setAboutOpen(true)}
                aria-label="About"
                sx={{ mr: 1 }}
              >
                <InfoOutlinedIcon />
              </IconButton>
            </Tooltip>
            <Tooltip title={mode === "dark" ? "Switch to light mode" : "Switch to dark mode"}>
              <IconButton color="inherit" onClick={toggle} aria-label="toggle color mode">
                {mode === "dark" ? <LightModeIcon /> : <DarkModeIcon />}
              </IconButton>
            </Tooltip>
          </Toolbar>
        </AppBar>

        <Dialog open={aboutOpen} onClose={() => setAboutOpen(false)} maxWidth="sm" fullWidth>
          <DialogTitle sx={{ fontWeight: 700 }}>GIS Vector Map Changes</DialogTitle>
          <DialogContent>
            <Typography variant="body2" sx={{ mb: 2 }}>
              A vector-GIS data platform for detecting and explaining changes
              between dated map snapshots of Tel Aviv-Yafo. It compares
              OpenStreetMap building footprints across time, classifies what
              changed -- added, removed, moved, resurveyed, or edited -- and
              renders the result as vector tiles served from PostGIS.
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Built with Apache Airflow, PostGIS, FastAPI, React, and MapLibre GL.
            </Typography>
            <Typography variant="body2">
              by Orel Kanditan ·{" "}
              <Link
                href="https://github.com/orelkan/gis-vector-map-changes"
                target="_blank"
                rel="noreferrer"
                sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}
              >
                <GitHubIcon fontSize="inherit" /> GitHub
              </Link>
            </Typography>
          </DialogContent>
        </Dialog>

        <Drawer
          variant="permanent"
          sx={{
            width: DRAWER_WIDTH,
            flexShrink: 0,
            "& .MuiDrawer-paper": { width: DRAWER_WIDTH, boxSizing: "border-box" },
          }}
        >
          <Toolbar variant="dense" />
          <Box sx={{ overflow: "auto", p: 2 }}>
            <Stack spacing={2}>
              <Paper variant="outlined" sx={{ p: 1.5, borderTopWidth: 3, borderTopColor: "primary.main" }}>
                <ChangesetTimeline
                  changesets={changesets}
                  selectedId={selectedChangesetId}
                  onChange={setSelectedChangesetId}
                />
              </Paper>
              <Paper variant="outlined" sx={{ p: 1.5 }}>
                <ClassificationFilter
                  changeset={selectedChangeset}
                  visible={visible}
                  onToggle={toggleClassification}
                />
              </Paper>
              <Paper
                variant="outlined"
                sx={{
                  p: 1.5,
                  borderLeftWidth: change ? 4 : 1,
                  borderLeftColor: change ? CLASSIFICATION_COLORS[change.classification] : "divider",
                  transition: "border-color 150ms",
                }}
              >
                <FeatureDetailPanel
                  change={change}
                  history={history}
                  loading={loadingDetail}
                  error={error}
                />
              </Paper>
            </Stack>
          </Box>
          <Box sx={{ mt: "auto", p: 1.5 }}>
            <Divider sx={{ mb: 1 }} />
            <Typography variant="caption" color="text.secondary" component="div">
              Building data ©{" "}
              <Link href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
                OpenStreetMap contributors
              </Link>
              , ODbL. Basemap ©{" "}
              <Link href="https://openfreemap.org/" target="_blank" rel="noreferrer">
                OpenFreeMap
              </Link>{" "}
              or{" "}
              <Link href="https://www.esri.com/" target="_blank" rel="noreferrer">
                Esri
              </Link>
              .
            </Typography>
          </Box>
        </Drawer>

        <Box component="main" sx={{ flexGrow: 1, position: "relative" }}>
          <Toolbar variant="dense" />
          <Box sx={{ position: "absolute", top: 48, bottom: 0, left: 0, right: 0 }}>
            <MapView
              mode={mode}
              basemap={basemap}
              changesetId={selectedChangesetId}
              contextSnapshotId={selectedChangeset?.snapshot_b_id ?? null}
              visibleClassifications={visible}
              selectedChange={change}
              onSelectChange={handleSelectChange}
            />
            <BasemapToggle value={basemap} onChange={setBasemap} />
          </Box>
        </Box>
      </Box>
    </ThemeProvider>
  );
}
