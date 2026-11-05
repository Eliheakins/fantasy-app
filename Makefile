.PHONY: setup test lint fmt check refresh backup schedule-install schedule-remove serve dev web-build odds odds-slate stat-data stat-data-refresh ask-model

backup:
	uv run python -m fantasy.stages.backup

refresh: backup
	uv run python -m fantasy.stages.sync_sleeper
	uv run python -m fantasy.stages.news_archive
	uv run python -m fantasy.stages.sleeper_projections
	uv run python -m fantasy.stages.outside_projections
	uv run python -m fantasy.stages.ingest_nfl
	uv run python -m fantasy.stages.crosswalk
	uv run python -m fantasy.stages.score
	uv run python -m fantasy.stages.prop_points
	uv run python -m fantasy.stages.streaming
	uv run python -m fantasy.stages.project
	uv run python -m fantasy.stages.learn
	uv run python -m fantasy.stages.availability
	uv run python -m fantasy.stages.distributions
	uv run python -m fantasy.stages.injuries
	uv run python -m fantasy.stages.outlook
	uv run python -m fantasy.stages.environment
	uv run python -m fantasy.stages.simulate
	uv run python -m fantasy.stages.digest
	uv run python -m fantasy.stages.market_values
	$(MAKE) stat-data-refresh

# nflverse play-by-play shards for the stat app, into data/stat (needs the network, takes minutes)
stat-data:
	uv run python -m nfl_stat.pipeline.cli

# Rebuild only the current season; other seasons are kept
stat-data-refresh:
	uv run python -m nfl_stat.pipeline.cli --refresh

# Local model for Ask (Apple Silicon; first run downloads about 2 GB). Ask works without it for
# questions the rules can read.
# Keep equal to the default of AppSettings.llm_model in src/nfl_stat/core/config.py
LLM_MODEL ?= mlx-community/Qwen3-4B-Instruct-2507-4bit
ask-model:
	uv run --group llm mlx_lm.server --model $(LLM_MODEL) --port 8080

web-build:
	cd web && npm run build

serve: web-build
	uv run python -m fantasy.api

dev:
	uv run uvicorn --factory fantasy.api:create_app --reload --port 8000 & cd web && npm run dev

setup:
	uv sync
	cd web && npm ci --ignore-scripts
	git config core.hooksPath .githooks

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run mypy src

fmt:
	uv run ruff check --fix .
	uv run ruff format .

check: lint
	uv run ruff format --check .
	uv run pytest -q
	cd web && npm run typecheck && npm test

odds:
	uv run python -m fantasy.stages.snapshot_odds

odds-slate:
	uv run python -m fantasy.stages.snapshot_odds --slate

# Scheduled refresh (macOS launchd): Tuesday 06:00, Friday 18:00, Sunday 08:00, local time. The
# Mac must be awake; a missed run is not repeated. Output goes to data/refresh.log.
PLIST = $(HOME)/Library/LaunchAgents/com.fantasy-app.refresh.plist
LAUNCH_PATH = $(dir $(shell command -v uv)):$(HOME)/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin

schedule-install:
	mkdir -p $(HOME)/Library/LaunchAgents data
	sed -e "s|__REPO__|$(CURDIR)|g" -e "s|__PATH__|$(LAUNCH_PATH)|g" ops/refresh.plist > $(PLIST)
	plutil -lint $(PLIST)
	-launchctl bootout gui/$$(id -u) $(PLIST)
	launchctl bootstrap gui/$$(id -u) $(PLIST)

schedule-remove:
	-launchctl bootout gui/$$(id -u) $(PLIST)
	rm -f $(PLIST)
