.PHONY: test build clean

test:
	@bash httpstat_test.sh

clean:
	rm -rf build dist *.egg-info

build:
	uv build

publish: clean build
	uv publish
