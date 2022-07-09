#GIMP_PLUGIN_DIR?=$(HOME)/.gimp-2.8/plugins
GIMP_PLUGIN_DIR?=$(HOME)/.config/GIMP/2.10/plug-ins

all:

install:
	install -m755 onion_layers.py $(GIMP_PLUGIN_DIR)

test:
	python2.7 tests.py

.PHONY: all install test
