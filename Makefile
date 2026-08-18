.PHONY: install clean

install:
	poetry install

check-settings:
	./check_settings.sh

test: install
	poetry run pytest

clean:
	rm -rf dist
	rm -rf *.egg-info
