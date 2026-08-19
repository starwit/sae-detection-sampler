# SAE Detection Sampler

This is a component that samples detections according to constraints.

# How-to start

## Check prerequisites
In order to work with this repository, you need to ensure the following steps:
- Install Poetry
- Install Docker with compose plugin
- Clone main SAE repository (you will most likely need a running SAE to do anything useful): https://github.com/starwit/starwit-awareness-engine

## Setup
- Run `poetry install`, this should install all necessary dependencies
- Start docker compose version of the SAE (see here: https://github.com/starwit/starwit-awareness-engine/blob/main/docker-compose/README.md)
- Run `poetry run python main.py`. If you see log messages like `Received SAE message from pipeline`, everything works as intended.

## Configuration
This template employs pydantic-settings for configuration handling. On startup, the following happens:
1. Load defaults (see `config.py`)
2. Read settings `settings.yaml` if it exists
3. Search through environment variables if any match configuration parameters (converted to upper_snake_case, nested levels delimited by `__`), overwriting the corresponding setting
4. Validate settings hierarchy if all necessary values are filled, otherwise Pydantic will throw a hopefully helpful error

The `settings.template.yaml` should always reflect a correct and fully fledged settings structure to use as a starting point for users. 

Note that `filters` is a list, and pydantic-settings does not merge a list across sources. Overriding it by environment variable therefore means passing the whole list as JSON, e.g. `FILTERS='[{"name": "crowded", "matching_count_above": 20}]'`.

## Filtering

A message is forwarded if **any** filter matches (OR). A filter matches if the number of detections that satisfy **all** of its `match_detection` predicates (AND) is greater than `matching_count_above` (default `0`, i.e. at least one matching detection).

The `match_detection` predicates are evaluated per single detection, so one and the same detection has to satisfy all of them. A filter with `class_id_in: [ 0 ]` and `confidence_below: 0.4` matches a person that was detected with low confidence — not a frame that happens to contain both a person and some unrelated low confidence detection. Delete a predicate to deactivate it; delete the whole `match_detection` block to count every detection.

| Predicate | Matches a detection whose ... |
| --- | --- |
| `class_id_in: [ 0, 1 ]` | `class_id` is any of the listed ids |
| `confidence_below: 0.2` | confidence is below the value |
| `width_below: 0.001` | bounding box width is below the value |
| `height_below: 0.001` | bounding box height is below the value |

Two optional timing settings limit the output:

- `cooldown` (per filter) puts a lower bound on the interval between messages forwarded by that filter. Filters are independent: a filter sitting in its cooldown is not affected by another filter forwarding a message.
- `heartbeat_interval` (top level) forwards a message if none has been forwarded for that long, regardless of the filters and regardless of whether the frame contains detections at all.

Both take a natural duration string: `1 day`, `5h`, `10 minutes`, `2h30m`, `1 day, 30 seconds`. Supported units are seconds, minutes, hours, days and weeks, each also as its usual abbreviation (`s`/`sec`, `m`/`min`, `h`/`hr`, `d`, `w`). All timing is measured in frame time (`frame.timestamp_utc_ms`), so the component behaves identically on a replayed stream.

Per filter, `detection_selector_filter_match_counter{filter="<name>"}` counts how often that filter caused a message to be forwarded (label value `heartbeat` for the heartbeat), which is the intended way to tune the filters.

## Github Workflows and Versioning

The following Github Actions are available:

* [PR build](.github/workflows/pr-build.yml): Builds python project for each pull request to main branch. `poetry install` and `poetry run pytest` are executed, to compile and test python code.
* [Build and publish latest image](.github/workflows/build-publish-latest.yml): Manually executed action. Same like PR build. Additionally puts latest docker image to internal docker registry.
* [Create release](.github/workflows/create-release.yml): Manually executed action. Creates a github release with tag, docker image in internal docker registry, helm chart in chartmuseum by using and incrementing the version in pyproject.toml. Poetry is updating to next version by using "patch, minor and major" keywords. If you want to change to non-incremental version, set version in directly in pyproject.toml and execute create release afterwards.

## Dependabot Version Update

With [dependabot.yml](.github/dependabot.yml) a scheduled version update via Dependabot is configured. Dependabot creates a pull request if newer versions are available and the compilation is checked via PR build.

## Changelog
### 1.0.0
- **Breaking**: Reworked the filter configuration into a list of independent `filters` (see [Filtering](#filtering)). The options `min_confidence`, `min_width`, `min_height`, `max_detections`, `time_past` and `cooldown_seconds` are gone and a settings file that still uses them is rejected at startup. Migration:
  - `min_confidence` / `min_width` / `min_height` / `max_detections` were ORed with each other, so every one of them that you used becomes its own filter with `confidence_below` / `width_below` / `height_below` / `matching_count_above`. Putting several predicates into one filter now ANDs them.
  - `time_past` becomes `heartbeat_interval`, `cooldown_seconds` becomes a per-filter `cooldown`. Both take a natural duration (`30s`, `10 minutes`, `1 day`) instead of a number of seconds.
- Add predicate `class_id_in`, and make every predicate optional - deleting it deactivates it
- Add metric `detection_selector_filter_match_counter`, labelled by filter name
- The heartbeat now also fires on frames without detections, and is no longer lost when the message it would have triggered is suppressed

### 0.2.0
- Add option `cooldown_seconds` (puts a lower bound on consecutive message interval)