# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import itertools


def dnf_convert(dep_struct):
	"""
	Convert dep_struct to disjunctive normal form (DNF), where dep_struct
	is either a conjunction or disjunction of the form produced by
	use_reduce(opconvert=True).
	"""
	# Normalize input to have a top-level conjunction.
	if isinstance(dep_struct, list):
		if dep_struct and dep_struct[0] == '||':
			dep_struct = [dep_struct]
	else:
		dep_struct = [dep_struct]

	conjunction = []
	disjunctions = []

	for x in dep_struct:
		if isinstance (x, list):
			assert x and x[0] == '||', \
				'Normalization error, nested conjunction found in %s' % (dep_struct,)
			if any(isinstance(element, list) for element in x):
				x_dnf = ['||']
				for element in x[1:]:
					if isinstance(element, list):
						# Due to normalization, a disjunction must not be
						# nested directly in another disjunction, so this
						# must be a conjunction.
						assert element, 'Normalization error, empty conjunction found in %s' % (x,)
						assert element[0] != '||', \
							'Normalization error, nested disjunction found in %s' % (x,)
						element = dnf_convert(element)
						if contains_disjunction(element):
							assert (len(element) == 1 and
								element[0] and element[0][0] == '||'), \
								'Normalization error, expected single disjunction in %s' % (element,)
							x_dnf.extend(element[0][1:])
						else:
							x_dnf.append(element)
					else:
						x_dnf.append(element)
				x = x_dnf
			disjunctions.append(x)
		else:
			conjunction.append(x)

	if disjunctions and (conjunction or len(disjunctions) > 1):
		dnf_form = ['||']
		for x in itertools.product(*[x[1:] for x in disjunctions]):
			normalized = conjunction[:]
			for element in x:
				if isinstance(element, list):
					normalized.extend(element)
				else:
					normalized.append(element)
			dnf_form.append(normalized)
		result = [dnf_form]
	else:
		result = conjunction + disjunctions

	return result


def contains_disjunction(dep_struct):
	"""
	Search for a disjunction contained in dep_struct, where dep_struct
	is either a conjunction or disjunction of the form produced by
	use_reduce(opconvert=True). If dep_struct is a disjunction, then
	this only returns True if there is a nested disjunction. Due to
	normalization, recursion is only needed when dep_struct is a
	disjunction containing a conjunction. If dep_struct is a conjunction,
	then it is assumed that normalization has elevated any nested
	disjunctions to the top-level.
	"""
	is_disjunction = dep_struct and dep_struct[0] == '||'
	for x in dep_struct:
		if isinstance(x, list):
			assert x, 'Normalization error, empty conjunction found in %s' % (dep_struct,)
			if x[0] == '||':
				return True
			if is_disjunction and contains_disjunction(x):
				return True
	return False
