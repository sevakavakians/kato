# Chart ↔ KATO compatibility

The chart `version` and the KATO `appVersion` are versioned independently:

- **`appVersion`** (KATO container image tag) is bumped in lockstep with KATO releases via `bump-version.sh`.
- **`version`** (chart version) is bumped manually in the same commit when chart templates or values change. Patch bump for fixes/docs, minor for additive values, major for breaking renames.

The chart at any version is supported as long as the pinned `appVersion` line is supported by KATO.

## Compatibility matrix

| Chart version | Supported KATO `appVersion` | Notes |
|---------------|-----------------------------|-------|
| `0.1.x`       | `3.10.1` – `3.10.x`         | Initial release. Requires KATO ≥ 3.10.1 because `/metrics-prom` and the image's non-root `USER` were added in 3.10.2. |

## Breaking change policy

- **Values keys**: deprecated keys remain accepted for one chart-minor cycle (with a `NOTES.txt` warning), then removed in the following minor.
- **Schema migrations**: the bootstrap Job applies the canonical `init.sql` shipped inside the chart. When KATO introduces a schema-breaking change, the chart bumps to a new major.
- **PSS / security defaults**: tightening defaults that could break existing deployments (e.g., new mandatory readOnlyRootFilesystem behavior) only happens on chart-major bumps.

## Choosing a chart version

If you pin a KATO image tag explicitly via `image.tag`, choose the chart row whose `appVersion` range includes your tag. If you do not set `image.tag`, the chart's default `appVersion` is used.
