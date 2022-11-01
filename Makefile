.PHONY: minimal
minimal: venv

venv: requirements.txt setup.py tox.ini
	tox -e venv

.PHONY: test
test:
	tox

.PHONY: clean
clean:
	find -name '*.pyc' -delete
	find -name '__pycache__' -delete
	rm -rf .tox
	rm -rf venv
