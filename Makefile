all:

install:
	install -m755 onion_layers.py $(HOME)/.gimp-2.8/plug-ins

test:
	python2.7 tests.py

.PHONY: all install test
