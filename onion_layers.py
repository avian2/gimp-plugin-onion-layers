#!/usr/bin/env python
from gimpfu import *
import re

NEXT_PREV_OPACITY = 25.

DEFAULT_CONTEXTS = [
	[ None, 100., None ],
	[ NEXT_PREV_OPACITY, 100., NEXT_PREV_OPACITY ],
	[ None, 100., NEXT_PREV_OPACITY ],
	[ NEXT_PREV_OPACITY, 100., None ],
]

class Frame(object):
	def __init__(self, layer):
		self.layer = layer
		self.opacity = None
		self.visible = None

	def apply(self):
		# we do it this way to prevent unnecessarily cluttering the undo history.
		#
		# AFIAK there is not way to manipulate the history from a plug-in.

		if (self.opacity is not None) and (self.layer.opacity != self.opacity):
			self.layer.opacity = self.opacity

		if (self.visible is not None) and (self.layer.visible != self.visible):
			self.layer.visible = self.visible


def get_frames(img):
	for layer in img.layers:
		if layer.name.startswith('['):
			continue

		yield Frame(layer)

def sanitize_name(name):
	return re.sub(r'\d+', '', name)

def show_all(img, act_layer):
	img.undo_group_start()

	for frame in get_frames(img):
		frame.opacity = 100.
		frame.visible = True
		frame.apply()

	img.undo_group_end()

def onion(img, act_layer, inc, context=None, dryrun=False):

	# Frames are either top-level layers or layer groups.
	frames = list(get_frames(img))

	# If no frames were found, do nothing.
	N = len(frames)
	if N < 1:
		return

	# Find the currently visible frame.
	i = None
	for j, frame in enumerate(frames):
		if frame.layer.visible and (frame.layer.opacity == 100.):
			i = j

	# If no visible frame was found, do nothing.
	if i is None:
		return

	CONTEXT_SIZE = 1
	if context is None:
		# Find which neighboring frames are also currently visible -
		# this is our desired context.

		context = [ None ] * (CONTEXT_SIZE*2 + 1)
		for c in range(-CONTEXT_SIZE, CONTEXT_SIZE + 1):
			# index into context
			j = c + CONTEXT_SIZE
			# frame
			k = (i + c) % N

			if frames[k].layer.visible:
				context[j] = frames[k].layer.opacity

	if not dryrun:
		# Select the next or previous frame.
		i = (i + inc) % N

		# Change visibility of frames.
		for frame in frames:
			frame.visible = False

		assert (len(context) % 2) == 1

		# index into context
		for j in range(len(context)):
			# context offset
			c = j - (len(context) - 1) // 2
			# frame
			k = (i + c) % N

			if (context[j] is not None) and (k != i) and not frames[k].visible:
				frames[k].opacity = context[j]
				frames[k].visible = True

		frames[i].opacity = 100.
		frames[i].visible = True

		img.undo_group_start()

		for frame in frames:
			frame.apply()

		img.undo_group_end()

		# Use some heuristic to change the active layer as well.
		if hasattr(frames[i].layer, 'layers'):
			n = sanitize_name(act_layer.name)

			for layer in frames[i].layer.layers:
				if sanitize_name(layer.name) == n:
					img.active_layer = layer
					break
		else:
			img.active_layer = frames[i].layer

	return context

def onion_up(img, layer):
	onion(img, layer, -1, [100.])

def onion_down(img, layer):
	onion(img, layer, 1, [100.])

def onion_up_ctx(img, layer):
	onion(img, layer, -1, [NEXT_PREV_OPACITY, 100., NEXT_PREV_OPACITY])

def onion_down_ctx(img, layer):
	onion(img, layer, 1, [NEXT_PREV_OPACITY, 100., NEXT_PREV_OPACITY])

def onion_up_ctx_auto(img, layer):
	onion(img, layer, -1, None)

def onion_down_ctx_auto(img, layer):
	onion(img, layer, 1, None)

def onion_cycle_context(img, layer):

	context = onion(img, layer, 0, dryrun=True)

	try:
		current_default = DEFAULT_CONTEXTS.index(context)
	except ValueError:
		current_default = -1

	current_default = (current_default + 1) % len(DEFAULT_CONTEXTS)

	onion(img, layer, 0, DEFAULT_CONTEXTS[current_default])

register(
	"python_fu_onion_up",
	"Onion up",
	"Move one onion layer up",
	"Tomaz Solc",
	"Open source (BSD 3-clause license)",
	"2017",
	"<Image>/Filters/Animation/Onion layers/up",
	"*",
	[],
	[],
	onion_up)

register(
	"python_fu_onion_down",
	"Onion down",
	"Move one onion layer down",
	"Tomaz Solc",
	"GPLv3+",
	"2017",
	"<Image>/Filters/Animation/Onion layers/down",
	"*",
	[],
	[],
	onion_down)

register(
	"python_fu_onion_up_ctx",
	"Onion up, contex",
	"Move one onion layer up, show next/prev frame",
	"Tomaz Solc",
	"GPLv3+",
	"2017",
	"<Image>/Filters/Animation/Onion layers/up, context",
	"*",
	[],
	[],
	onion_up_ctx)

register(
	"python_fu_onion_down_ctx",
	"Onion down, context",
	"Move one onion layer down, show next/prev frame",
	"Tomaz Solc",
	"GPLv3+",
	"2017",
	"<Image>/Filters/Animation/Onion layers/down, context",
	"*",
	[],
	[],
	onion_down_ctx)

register(
	"python_fu_onion_up_ctx_auto",
	"Onion up, auto context",
	"Move one onion layer up, retain current context",
	"Tomaz Solc",
	"GPLv3+",
	"2017",
	"<Image>/Filters/Animation/Onion layers/up, auto context",
	"*",
	[],
	[],
	onion_up_ctx_auto)

register(
	"python_fu_onion_down_ctx_auto",
	"Onion down, auto context",
	"Move one onion layer down, retain current context",
	"Tomaz Solc",
	"GPLv3+",
	"2017",
	"<Image>/Filters/Animation/Onion layers/down, auto context",
	"*",
	[],
	[],
	onion_down_ctx_auto)

register(
	"python_fu_onion_cycle_ctx",
	"Cycle through frame contexts",
	"Cycle through no, prev, next, prev/next contexts.",
	"Tomaz Solc",
	"GPLv3+",
	"2017",
	"<Image>/Filters/Animation/Onion layers/cycle context",
	"*",
	[],
	[],
	onion_cycle_context)

register(
	"python_fu_onion_show_all",
	"Show all frames",
	"Shows all frames with full opacity",
	"Tomaz Solc",
	"GPLv3+",
	"2017",
	"<Image>/Filters/Animation/Onion layers/Show all",
	"*",
	[],
	[],
	show_all)

main()
