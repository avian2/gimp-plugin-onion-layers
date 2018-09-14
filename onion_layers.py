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

# see gimpshelf for persistent storage

class Frame(object):
	TINT_COLORS = {
		'before': (100, 48, 135),
		'after': (83, 135, 48),
	}

	TINT_PREFIX = "onion-tint-"

	def __init__(self, layer):
		self.layer = layer
		self.opacity = None
		self.visible = None
		self.tint = None

	def apply(self, img):
		# we do it this way to prevent unnecessarily cluttering the undo history.
		#
		# AFIAK there is not way to manipulate the history from a plug-in.

		if (self.opacity is not None) and (self.layer.opacity != self.opacity):
			self.layer.opacity = self.opacity

		if (self.visible is not None) and (self.layer.visible != self.visible):
			self.layer.visible = self.visible

		# Comment this out if you don't like layer tinting
		self._apply_tint(img)

	def _create_tint_layer(self, img, name, color):
		# Note: tint layer must be RGBA to preseve alpha for underlying layers.
		# layer mode: addition
		tint_layer = pdb.gimp_layer_new(img, img.width, img.height, 1, name, 100, 7)
		pdb.gimp_image_insert_layer(img, tint_layer, self.layer, 0)
		c = pdb.gimp_context_get_foreground()
		pdb.gimp_context_set_foreground(color)
		pdb.gimp_edit_fill(tint_layer, 0)
		pdb.gimp_context_set_foreground(c)

	def _apply_tint(self, img):
		if not hasattr(self.layer, 'layers'):
			return

		if self.tint is None:
			# If the whole freme is not currently visible, no need
			# to waste time doing anything.
			if self.visible:
				for layer in self.layer.layers:
					if self.TINT_PREFIX in layer.name:
						layer.visible = False
						break
		elif self.tint == "clean":
			# This will actually remove the tint layer compared to
			# just making it invisible. We use this when we want a
			# clean image.
			for layer in self.layer.layers:
				if self.TINT_PREFIX in layer.name:
					pdb.gimp_image_remove_layer(img, layer)
		else:
			tint_layer = pdb.gimp_image_get_layer_by_name(img, "onion-tint-%s" % (self.tint,))

			if tint_layer is not None:
				# If a tint layer already exists somewhere in the image, we just
				# move it here. It's much faster than creating a new layer from scratch
				# and we only ever need two tint layers to exist simultaneously.
				pdb.gimp_image_reorder_item(img, tint_layer, self.layer, 0)
				tint_layer.visible = True
			else:
				self._create_tint_layer(img, "onion-tint-%s" % (self.tint,),
						self.TINT_COLORS[self.tint])

def get_frames(img):
	for layer in img.layers:
		if layer.name.startswith('['):
			continue

		yield Frame(layer)

def sanitize_name(name):
	# if layer mask is active when a function is invoked,
	# the active layer name has " mask" appended.
	name = re.sub(r' mask$', '', name)
	return re.sub(r'\d+', '', name)

def show_all(img, act_layer):
	img.undo_group_start()

	for frame in get_frames(img):
		frame.opacity = 100.
		frame.visible = True
		frame.tint = "clean"
		frame.apply(img)

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

				if c > 0:
					frames[k].tint = "after"
				else:
					frames[k].tint = "before"

		frames[i].opacity = 100.
		frames[i].visible = True
		frames[i].tint = None

		img.undo_group_start()

		for frame in frames:
			frame.apply(img)

		img.undo_group_end()

		# Use some heuristic to change the active layer as well.
		if hasattr(frames[i].layer, 'layers'):
			n = sanitize_name(act_layer.name)

			for layer in frames[i].layer.layers:
				if sanitize_name(layer.name) == n:
					img.active_layer = layer
					if layer.mask is not None:
						layer.edit_mask = False
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

def onion_copy_layer(img, act_layer):
	frames = list(get_frames(img))

	# If no frames were found, do nothing.
	N = len(frames)
	if N < 1:
		return

	# Find the location of the layer to copy in the current frame.
	act_loc = -1
	for frame in frames:
		if not hasattr(frame.layer, 'layers'):
			continue

		for i, layer in enumerate(frame.layer.layers):
			if layer.name == act_layer.name:
				act_loc = i
				break

		if act_loc != -1:
			break

	act_name = sanitize_name(act_layer.name)

	img.undo_group_start()

	for frame in frames:

		# If the frame is not a layer group, do nothing
		if not hasattr(frame.layer, 'layers'):
			continue

		for layer in frame.layer.layers:
			if sanitize_name(layer.name) == act_name:
				# This frame already has a copy. Just copy over
				# visibility and opacity.
				layer.visible = act_layer.visible
				layer.opacity = act_layer.opacity
				break
		else:
			# This frame doesn't have a copy. Make one.
			layer = act_layer.copy()

			# Copy over frame number
			g = re.search(r'(\d+)$', frame.layer.name)
			if g is not None:
				layer.name = sanitize_name(act_layer.name) + g.group(1)

			pdb.gimp_image_insert_layer(img, layer, frame.layer, act_loc)

	img.undo_group_end()


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

register(
	"python_fu_onion_copy_layer",
	"Copy layer to all frames",
	"Copy active layer to all frames. If layer already exists in that frame, copy opacity and visibility.",
	"Tomaz Solc",
	"GPLv3+",
	"2017",
	"<Image>/Filters/Animation/Onion layers/Copy layer",
	"*",
	[],
	[],
	onion_copy_layer)

main()
