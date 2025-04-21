install:
	pip install --upgrade pip &&\
		pip install -r requirements.txt

format:
	black api/*.py config/*.py core/*.py *.py

lint:
	pylint --disable=R,C api/*.py config/*.py core/*.py core/arbitrage/*.py core/database/*.py core/scrapers/*.py *.py

all: install lint