# -*- coding:utf-8 -*-

import copy
import itertools
import json
import os
import stat

try:
	import yaml
except ImportError:
	yaml = None


class ConfigError(Exception):
	"""Raised when a config file fails to load"""
	pass


def merge_config(base, head):
	"""
	Merge two JSON or YAML documents into a single object. Arrays are
	merged by extension. If dissimilar types are encountered, then the
	head value overwrites the base value.
	"""

	if isinstance(head, dict):
		if not isinstance(base, dict):
			return copy.deepcopy(head)

		result = {}
		for k in itertools.chain(head, base):
			try:
				result[k] = merge_config(base[k], head[k])
			except KeyError:
				try:
					result[k] = copy.deepcopy(head[k])
				except KeyError:
					result[k] = copy.deepcopy(base[k])

	elif isinstance(head, list):
		result = []
		if not isinstance(base, list):
			result.extend(copy.deepcopy(x) for x in head)
		else:
			if any(isinstance(x, (dict, list)) for x in itertools.chain(head, base)):
				# merge items with identical indexes
				for x, y in zip(base, head):
					if isinstance(x, (dict, list)):
						result.append(merge_config(x, y))
					else:
						# head overwrites base (preserving index)
						result.append(copy.deepcopy(y))
				# copy remaining items from the longer list
				if len(base) != len(head):
					if len(base) > len(head):
						result.extend(copy.deepcopy(x) for x in base[len(head):])
					else:
						result.extend(copy.deepcopy(x) for x in head[len(base):])
			else:
				result.extend(copy.deepcopy(x) for x in base)
				result.extend(copy.deepcopy(x) for x in head)

	else:
		result = copy.deepcopy(head)

	return result

def _yaml_load(filename):
	"""
	Load filename as YAML and return a dict. Raise ConfigError if
	it fails to load.
	"""
	if yaml is None:
		raise ImportError('Please install pyyaml in order to read yaml files')

	with open(filename, 'rt') as f:
		try:
			return yaml.safe_load(f)
		except yaml.parser.ParserError as e:
			raise ConfigError("{}: {}".format(filename, e))

def _json_load(filename):
	"""
	Load filename as JSON and return a dict. Raise ConfigError if
	it fails to load.
	"""
	with open(filename, 'rt') as f:
		try:
			return json.load(f) #nosec
		except ValueError as e:
			raise ConfigError("{}: {}".format(filename, e))

def iter_files(files_dirs):
	"""
	Iterate over nested file paths in lexical order.
	"""
	stack = list(reversed(files_dirs))
	while stack:
		location = stack.pop()
		try:
			st = os.stat(location)
		except FileNotFoundError:
			continue

		if stat.S_ISDIR(st.st_mode):
			stack.extend(os.path.join(location, x)
				for x in sorted(os.listdir(location), reverse=True))

		elif stat.S_ISREG(st.st_mode):
			yield location

def load_config(conf_dirs, file_extensions=None, valid_versions=None):
	"""
	Load JSON and/or YAML files from a directories, and merge them together
	into a single object.

	@param conf_dirs: ordered iterable of directories to load the config from
	@param file_extensions: Optional list of file extension types to load
	@param valid_versions: list of compatible file versions allowed
	@returns: the stacked config
	"""

	result = {}
	for filename in iter_files(conf_dirs):
		if file_extensions is not None and not filename.endswith(file_extensions):
			continue

		loaders = []
		extension = filename.rsplit('.', 1)[1]
		if extension in ['json']:
			loaders.append(_json_load)
		elif extension in ['yml', 'yaml']:
			loaders.append(_yaml_load)

		config = None
		exception = None
		for loader in loaders:
			try:
				config = loader(filename) or {}
			except ConfigError as e:
				exception = e
			else:
				break

		if config is None:
			print("Repoman.config.load_config(), Error loading file: %s"  % filename)
			print("   Aborting...")
			raise exception

		if config:
			if config['version'] not in valid_versions:
				raise ConfigError(
					"Invalid file version: %s in: %s\nPlease upgrade to "
					">=app-portage/repoman-%s, current valid API versions: %s"
					% (config['version'], filename,
						config['repoman_version'], valid_versions))
			result = merge_config(result, config)

	return result
