.PHONY: test build

test:
	@bash httpstat_test.sh

clean:
	rm -rf build dist *.egg-info

build:
	python3 setup.py build

build-dist:
	python3 setup.py sdist bdist_wheel

publish: clean build-dist
	python3 -m twine upload dist/*
