.PHONY: minimal
minimal: venv

venv: requirements.txt setup.py tox.ini
	tox -e venv

.PHONY: test
test:
	tox -e tests

.PHONY: pre-commit
pre-commit:
	tox -e pre-commit

.PHONY: clean
clean:
	find -name '*.pyc' -delete
	find -name '__pycache__' -delete
	rm -rf .tox
	rm -rf venv

.PHONY: install-hooks
install-hooks:
	tox -e install-hooks
