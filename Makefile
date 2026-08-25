.PHONY: run test

run:
	python3 server.py --host 127.0.0.1 --port 7771

test:
	python3 -m pytest -q
