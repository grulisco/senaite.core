# -*- coding: utf-8 -*-
#
# This file is part of SENAITE.CORE
#
# Copyright 2018 by it's authors.
# Some rights reserved. See LICENSE.rst, CONTRIBUTORS.rst.

import itertools
import re

import transaction
from bika.lims import api
from bika.lims import logger
from bika.lims.alphanumber import Alphanumber
from bika.lims.alphanumber import to_alpha
from bika.lims.browser.fields.uidreferencefield import \
    get_backreferences as get_backuidreferences
from bika.lims.interfaces import IAnalysisRequest
from bika.lims.interfaces import IAnalysisRequestPartition
from bika.lims.interfaces import IAnalysisRequestRetest
from bika.lims.interfaces import IIdServer
from bika.lims.numbergenerator import INumberGenerator
from DateTime import DateTime
from Products.ATContentTypes.utils import DT2dt
from zope.component import getAdapters
from zope.component import getUtility

AR_TYPES = [
    "AnalysisRequest",
    "AnalysisRequestRetest",
    "AnalysisRequestPartition",
]


def get_objects_in_sequence(brain_or_object, ctype, cref):
    """Return a list of items
    """
    obj = api.get_object(brain_or_object)
    if ctype == "backreference":
        return get_backreferences(obj, cref)
    if ctype == "contained":
        return get_contained_items(obj, cref)
    raise ValueError("Reference value is mandatory for sequence type counter")


def get_backreferences(obj, relationship):
    """Returns the backreferences
    """
    refs = get_backuidreferences(obj, relationship)

    # TODO remove after all ReferenceField get ported to UIDReferenceField
    # At this moment, there are still some content types that are using the
    # ReferenceField, so we need to fallback to traditional getBackReferences
    # for these cases.
    if not refs:
        refs = obj.getBackReferences(relationship)

    return refs


def get_contained_items(obj, spec):
    """Returns a list of (id, subobject) tuples of the current context.
    If 'spec' is specified, returns only objects whose meta_type match 'spec'
    """
    return obj.objectItems(spec)


def get_type_id(context, **kw):
    """Returns the type id for the context passed in
    """
    portal_type = kw.get("portal_type", None)
    if portal_type:
        return portal_type

    # Override by provided marker interface
    if IAnalysisRequestPartition.providedBy(context):
        return "AnalysisRequestPartition"
    elif IAnalysisRequestRetest.providedBy(context):
        return "AnalysisRequestRetest"

    return api.get_portal_type(context)


def get_suffix(id, regex="-[A-Z]{1}[0-9]{1,2}$"):
    """Get the suffix of the ID, e.g. '-R01' or '-P05'

    The current regex determines a pattern of a single uppercase character with
    at most 2 numbers following at the end of the ID as the suffix.
    """
    parts = re.findall(regex, id)
    if not parts:
        return ""
    return parts[0]


def strip_suffix(id):
    """Split off any suffix from ID

    This mimics the old behavior of the Sample ID.
    """
    suffix = get_suffix(id)
    if not suffix:
        return id
    return re.split(suffix, id)[0]


def get_retest_count(context, default=0):
    """Returns the number of retests of this AR
    """
    if not is_ar(context):
        return default

    invalidated = context.getInvalidated()

    count = 0
    while invalidated:
        count += 1
        invalidated = invalidated.getInvalidated()

    return count


def get_partition_count(context, default=0):
    """Returns the number of partitions of this AR
    """
    if not is_ar(context):
        return default

    parent = context.getParentAnalysisRequest()

    if not parent:
        return default

    return len(parent.getDescendants())


def is_ar(context):
    """Checks if the context is an AR
    """
    return IAnalysisRequest.providedBy(context)


def get_config(context, **kw):
    """Fetch the config dict from the Bika Setup for the given portal_type
    """
    # get the ID formatting config
    config_map = api.get_bika_setup().getIDFormatting()

    # allow portal_type override
    portal_type = get_type_id(context, **kw)

    # check if we have a config for the given portal_type
    for config in config_map:
        if config['portal_type'].lower() == portal_type.lower():
            return config

    # return a default config
    default_config = {
        'form': '%s-{seq}' % portal_type.lower(),
        'sequence_type': 'generated',
        'prefix': '%s' % portal_type.lower(),
    }
    return default_config


def get_variables(context, **kw):
    """Prepares a dictionary of key->value pairs usable for ID formatting
    """
    # allow portal_type override
    portal_type = get_type_id(context, **kw)

    # The variables map hold the values that might get into the constructed id
    variables = {
        "context": context,
        "id": api.get_id(context),
        "portal_type": portal_type,
        "year": get_current_year(),
        "parent": api.get_parent(context),
        "seq": 0,
        "alpha": Alphanumber(0),
    }

    # Augment the variables map depending on the portal type
    if portal_type in AR_TYPES:
        now = DateTime()
        sampling_date = context.getSamplingDate()
        sampling_date = sampling_date and DT2dt(sampling_date) or DT2dt(now)
        date_sampled = context.getDateSampled()
        date_sampled = date_sampled and DT2dt(date_sampled) or DT2dt(now)
        test_count = 1

        variables.update({
            "clientId": context.getClientID(),
            "dateSampled": date_sampled,
            "samplingDate": sampling_date,
            "sampleType": context.getSampleType().getPrefix(),
            "test_count": test_count
        })

        # Partition
        if portal_type == "AnalysisRequestPartition":
            parent_ar = context.getParentAnalysisRequest()
            parent_ar_id = api.get_id(parent_ar)
            parent_base_id = strip_suffix(parent_ar_id)
            partition_count = get_partition_count(context)
            variables.update({
                "parent_analysisrequest": parent_ar,
                "parent_ar_id": parent_ar_id,
                "parent_base_id": parent_base_id,
                "partition_count": partition_count,
            })

        # Retest
        elif portal_type == "AnalysisRequestRetest":
            # Note: we use "parent" instead of "invalidated" for simplicity
            parent_ar = context.getInvalidated()
            parent_ar_id = api.get_id(parent_ar)
            parent_base_id = strip_suffix(parent_ar_id)
            # keep the full ID if the retracted AR is a partition
            if context.isPartition():
                parent_base_id = parent_ar_id
            retest_count = get_retest_count(context)
            test_count = test_count + retest_count
            variables.update({
                "parent_analysisrequest": parent_ar,
                "parent_ar_id": parent_ar_id,
                "parent_base_id": parent_base_id,
                "retest_count": retest_count,
                "test_count": test_count,
            })

    elif portal_type == "ARReport":
        variables.update({
            "clientId": context.aq_parent.getClientID(),
        })

    return variables


def split(string, separator="-"):
    """ split a string on the given separator
    """
    if not isinstance(string, basestring):
        return []
    return string.split(separator)


def to_int(thing, default=0):
    """Convert a thing to an integer
    """
    try:
        return int(thing)
    except (TypeError, ValueError):
        return default


def slice(string, separator="-", start=None, end=None):
    """Slice out a segment of a string, which is splitted on both the wildcards
    and the separator passed in, if any
    """
    # split by wildcards/keywords first
    # AR-{sampleType}-{parentId}{alpha:3a2d}
    segments = filter(None, re.split('(\{.+?\})', string))
    # ['AR-', '{sampleType}', '-', '{parentId}', '{alpha:3a2d}']
    if separator:
        # Keep track of singleton separators as empties
        # We need to do this to prevent duplicates later, when splitting
        segments = map(lambda seg: seg!=separator and seg or "", segments)
        # ['AR-', '{sampleType}', '', '{parentId}', '{alpha:3a2d}']
        # Split each segment at the given separator
        segments = map(lambda seg: split(seg, separator), segments)
        # [['AR', ''], ['{sampleType}'], [''], ['{parentId}'], ['{alpha:3a2d}']]
        # Flatten the list
        segments = list(itertools.chain.from_iterable(segments))
        # ['AR', '', '{sampleType}', '', '{parentId}', '{alpha:3a2d}']
        # And replace empties with separator
        segments = map(lambda seg: seg!="" and seg or separator, segments)
        # ['AR', '-', '{sampleType}', '-', '{parentId}', '{alpha:3a2d}']

    # Get the start and end positions from the segments without separator
    cleaned_segments = filter(lambda seg: seg!=separator, segments)
    start_pos = to_int(start, 0)
    # Note "end" is not a position, but the number of elements to join!
    end_pos = to_int(end, len(cleaned_segments) - start_pos) + start_pos - 1

    # Map the positions against the segments with separator
    start = segments.index(cleaned_segments[start_pos])
    end = segments.index(cleaned_segments[end_pos]) + 1

    # Return all segments joined
    sliced_parts = segments[start:end]
    return "".join(sliced_parts)


def get_current_year():
    """Returns the current year as a two digit string
    """
    return DateTime().strftime("%Y")[2:]


def search_by_prefix(portal_type, prefix):
    """Returns brains which share the same portal_type and ID prefix
    """
    catalog = api.get_tool("uid_catalog")
    brains = catalog({"portal_type": portal_type})
    # Filter brains with the same ID prefix
    return filter(lambda brain: api.get_id(brain).startswith(prefix), brains)


def get_ids_with_prefix(portal_type, prefix):
    """Return a list of ids sharing the same portal type and prefix
    """
    brains = search_by_prefix(portal_type, prefix)
    ids = map(api.get_id, brains)
    return ids


def make_storage_key(portal_type, prefix=None):
    """Make a storage (dict-) key for the number generator
    """
    key = portal_type.lower()
    if prefix:
        key = "{}-{}".format(key, prefix)
    return key


def get_seq_number_from_id(id, id_template, prefix, **kw):
    """Return the sequence number of the given ID
    """
    separator = kw.get("separator", "-")
    postfix = id.replace(prefix, "").strip(separator)
    postfix_segments = postfix.split(separator)
    seq_number = 0
    possible_seq_nums = filter(lambda n: n.isalnum(), postfix_segments)
    if possible_seq_nums:
        seq_number = possible_seq_nums[-1]

    # Check if this id has to be expressed as an alphanumeric number
    seq_number = get_alpha_or_number(seq_number, id_template)
    seq_number = to_int(seq_number)
    return seq_number


def get_alpha_or_number(number, template):
    """Returns an Alphanumber that represents the number passed in, expressed
    as defined in the template. Otherwise, returns the number
    """
    match = re.match(r".*\{alpha:(\d+a\d+d)\}$", template.strip())
    if match and match.groups():
        format = match.groups()[0]
        return to_alpha(number, format)
    return number


def get_counted_number(context, config, variables, **kw):
    """Compute the number for the sequence type "Counter"
    """
    # This "context" is defined by the user in the Setup and can be actually
    # anything. However, we assume it is something like "sample" or similar
    ctx = config.get("context")

    # get object behind the context name (falls back to the current context)
    obj = variables.get(ctx, context)

    # get the counter type, which is either "backreference" or "contained"
    counter_type = config.get("counter_type")

    # the counter reference is either the "relationship" for
    # "backreference" or the meta type for contained objects
    counter_reference = config.get("counter_reference")

    # This should be a list of existing items, including the current context
    # object
    seq_items = get_objects_in_sequence(obj, counter_type, counter_reference)

    number = len(seq_items)
    return number


def get_generated_number(context, config, variables, **kw):
    """Generate a new persistent number with the number generator for the
    sequence type "Generated"
    """
    # separator where to split the ID
    separator = kw.get('separator', '-')

    # allow portal_type override
    portal_type = get_type_id(context, **kw)

    # The ID format for string interpolation, e.g. WS-{seq:03d}
    id_template = config.get("form", "")

    # The split length defines where the key is splitted from the value
    split_length = config.get("split_length", 1)

    # The prefix template is the static part of the ID
    prefix_template = slice(id_template, separator=separator, end=split_length)

    # get the number generator
    number_generator = getUtility(INumberGenerator)

    # generate the key for the number generator storage
    prefix = prefix_template.format(**variables)

    # normalize out any unicode characters like Ö, É, etc. from the prefix
    prefix = api.normalize_filename(prefix)

    # The key used for the storage
    key = make_storage_key(portal_type, prefix)

    # Handle flushed storage
    if key not in number_generator:
        max_num = 0
        existing = get_ids_with_prefix(portal_type, prefix)
        numbers = map(lambda id: get_seq_number_from_id(id, id_template, prefix), existing)
        # figure out the highest number in the sequence
        if numbers:
            max_num = max(numbers)
        # set the number generator
        logger.info("*** SEEDING Prefix '{}' to {}".format(prefix, max_num))
        number_generator.set_number(key, max_num)

    if not kw.get("dry_run", False):
        # Generate a new number
        # NOTE Even when the number exceeds the given ID sequence format,
        #      it will overflow gracefully, e.g.
        #      >>> {sampleId}-R{seq:03d}'.format(sampleId="Water", seq=999999)
        #      'Water-R999999‘
        number = number_generator.generate_number(key=key)
    else:
        # => This allows us to "preview" the next generated ID in the UI
        # TODO Show the user the next generated number somewhere in the UI
        number = number_generator.get(key, 1)

    # Return an int or Alphanumber
    return get_alpha_or_number(number, id_template)


def generateUniqueId(context, **kw):
    """ Generate pretty content IDs.
    """

    # get the config for this portal type from the system setup
    config = get_config(context, **kw)

    # get the variables map for later string interpolation
    variables = get_variables(context, **kw)

    # The new generate sequence number
    number = 0

    # get the sequence type from the global config
    sequence_type = config.get("sequence_type", "generated")

    # Sequence Type is "Counter", so we use the length of the backreferences or
    # contained objects of the evaluated "context" defined in the config
    if sequence_type in ["counter"]:
        number = get_counted_number(context, config, variables, **kw)

    # Sequence Type is "Generated", so the ID is constructed according to the
    # configured split length
    if sequence_type in ["generated"]:
        number = get_generated_number(context, config, variables, **kw)

    # store the new sequence number to the variables map for str interpolation
    if isinstance(number, Alphanumber):
        variables["alpha"] = number
    variables["seq"] = to_int(number)

    # The ID formatting template from user config, e.g. {sampleId}-R{seq:02d}
    id_template = config.get("form", "")

    # Interpolate the ID template
    try:
        new_id = id_template.format(**variables)
    except KeyError, e:
        logger.error('KeyError: {} not in id_template {}'.format(
            e, id_template))
        raise
    normalized_id = api.normalize_filename(new_id)
    logger.info("generateUniqueId: {}".format(normalized_id))

    return normalized_id


def renameAfterCreation(obj):
    """Rename the content after it was created/added
    """
    # Check if the _bika_id was already set
    bika_id = getattr(obj, "_bika_id", None)
    if bika_id is not None:
        return bika_id
    # Can't rename without a subtransaction commit when using portal_factory
    transaction.savepoint(optimistic=True)
    # The id returned should be normalized already
    new_id = None
    # Checking if an adapter exists for this content type. If yes, we will
    # get new_id from adapter.
    for name, adapter in getAdapters((obj, ), IIdServer):
        if new_id:
            logger.warn(('More than one ID Generator Adapter found for'
                         'content type -> %s') % obj.portal_type)
        new_id = adapter.generate_id(obj.portal_type)
    if not new_id:
        new_id = generateUniqueId(obj)

    # TODO: This is a naive check just in current folder
    # -> this should check globally for duplicate objects with same prefix
    # N.B. a check like `search_by_prefix` each time would probably slow things
    # down too much!
    # -> A solution could be to store all IDs with a certain prefix in a storage
    parent = api.get_parent(obj)
    if new_id in parent.objectIds():
        # XXX We could do the check in a `while` loop and generate a new one.
        raise KeyError("The ID {} is already taken in the path {}".format(
            new_id, api.get_path(parent)))
    # rename the object to the new id
    parent.manage_renameObject(obj.id, new_id)

    return new_id
