init:
	pip install -r requirements-dev.txt
	pre-commit install --install-hooks

hooks:
	pre-commit install --install-hooks
