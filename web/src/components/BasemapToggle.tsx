import { Paper, ToggleButton, ToggleButtonGroup, Tooltip } from "@mui/material";
import MapIcon from "@mui/icons-material/Map";
import SatelliteAltIcon from "@mui/icons-material/SatelliteAlt";
import type { BasemapChoice } from "../theme";

interface Props {
  value: BasemapChoice;
  onChange: (value: BasemapChoice) => void;
}

/** Floating control, positioned like a native MapLibre control, that lets
 *  the user swap the vector street basemap for Esri satellite imagery --
 *  independent of the light/dark UI theme, since satellite view has no
 *  meaningful "dark mode" of its own. */
export function BasemapToggle({ value, onChange }: Props) {
  return (
    <Paper
      elevation={2}
      sx={{ position: "absolute", top: 10, left: 10, zIndex: 1, borderRadius: 1.5 }}
    >
      <ToggleButtonGroup
        value={value}
        exclusive
        size="small"
        onChange={(_event, next: BasemapChoice | null) => next && onChange(next)}
      >
        <ToggleButton value="map" aria-label="Street map view">
          <Tooltip title="Street map">
            <MapIcon fontSize="small" />
          </Tooltip>
        </ToggleButton>
        <ToggleButton value="satellite" aria-label="Satellite imagery view">
          <Tooltip title="Satellite imagery">
            <SatelliteAltIcon fontSize="small" />
          </Tooltip>
        </ToggleButton>
      </ToggleButtonGroup>
    </Paper>
  );
}
