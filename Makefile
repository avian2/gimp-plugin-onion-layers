all:

install:
	install -m755 onion_layers.py $(HOME)/.gimp-2.8/plug-ins

.PHONY: all install
