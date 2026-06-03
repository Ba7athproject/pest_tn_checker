# Makefile for Tunisian Pesticides Reconciliation Pipeline

.PHONY: install test download queue reinject pipeline clean help

help:
	@echo "Available commands:"
	@echo "  install    - Install required dependencies via pip"
	@echo "  test       - Run all pytest unit tests"
	@echo "  download   - Download latest EU reference active substances database"
	@echo "  queue      - Process input products and generate the manual review queue"
	@echo "  reinject   - Reinject manual reviews and build the final approved dataset"
	@echo "  pipeline   - Run complete pipeline end-to-end (download -> queue -> reinject)"
	@echo "  clean      - Remove compiled cache files"

install:
	pip install -r requirements.txt

test:
	python -m pytest tests/ -v

download:
	python scripts/01_download_db.py

queue:
	python scripts/build_manual_review_queue.py --enable-embeddings

reinject:
	python scripts/reinject_decisions.py

pipeline: download queue reinject
	@echo "Pipeline executed successfully! Clean output saved to data/output/pesticides_tn_clean.csv"

clean:
	rm -rf __pycache__ src/**/__pycache__ scripts/__pycache__ tests/__pycache__ utils/__pycache__ .pytest_cache
