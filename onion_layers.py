#!/usr/bin/env python
import re
import fcntl
from contextlib import contextmanager
import os

NEXT_PREV_OPACITY = 25.

DEFAULT_CONTEXTS = [
	[ None, 100., None ],
	[ NEXT_PREV_OPACITY, 100., NEXT_PREV_OPACITY ],
	[ None, 100., NEXT_PREV_OPACITY ],
	[ NEXT_PREV_OPACITY, 100., None ],
]

# This is a bit ugly, but if you press keyboard shortcuts faster than the
# functions execute, you end up with two instances running in parallel. This
# leads to annoying pop-ups with  "Plug-In 'up, auto, tint' left image undo in
# inconsistent state, closing open undo groups.".
#
# We can't use the usual threading.Lock since each function call runs in a
# separate interpreter process that is forked by GIMP.
#
# So we do our own file locking here with fcntl. This bit is the only thing
# that is incompatible with Windows, so if you're looking to fix that, replace
# flocked() with a similar mechanism that works there and submit a pull
# request.

LOCK_DIR = os.environ.get('XDG_CACHE_HOME', os.path.join(os.environ['HOME'], '.cache'))
LOCK_FILE = os.path.join(LOCK_DIR, 'gimp-plugin-onion-layers-lock')

@contextmanager
def flocked():
	with open(LOCK_FILE, "w") as fd:
		try:
			fcntl.flock(fd, fcntl.LOCK_EX)
			yield
		finally:
			fcntl.flock(fd, fcntl.LOCK_UN)

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

	@classmethod
	def clear_tints(cls, img):
		for tint in cls.TINT_COLORS.keys():
			tint_layer = pdb.gimp_image_get_layer_by_name(img, cls.TINT_PREFIX + tint)
			if tint_layer is not None:
				tint_layer.visible = False

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
			return
		elif self.tint == "clean":
			# This will actually remove the tint layer compared to
			# just making it invisible. We use this when we want a
			# clean image.
			for layer in self.layer.layers:
				if self.TINT_PREFIX in layer.name:
					pdb.gimp_image_remove_layer(img, layer)
		else:
			tint_layer = pdb.gimp_image_get_layer_by_name(img, self.TINT_PREFIX + self.tint)

			if tint_layer is not None:
				# If a tint layer already exists somewhere in the image, we just
				# move it here. It's much faster than creating a new layer from scratch
				# and we only ever need two tint layers to exist simultaneously.
				pdb.gimp_image_reorder_item(img, tint_layer, self.layer, 0)
				tint_layer.visible = True
			else:
				self._create_tint_layer(img, self.TINT_PREFIX + self.tint,
						self.TINT_COLORS[self.tint])

def get_frames(img):
	for layer in img.layers:
		if layer.name.startswith('['):
			continue

		yield Frame(layer)

class NumberedName(object):
	def __init__(self, name, num=None, width=None, is_mask=False):
		self.name = name
		self.num = num
		self.width = width
		self.is_mask = is_mask

	@classmethod
	def from_layer_name(cls, name):
		# if layer mask is active when a function is invoked,
		# the active layer name has " mask" appended.
		name_nomask = re.sub(r' mask$', '', name)

		is_mask = (name_nomask != name)

		g = re.search(r'(\d+)$', name_nomask)
		if g:
			num = int(g.group(1))
			width = len(g.group(1))
		else:
			num = None
			width = None

		name_nonum = re.sub(r'\d+$', '', name_nomask)

		return cls(name_nonum, num, width, is_mask)

	def to_string(self):
		if self.num is None:
			return self.name
		else:
			fmt = "%s%0" + str(self.width) + "d"
			return fmt % (self.name, self.num)

	def __repr__(self):
		return "NumberedName(name=%r, num=%r, width=%r, is_mask=%r)" % (
				self.name, self.num, self.width, self.is_mask)

def sanitize_name(name):
	return NumberedName.from_layer_name(name).name

def show_all(img, act_layer):
	img.undo_group_start()

	for frame in get_frames(img):
		frame.opacity = 100.
		frame.visible = True
		frame.tint = "clean"
		frame.apply(img)

	img.undo_group_end()

def onion(*args, **kwargs):
	with flocked():
		return onion_unsafe(*args, **kwargs)

def onion_unsafe(img, act_layer, inc, context=None, dryrun=False, do_tint=False):

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

	# If no visible frame was found, show first frame.
	if i is None:
		i = 0

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
				opacity = frames[k].layer.opacity
				# Since we're detecting the current frame
				# based on 100% opacity, it doesn't make
				# sense that any context frames would have
				# 100% opacity as well.
				#
				# This typically happens when you do
				# "up-ctx-auto" after "show-all"
				if (c != 0) and (opacity >= 99.):
					opacity = 99.

				context[j] = opacity

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

				if do_tint:
					if c < 0:
						frames[k].tint = "after"
					else:
						frames[k].tint = "before"

		frames[i].opacity = 100.
		frames[i].visible = True
		frames[i].tint = None

		img.undo_group_start()

		Frame.clear_tints(img)
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

def onion_up_ctx_auto_tint(img, layer):
	onion(img, layer, -1, None, do_tint=True)

def onion_down_ctx_auto_tint(img, layer):
	onion(img, layer, 1, None, do_tint=True)

def cycle_context(img, layer, do_tint=False):

	context = onion(img, layer, 0, dryrun=True)

	try:
		current_default = DEFAULT_CONTEXTS.index(context)
	except ValueError:
		current_default = -1

	current_default = (current_default + 1) % len(DEFAULT_CONTEXTS)

	onion(img, layer, 0, DEFAULT_CONTEXTS[current_default], do_tint=do_tint)

def onion_cycle_context(img, layer):
	cycle_context(img, layer, do_tint=False)

def onion_cycle_context_tint(img, layer):
	cycle_context(img, layer, do_tint=True)

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

def renumber_frames(img):

	frames = list(get_frames(img))

	def update_layer_name(layer, num, temp):
		nn = NumberedName.from_layer_name(layer.name)

		if nn.num is not None:
			if temp:
				nn.name = "temp-" + nn.name
			else:
				nn.name = re.sub(r'^temp-', '', nn.name)
			nn.num = num

			layer.name = nn.to_string()

	def do_renumber(temp):

		for n, frame in enumerate(frames):

			m = len(frames) - n

			update_layer_name(frame.layer, m, temp)

			if hasattr(frame.layer, 'layers'):
				for layer in frame.layer.layers:
					update_layer_name(layer, m, temp)


	do_renumber(temp=True)
	do_renumber(temp=False)

def onion_add_frame(img, act_layer):
	frames = list(get_frames(img))

	# remember current frame context
	context = onion(img, act_layer, 0, dryrun=True)

	# If no frames were found, do nothing.
	N = len(frames)
	if N < 1:
		return

	# Get the top level layer (frame) from the currently active layer
	act_frame = act_layer
	while act_frame.parent is not None:
		act_frame = act_frame.parent

	# This only works if frames are layer groups
	if not hasattr(act_frame, 'layers'):
		return

	n = pdb.gimp_image_get_item_position(img, act_frame)

	new_frame_name = get_last_numbered_name(frames)
	new_frame_name.num += 1

	img.undo_group_start()

	# hide the frame we're copying so that the new frame will be detected
	# as currently visible.
	act_frame.visible = False

	new_frame = pdb.gimp_layer_group_new(img)
	new_frame.name = new_frame_name.to_string()
	pdb.gimp_image_insert_layer(img, new_frame, None, n)

	for n, layer in enumerate(act_frame.layers):
		name = NumberedName.from_layer_name(layer.name)

		if name.num is None:
			continue
		name.num = 99

		new_layer = pdb.gimp_layer_new(img, img.width, img.height, 1,
				name.to_string(), layer.opacity, 0)

		pdb.gimp_image_insert_layer(img, new_layer, new_frame, n)

	renumber_frames(img)

	# quick dirty check if tinting was used
	do_tint = (pdb.gimp_image_get_layer_by_name(img, "onion-tint-after") is not None)

	onion(img, act_layer, 0, context, do_tint=do_tint)

	img.undo_group_end()

def onion_enable_disable_frame(img, act_layer, enable):
	# Get the top level layer (frame) from the currently active layer
	act_frame = act_layer
	while act_frame.parent is not None:
		act_frame = act_frame.parent

	img.undo_group_start()

	if enable:
		act_frame.name = act_frame.name.replace('[', '').replace(']', '')
	else:
		act_frame.name = '[' + act_frame.name + ']'

	img.undo_group_end()

def onion_enable_frame(img, act_layer):
	onion_enable_disable_frame(img, act_layer, True)

def onion_disable_frame(img, act_layer):
	onion_enable_disable_frame(img, act_layer, False)

# Gets the highest numbered frame, or a sane default
# if no numbered frame was found.
def get_last_numbered_name(frames):
	last_name = None

	for frame in frames:
		name = NumberedName.from_layer_name(frame.layer.name)
		if name.num is not None:
			if last_name is None:
				last_name = name
			else:
				if name.num > last_name.num:
					last_name = name

	if last_name is None:
		last_name = NumberedName('frame', 0, 4)

	return last_name

def onion_convert_to_groups(img, act_layer):
	frames = list(get_frames(img))

	# If no frames were found, do nothing.
	N = len(frames)
	if N < 1:
		return

	# We need to generate some frame names that
	# are not used elsewhere (we'll renumber later)
	new_frame_name = get_last_numbered_name(frames)
	new_frame_name.num += 1

	layer_name = 'imported'

	img.undo_group_start()

	has_new_frames = False
	for n, frame in enumerate(frames):
		# If the frame is layer and not a group,
		# create a new group and put it in.
		if not hasattr(frame.layer, 'layers'):
			new_frame = pdb.gimp_layer_group_new(img)
			new_frame.name = new_frame_name.to_string()

			pdb.gimp_image_insert_layer(img, new_frame, None, n)

			pdb.gimp_image_reorder_item(img, frame.layer, new_frame, 0)

			name = NumberedName(layer_name, new_frame_name.num, new_frame_name.width)
			frame.layer.name = name.to_string()

			has_new_frames = True
			new_frame_name.num += 1

	# Renumber frames if any new ones have been added
	if has_new_frames:
		renumber_frames(img)

	img.undo_group_end()


def start():
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
		"<Image>/Filters/Animation/Onion layers/up, auto",
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
		"<Image>/Filters/Animation/Onion layers/down, auto",
		"*",
		[],
		[],
		onion_down_ctx_auto)

	register(
		"python_fu_onion_up_ctx_auto_tint",
		"Onion up, auto context, tint",
		"Move one onion layer up, retain current context. Next layer is shown with a green tint, previous layer is shown with a purple tint.",
		"Tomaz Solc",
		"GPLv3+",
		"2017",
		"<Image>/Filters/Animation/Onion layers/up, auto, tint",
		"*",
		[],
		[],
		onion_up_ctx_auto_tint)

	register(
		"python_fu_onion_down_ctx_auto_tint",
		"Onion down, auto context, tint",
		"Move one onion layer down, retain current context. Next layer is shown with a green tint, previous layer is shown with a purple tint.",
		"Tomaz Solc",
		"GPLv3+",
		"2017",
		"<Image>/Filters/Animation/Onion layers/down, auto, tint",
		"*",
		[],
		[],
		onion_down_ctx_auto_tint)

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
		"python_fu_onion_cycle_ctx_tint",
		"Cycle through frame contexts, with tinting enabled.",
		"Cycle through no, prev, next, prev/next contexts. Next layer is shown with a green tint, previous layer is shown with a purple tint.",
		"Tomaz Solc",
		"GPLv3+",
		"2017",
		"<Image>/Filters/Animation/Onion layers/cycle context, tint",
		"*",
		[],
		[],
		onion_cycle_context_tint)

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

	register(
		"python_fu_onion_add_frame",
		"Add a frame above current one",
		"Add a frame above current one, copying all the layers.",
		"Tomaz Solc",
		"GPLv3+",
		"2017",
		"<Image>/Filters/Animation/Onion layers/Add frame",
		"*",
		[],
		[],
		onion_add_frame)

	register(
		"python_fu_onion_enable_frame",
		"Make the current frame a cel frame",
		"Removes square brackets around the name of the currently active frame.",
		"Tomaz Solc",
		"GPLv3+",
		"2019",
		"<Image>/Filters/Animation/Onion layers/Enable frame",
		"*",
		[],
		[],
		onion_enable_frame)

	register(
		"python_fu_onion_disable_frame",
		"Make the current frame a background frame",
		"Puts square brackets around the name of the currently active frame.",
		"Tomaz Solc",
		"GPLv3+",
		"2019",
		"<Image>/Filters/Animation/Onion layers/Disable frame",
		"*",
		[],
		[],
		onion_disable_frame)

	register(
		"python_fu_onion_convert_to_groups",
		"Convert bare layers into groups",
		"Puts each layer on the top level into its own layer group.",
		"Tomaz Solc",
		"GPLv3+",
		"2019",
		"<Image>/Filters/Animation/Onion layers/Convert to groups",
		"*",
		[],
		[],
		onion_convert_to_groups)

	main()

if __name__ == "__main__":
	from gimpfu import *

	start()
