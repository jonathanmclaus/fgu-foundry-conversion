#!/usr/bin/env python3.8

# This script converts calendar entries in FGU to a format compatible with the
# Simple Calendar module for Foundry. Entry IDs are integer indices represented
# as hexadecimal strings.

# The monthDisplay value in an FGU note is deliberately excluded, as this value
# is not used and computing it requires parsing the text in an FGU entry.

# Example input under db.xml::root/calendar/log:
# <id-00134>
#     <public />
#     <day type="number">9</day>
#     <gmlogentry type="formattedtext">
#         <p />
#     </gmlogentry>
#     <logentry type="formattedtext">
#         <p>Returned to Elesomare. Spoke with Sharvaros who matched Wrenn's and Karina's description of the attackers to a Telgrodradt. Left Karina in Sharvaros' company.</p>
#     </logentry>
#     <month type="number">1</month>
#     <name type="string">9th Abadius, 4721 </name>
#     <year type="number">4721</year>
# </id-00134>

# Example output under settings.db::foundryvtt-simple-calendar.notes/value:
# {
#     "title": "Journal",
#     "content": "<p>Returned to Elesomare. Spoke with Sharvaros who matched Wrenn's and Karina's description of the attackers to a Telgrodradt. Left Karina in Sharvaros' company.</p>",
#     "author": "zph8yxjDa80f9VnL",
#     "year": 4721,
#     "month": 1,
#     "day": 9,
#     "playerVisible": true,
#     "id": "142f4260",
#     "repeats": 0,
#     "allDay": true,
#     "hour": 0,
#     "minute": 0,
#     "endDate": {
#         "year": 4721,
#         "month": 1,
#         "day": 9,
#         "hour": 0,
#         "minute": 0,
#         "seconds": 0
#     },
#     "order": 0,
#     "categories": [],
#     "remindUsers": []
# }

# Standard library imports:
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, FileType
from functools import partial
from itertools import chain
from json import dumps, loads
from operator import attrgetter, methodcaller
from os import path
from random import randrange
from shutil import copyfile
from xml.etree import ElementTree

# Third-party imports:
from boltons.dictutils import subdict
from toolz.functoolz import compose

# The ID of the FVTT settings entry where calendar notes are location.
CAL_SETTINGS = "foundryvtt-simple-calendar.notes"


def get_id():
    """
    Generates a random ID for a calendar entry, which is a hexadecimal string
    representing an unsigned 32-bit integer.
    """
    return "{0:08x}".format(randrange(0, 1 << 32))


def textify(element):
    """
    Converts an XML element to its textual representation, skipping the head
    and tail because those are not used for log entries in FGU.
    """
    # Combine each child element.
    return "".join(map(
        compose(
            # Remove the excesss whitespace around the tags.
            methodcaller("strip"),
            # Decode from the UTF-8 formatted data.
            methodcaller("decode"),
            # Look up the original text of each child.
            ElementTree.tostring,
        ),
        # Ignore empty elements, e.g. <p />.
        filter(attrgetter("text"), element),
    ))


def get_fvtt_entries(fgu_entry, public_title, private_title, author):
    """
    Converts an FGU calendar entry to FVTT entries, with an entry each for of
    the public and private portions of the entry that are not empty.
    """
    # Look up the elements for the time and convert them to integers.
    time = {
        element: int(fgu_entry.find(element).text)
        for element in ["year", "month", "day"]
    }

    # Use default values for intraday timestamps, as FGU does not support them.
    for key in ["hour", "minute"]:
        time[key] = 0

    # Create the shared portion of the entries, without the content.
    base_entry = {
        "author": author,
        "repeats": 0,
        "allDay": True,
        "categories": [],
        "remindUsers": [],
        "endDate": {
            "seconds": 0,
            **time,
        },
        **time,
    }

    # Convert the two types of entries.
    for is_public in (True, False):
        # Look up the relevant log entry.
        log = fgu_entry.find("logentry" if is_public else "gmlogentry")

        # Skip log entries without text.
        if not (content := textify(log)):
            continue

        # Output an entry for FVTT.
        yield {
            "id":            get_id(),
            "content":       content,
            "playerVisible": is_public,
            # Use the appropriate title.
            "title": public_title if is_public else private_title,
            # Place private entries beneath public ones.
            "priority": int(not is_public),
            # Include all common elements.
            **base_entry,
        }


def parse_args(args=None):
    # Construct the argument parser.
    parser = ArgumentParser(
        "Convert Calendar Entries",
        description="Convert calendar entries from FGU to FVTT.",
        formatter_class=ArgumentDefaultsHelpFormatter,
    )

    # Add the arguments.
    parser.add_argument(
        "--author",
        required=True,
        help="User ID to use for entries, e.g. zph8yxjDa80f9VnL"
    )
    parser.add_argument(
        "--public-title",
        default="Journal",
        help="The name to use for each public entry in the calendar"
    )
    parser.add_argument(
        "--private-title",
        default="Notes",
        help="The name to use for each private entry in the calendar"
    )
    parser.add_argument(
        "fgu",
        type=FileType(),
        help="Input database file for FGU, typically db.xml")
    parser.add_argument(
        "fvtt",
        type=FileType("r+"),
        help="Output settings file for FVTT, typically settings.db"
    )

    # Parse and output arguments.
    return parser.parse_args(args)


if __name__ == "__main__":
    # Parse the arguments.
    args = vars(parse_args())
    print(args)

    # Use an increment backup filename.
    index = 0

    # Decide on the location of the backup.
    while path.exists(f"{args['fvtt'].name}.bak.{index}"):
        index += 1

    # Back up the settings file prior to any modification.
    copyfile(args["fvtt"].name, f"{args['fvtt'].name}.bak.{index}")

    # Parse the db.xml file.
    fgu_db_tree = ElementTree.parse(args["fgu"])
    fgu_db_root = fgu_db_tree.getroot()

    # Collect the set of log entries.
    fgu_db_logs = list(filter(
        # Ignore the "public" child, which functions as an attribute.
        lambda child: child.tag != "public",
        # Iterate over the children underneath the logs in the calendar.
        fgu_db_root.find("./calendar/log"),
    ))

    # Parametrize the converter.
    converter = partial(
        get_fvtt_entries,
        **subdict(args, ["author", "public_title", "private_title"]),
    )

    # Get the entries for FVTT.
    fvtt_entries = list(chain.from_iterable(map(converter, fgu_db_logs)))
    print(dumps(fvtt_entries[50], indent=4))

    # Read the FVTT settings, which is in line-delimited JSON.
    for line_number, line in enumerate(lines := args["fvtt"].readlines()):
        # Find the relevant line for the calendar notes.
        if (payload := loads(line.strip()))["key"] == CAL_SETTINGS:
            # Exit the loop to reach the next step of processing.
            break
    else:
        # Exit due to failing to find the relevant setting.
        exit(f"Failed to find settings: {CAL_SETTINGS}")

    # Process the relevant entry.
    payload["value"] = dumps(fvtt_entries)

    # Modify the relevant line.
    lines[line_number] = dumps(payload) + "\n"

    # Overwrite the settings.
    args["fvtt"].seek(0)
    args["fvtt"].writelines(lines)
    args["fvtt"].truncate

    # Exit cleanly.
    exit()
