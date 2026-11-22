# nuget-deprecation-report fixtures

`deprecated/` is a `.slnx` with one `net10.0` project, central package management (`Directory.Packages.props`), and `global.json` pinning SDK `10.0.100` (`rollForward: latestFeature`).

| Package | Version | Deprecation reason | Alternative | Reference |
|---|---|---|---|---|
| `Microsoft.Azure.ServiceBus` | 5.2.0 | `Legacy` | `Azure.Messaging.ServiceBus` | direct |

It also pulls six deprecated (`Legacy`) transitive packages, four of them without an alternative. Expected report result: pass, `deprecated-count` 7, one `::warning::` for the direct package.

`Directory.Build.props` sets `TreatWarningsAsErrors=false`: the transitive `Newtonsoft.Json` 10.0.3 has a High advisory (NU1903), which would otherwise fail restore before the report runs.

Recorded `dotnet list package --deprecated` outputs for the unit tests are in `tests/unit/nuget-deprecation-report/fixtures/`. `deprecated.json` and `not-restored.json` come from this fixture with and without restore. Absolute paths are rewritten to `/home/runner/work/app`.
