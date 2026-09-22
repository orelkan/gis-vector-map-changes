import { useCallback, useEffect, useMemo, useState } from "react";
import { useMediaQuery, type PaletteMode } from "@mui/material";

const STORAGE_KEY = "gvmc-color-mode";

/** localStorage is not always usable -- Safari private mode and
 *  storage-disabled browsers throw on access, and it is absent in some
 *  non-browser runtimes. Persisting a colour preference is a nicety, so
 *  failures degrade to "don't remember" rather than breaking the app. */
function readStoredMode(): PaletteMode | null {
  try {
    const stored = globalThis.localStorage?.getItem(STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : null;
  } catch {
    return null;
  }
}

function writeStoredMode(mode: PaletteMode): void {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, mode);
  } catch {
    // Preference simply won't persist; not worth surfacing to the user.
  }
}

/** Colour mode with an explicit override persisted across reloads.
 *
 * Defaults to the OS preference, but once the user picks a mode that choice
 * wins -- otherwise toggling would silently revert on the next visit.
 */
export function useColorMode() {
  const prefersDark = useMediaQuery("(prefers-color-scheme: dark)");
  const [override, setOverride] = useState<PaletteMode | null>(readStoredMode);

  const mode: PaletteMode = override ?? (prefersDark ? "dark" : "light");

  useEffect(() => {
    if (override) writeStoredMode(override);
  }, [override]);

  const toggle = useCallback(() => {
    setOverride(mode === "dark" ? "light" : "dark");
  }, [mode]);

  return useMemo(() => ({ mode, toggle }), [mode, toggle]);
}
