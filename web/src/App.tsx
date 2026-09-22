import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AppBar, Box, CssBaseline, Divider, Drawer, IconButton, Link, Stack,
  ThemeProvider, Toolbar, Tooltip, Typography,
} from "@mui/material";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import LightModeIcon from "@mui/icons-material/LightMode";
import { api } from "./api/client";
import {
  CLASSIFICATIONS, type ChangeDetail, type Changeset, type Classification,
  type FeatureHistory,
} from "./api/types";
import { buildTheme } from "./theme";
import { useColorMode } from "./hooks/useColorMode";
import { MapView } from "./components/MapView";
import { ChangesetPicker } from "./components/ChangesetPicker";
import { ClassificationFilter } from "./components/ClassificationFilter";
import { FeatureDetailPanel } from "./components/FeatureDetailPanel";

const DRAWER_WIDTH = 380;

export default function App() {
  const { mode, toggle } = useColorMode();
  const theme = useMemo(() => buildTheme(mode), [mode]);

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
        if (list.length) setSelectedChangesetId(list[0].id);
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
        <AppBar position="fixed" sx={{ zIndex: (t) => t.zIndex.drawer + 1 }}>
          <Toolbar variant="dense">
            <Typography variant="h6" sx={{ flexGrow: 1 }}>
              GIS Vector Map Changes — Tel Aviv-Yafo
            </Typography>
            <Tooltip title={mode === "dark" ? "Switch to light mode" : "Switch to dark mode"}>
              <IconButton color="inherit" onClick={toggle} aria-label="toggle color mode">
                {mode === "dark" ? <LightModeIcon /> : <DarkModeIcon />}
              </IconButton>
            </Tooltip>
          </Toolbar>
        </AppBar>

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
              <ChangesetPicker
                changesets={changesets}
                selectedId={selectedChangesetId}
                onChange={setSelectedChangesetId}
              />
              <ClassificationFilter
                changeset={selectedChangeset}
                visible={visible}
                onToggle={toggleClassification}
              />
              <Divider />
              <FeatureDetailPanel
                change={change}
                history={history}
                loading={loadingDetail}
                error={error}
              />
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
              changesetId={selectedChangesetId}
              contextSnapshotId={selectedChangeset?.snapshot_b_id ?? null}
              visibleClassifications={visible}
              selectedChange={change}
              onSelectChange={handleSelectChange}
            />
          </Box>
        </Box>
      </Box>
    </ThemeProvider>
  );
}
