.PHONY: install test lint run-daily run-weekly clean

install:
	pip install -r requirements.txt

test:
	pytest tests/

run-daily:
	export PYTHONPATH=$$PYTHONPATH:. && python src/main.py --type daily

run-weekly:
	export PYTHONPATH=$$PYTHONPATH:. && python src/main.py --type weekly

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache
	rm -rf .venv
