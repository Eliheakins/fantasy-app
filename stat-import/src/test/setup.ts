import { useManifestStore } from "@/stores/useManifestStore";

import { FIXTURE_SEASONS } from "./seasons";

// Season chips come from the data manifest; give every test file the fixture's seasons.
useManifestStore.setState({ seasons: FIXTURE_SEASONS });
