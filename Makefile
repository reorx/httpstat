.PHONY: test

test:
	@bash httpstat_test.sh

publish:
	python setup.py sdist bdist_wheel upload
