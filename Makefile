# bash を明示指定（WSL の /bin/sh が dash の場合 pipefail が使えないため）
SHELL := /bin/bash

.PHONY: deploy-firestore-indexes
.PHONY: deploy-cloud-run
.PHONY: release-cloud-run
.PHONY: firestore-emulator
.PHONY: seed-firestore-demo

CLOUD_RUN_SCRIPT := ./scripts/deploy_cloud_run.sh
DEPLOY_CLOUD_RUN_ARGS = $(if $(PROJECT_ID),--project-id $(PROJECT_ID),) \
        $(if $(REGION),--region $(REGION),) \
        $(if $(SERVICE),--service $(SERVICE),) \
        $(if $(ARTIFACT_REPO),--artifact-repo $(ARTIFACT_REPO),) \
        $(if $(IMAGE_URI),--image-uri "$(IMAGE_URI)",) \
        $(if $(RUN_TIMEOUT),--run-timeout $(RUN_TIMEOUT),) \
        $(if $(MIN_INSTANCES),--min-instances $(MIN_INSTANCES),) \
        $(if $(NO_CPU_THROTTLING),--no-cpu-throttling,) \
        $(if $(filter true,$(NO_TRAFFIC)),--no-traffic,) \
        $(if $(TRAFFIC_TAG),--traffic-tag $(TRAFFIC_TAG),) \
        $(if $(GENERATE_SECRET),--generate-secret,) \
        $(if $(SECRET_LENGTH),--secret-length $(SECRET_LENGTH),) \
        $(if $(filter true,$(VALIDATE_IN_IMAGE)),--validate-in-image,) \
        $(if $(DRY_RUN),--dry-run,) \
        $(if $(ENV_FILE),--env-file $(ENV_FILE),)

SKIP_FIRESTORE_INDEX_SYNC ?= false
FIRESTORE_PROJECT_ID ?= wordpack-local
FIRESTORE_EMULATOR_HOST ?= 127.0.0.1:8080
FIRESTORE_EMULATOR_PORT ?= 8080
FIRESTORE_EMULATOR_BIND ?= 127.0.0.1
FIRESTORE_EMULATOR_DATA ?= firestore-emulator-data
SQLITE_DEMO_PATH ?= .data_demo/wordpack.sqlite3.demo

# 使用例:
#   make deploy-firestore-indexes PROJECT_ID=my-gcp-project
#   make deploy-firestore-indexes PROJECT_ID=my-firebase-project TOOL=firebase

deploy-firestore-indexes:
	./scripts/deploy_firestore_indexes.sh $(if $(PROJECT_ID),--project $(PROJECT_ID),) $(if $(TOOL),--tool $(TOOL),)

firestore-emulator:
	@echo "[firestore-emulator] Firebase CLI 経由で Firestore エミュレータを起動し、firebase.json / firestore.indexes.json を読み込みます"
	./scripts/start_firestore_emulator.sh --project-id "$(FIRESTORE_PROJECT_ID)" --port "$(FIRESTORE_EMULATOR_PORT)" --bind "$(FIRESTORE_EMULATOR_BIND)" --import-dir "$(FIRESTORE_EMULATOR_DATA)"

seed-firestore-demo:
	@echo "[seed-firestore-demo] $(SQLITE_DEMO_PATH) から Firestore へ開発用データを投入します"
	FIRESTORE_PROJECT_ID="$(FIRESTORE_PROJECT_ID)" FIRESTORE_EMULATOR_HOST="$(FIRESTORE_EMULATOR_HOST)" python ./scripts/seed_firestore_demo.py --sqlite-path "$(SQLITE_DEMO_PATH)" --project-id "$(FIRESTORE_PROJECT_ID)" --emulator-host "$(FIRESTORE_EMULATOR_HOST)"

deploy-cloud-run:
	$(CLOUD_RUN_SCRIPT) $(DEPLOY_CLOUD_RUN_ARGS)

release-cloud-run: ENV_FILE ?= .env.deploy
# release-cloud-run: Cloud Run dry-run → Firestore インデックス同期 → 本番デプロイを一括で行い、
# `.env.deploy` などの env ファイル存在チェックと dry-run 成功を副作用の前提条件にしています。
release-cloud-run:
	@set -euo pipefail; \
	PROJECT_ID_VALUE="$(PROJECT_ID)"; \
	REGION_VALUE="$(REGION)"; \
	ARTIFACT_REPO_VALUE="$(ARTIFACT_REPO)"; \
	ENV_FILE_PATH="$(ENV_FILE)"; \
	IMAGE_URI_VALUE="$(IMAGE_URI)"; \
	SKIP_INDEX_SYNC="$(SKIP_FIRESTORE_INDEX_SYNC)"; \
	FIRESTORE_TOOL_VALUE="$(TOOL)"; \
	if [ -z "$$PROJECT_ID_VALUE" ]; then \
	echo "[release-cloud-run] PROJECT_ID is required (pass PROJECT_ID= or export the variable)" >&2; \
	exit 1; \
	fi; \
	if [ -z "$$REGION_VALUE" ]; then \
	echo "[release-cloud-run] REGION is required (pass REGION= or export the variable)" >&2; \
	exit 1; \
	fi; \
	if [ -z "$$ARTIFACT_REPO_VALUE" ]; then ARTIFACT_REPO_VALUE="wordpack/backend"; fi; \
	if [[ ! "$$PROJECT_ID_VALUE" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$$ ]]; then \
	echo "[release-cloud-run] PROJECT_ID must be a valid Google Cloud project ID" >&2; \
	exit 1; \
	fi; \
	if [[ ! "$$REGION_VALUE" =~ ^[a-z0-9]+(-[a-z0-9]+)*$$ ]]; then \
	echo "[release-cloud-run] REGION must be a valid Artifact Registry location" >&2; \
	exit 1; \
	fi; \
	if [[ ! "$$ARTIFACT_REPO_VALUE" =~ ^[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)*$$ ]]; then \
	echo "[release-cloud-run] ARTIFACT_REPO must be a valid Artifact Registry image path" >&2; \
	exit 1; \
	fi; \
	if [ -z "$$ENV_FILE_PATH" ]; then \
	echo "[release-cloud-run] ENV_FILE is required; default .env.deploy was not resolved" >&2; \
	exit 1; \
	fi; \
	if [ -z "$$IMAGE_URI_VALUE" ]; then \
	echo "[release-cloud-run] IMAGE_URI is required and must be an immutable image digest" >&2; \
	exit 1; \
	fi; \
	EXPECTED_IMAGE_NAME="$$REGION_VALUE-docker.pkg.dev/$$PROJECT_ID_VALUE/$$ARTIFACT_REPO_VALUE"; \
	IMAGE_DIGEST_VALUE="$${IMAGE_URI_VALUE##*@}"; \
	if [[ "$$IMAGE_URI_VALUE" != "$$EXPECTED_IMAGE_NAME@"* ]] || \
	[[ ! "$$IMAGE_DIGEST_VALUE" =~ ^sha256:[0-9a-f]{64}$$ ]] || \
	[[ "$$IMAGE_URI_VALUE" != "$$EXPECTED_IMAGE_NAME@$$IMAGE_DIGEST_VALUE" ]]; then \
	echo "[release-cloud-run] IMAGE_URI must exactly match $$EXPECTED_IMAGE_NAME@sha256:<64 lowercase hex>" >&2; \
	exit 1; \
	fi; \
	if [ ! -f "$$ENV_FILE_PATH" ]; then \
	echo "[release-cloud-run] Env file not found: $$ENV_FILE_PATH" >&2; \
	echo "Please prepare the file (cp env.deploy.example $$ENV_FILE_PATH) before releasing." >&2; \
	exit 1; \
	fi; \
	if [ "$$SKIP_INDEX_SYNC" != "true" ] && [ -n "$$FIRESTORE_TOOL_VALUE" ] && \
	[ "$$FIRESTORE_TOOL_VALUE" != "gcloud" ] && [ "$$FIRESTORE_TOOL_VALUE" != "firebase" ]; then \
	echo "[deploy_firestore_indexes.sh] --tool には gcloud または firebase を指定してください" >&2; \
	exit 1; \
	fi; \
	echo "[release-cloud-run] Validating Cloud Run configuration via dry-run"; \
	SKIP_FIRESTORE_INDEX_SYNC=true $(CLOUD_RUN_SCRIPT) $(DEPLOY_CLOUD_RUN_ARGS) --dry-run; \
	if [ "$$SKIP_INDEX_SYNC" != "true" ]; then \
	echo "[release-cloud-run] Syncing Firestore indexes before deployment"; \
	$(MAKE) --no-print-directory deploy-firestore-indexes PROJECT_ID="$$PROJECT_ID_VALUE" $(if $(TOOL),TOOL=$(TOOL),); \
	else \
	echo "[release-cloud-run] Skipping Firestore index sync because SKIP_FIRESTORE_INDEX_SYNC=true"; \
	fi; \
	echo "[release-cloud-run] Dry-run succeeded. Deploying to Cloud Run"; \
	SKIP_FIRESTORE_INDEX_SYNC=true $(CLOUD_RUN_SCRIPT) $(DEPLOY_CLOUD_RUN_ARGS)
