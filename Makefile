.PHONY: build-catalog

build-catalog:
	python -m vibelens.catalog \
		--hub-dir ../agent-skills/hub \
		--output src/vibelens/data/catalog.json \
		--existing src/vibelens/data/catalog.json \
		--stats
