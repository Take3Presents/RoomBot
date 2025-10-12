.PHONY = frontend_build frontend_dev frontend_archive frontend_clean \
	backend_dev backend_archive backend_clean backend_migrations backend_env \
	archive sample_data clean distclean backend_clean_data frontend_clean \
	backend_distclean

# generates the frontend static content
frontend_build:
#	test -d frontend/public/layouts || ./scripts/fetch-images
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
	tar -cvz \
		-C build \
		--exclude "__pycache__" \
		--exclude ".env" \
		--exclude "venv" \
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

backend_env:
	test -d backend/venv || \
		( mkdir backend/venv && \
			virtualenv -p python3.10 backend/venv) && \
		backend/venv/bin/python3 -m pip install --upgrade pip
	backend/venv/bin/pip install \
		-r backend/requirements.txt \
		-r backend/requirements-dev.txt \
		--upgrade

backend_dev: backend_env
	./scripts/start_backend_dev.sh

# tests are cool
backend_tests: backend_env
	./scripts/api_test.sh

# automagically generate django migrations
backend_migrations: backend_env
	backend/venv/bin/python3 backend/manage.py makemigrations

# targets to handle data for local dev environment
sample_data:
	./scripts/sample_data.sh

backend_clean_data:
	rm -rf backend/db.sqlite3

# clean up build artifacts and such
backend_distclean: backend_clean backend_clean_data
	rm -rf backend/venv

backend_clean:
	rm -rf build/roombaht-backend.tgz

frontend_clean:
	rm -rf build/roombaht-frontend.tgz frontend/public/layouts

# project-wide targets
archive: backend_archive frontend_archive
clean: backend_clean frontend_clean
distclean: backend_distclean frontend_clean
