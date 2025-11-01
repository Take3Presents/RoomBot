.PHONY = frontend_build frontend_dev frontend_archive frontend_clean \
	local_backend_dev backend_archive local_backend_migrations \
	local_backend_env archive local_sample_data clean distclean \
	local_backend_clean_data frontend_clean backend_distclean \
	test

# generates the frontend static content
frontend_build:
	test -d frontend/public/layouts || ./scripts/fetch-images
	docker build -t roombaht:latest frontend/
	docker run -u node \
		-v $(shell pwd)/frontend:/src \
		-v $(shell pwd)/build:/build \
		roombaht:latest build

# generates artifacts to yeet onto deployment hosts
backend_archive:
	mkdir -p build && \
	cp -r backend build/roombaht-backend && \
	./scripts/version > build/roombaht-backend/reservations/version && \
	cp .python-version build/roombaht-backend && \
	tar -cvz \
		-C build \
		--exclude "__pycache__" \
		--exclude ".env" \
		--exclude "venv" \
		--exclude ".venv" \
		--exclude "db.sqlite3" \
		roombaht-backend > build/roombaht-backend.tgz && \
	rm -rf build/roombaht-backend

frontend_archive: frontend_build
	mkdir -p build && \
	cp -r frontend/build build/roombaht-frontend && \
	tar -cvz \
		-C build \
		roombaht-frontend > build/roombaht-frontend.tgz && \
	rm -rf build/roombaht-frontend


# targets to support local non-containerized development environments
frontend_dev: frontend_build
	docker run -ti \
		-p 3000:3000 \
		-u node \
		-v $(shell pwd)/frontend/:/app roombaht:latest

install_python:
	uv python find `cat .python-version` || \
		uv python install `cat .python-version`

local_backend_env: install_python
	test -d backend/.venv || \
		( mkdir backend/.venv && \
		    uv sync \
		      --python `cat .python-version` \
		      --project backend/pyproject.toml \
		      --frozen )

local_backend_dev: local_backend_env
	./scripts/start_backend_dev.sh

# tests are cool
local_backend_tests: backend_unit_tests local_tavern_tests

local_tavern_tests: local_backend_env
	@docker compose down 2>/dev/null || true
	./scripts/api_test.sh

backend_unit_tests: local_backend_env
	./scripts/manage_dev test backend/reservations

# automagically generate django migrations
local_backend_migrations: local_backend_env
	./scripts/manage_dev makemigrations

# targets to handle data for local dev environment
local_sample_data: local_backend_env
	./scripts/sample_data.sh

local_backend_clean_data:
	rm -rf backend/db.sqlite3

# clean up build artifacts and such
local_backend_distclean: local_backend_clean local_backend_clean_data
	rm -rf backend/.venv

local_backend_clean:
	rm -rf build/roombaht-backend.tgz

frontend_clean:
	rm -rf build/roombaht-frontend.tgz frontend/public/layouts

# project-wide targets
archive: backend_archive frontend_archive
clean: local_backend_clean frontend_clean
distclean: local_backend_distclean frontend_clean

# testing shortcut
test: local_backend_tests frontend_e2e_tests

frontend_e2e_tests:
# Build images and start app services in the background
	docker compose up -d --build db backend frontend
# Prepare backend database: migrate and load test fixtures
	@echo "Seeding backend with test fixtures..."
	docker compose exec -T backend sh -lc "uv run python manage.py migrate --noinput"
	docker compose exec -T backend sh -lc "uv run python manage.py loaddata test_admin test_users test_rooms"
# Wait for the frontend to be ready inside the container (no host curl dependency)
	until docker compose exec -T frontend sh -lc "curl -sf http://localhost:3000/ > /dev/null"; do \
		echo "Waiting for frontend at http://localhost:3000 ..."; \
		sleep 2; \
	done
# Run the Playwright tests in the test container
	docker compose run --rm frontend-e2e
# And clean up
	docker compose stop
