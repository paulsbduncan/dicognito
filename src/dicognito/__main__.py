"""\
Anonymize one or more DICOM files' headers (not pixel data).
"""
from __future__ import print_function
import sys
import argparse
import collections
import glob
import os.path
import logging
import pydicom

import dicognito
from dicognito.anonymizer import Anonymizer


def main(args=None):
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "sources",
        metavar="source",
        type=str,
        nargs="+",
        help="The directories or file globs (e.g. *.dcm) to anonymize. Directories "
        "will be recursed, and all files found within will be anonymized.",
    )
    parser.add_argument(
        "--id-prefix",
        "-p",
        default="",
        help="A short string prepended to each ID field, such as PatientID, "
        "AccessionNumber, and so on, to make it easier to identify anonymized "
        "studies. Longer prefixes reduce the number of available random "
        "characters in the ID and increase the chance of collisions with other "
        "IDs. May be combined with --id-suffix.",
    )
    parser.add_argument(
        "--id-suffix",
        "-s",
        default="",
        help="A short string appended to each ID field, such as PatientID, "
        "AccessionNumber, and so on, to make it easier to identify anonymized "
        "studies. Longer suffixes reduce the number of available random "
        "characters in the ID and increase the chance of collisions with other "
        "IDs. May be combined with --id-prefix.",
    )
    parser.add_argument(
        "--output-directory",
        "-o",
        action="store",
        type=str,
        help="Instead of anonymizing files in-place, write anonymized files to "
        "OUTPUT_DIRECTORY, which will be created if necessary",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Reduce the verbosity of output. Suppresses summary of anonymized studies.",
    )
    parser.add_argument(
        "--log-level",
        action="store",
        metavar="LEVEL",
        default="WARNING",
        help="Set the log level. May be one of DEBUG, INFO, WARNING, ERROR, or CRITICAL.",
    )
    parser.add_argument(
        "--seed",  # currently only intended to make testing easier
        help="The seed to use when generating random attribute values. Primarily "
        "intended to make testing easier. Best anonymization practice is to omit "
        "this value and let dicognito generate its own random seed.",
    )
    parser.add_argument("--version", action="version", version=dicognito.__version__)

    args = parser.parse_args(args)

    numeric_level = getattr(logging, args.log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError("Invalid log level: %s" % args.log_level)
    logging.basicConfig(format="", level=numeric_level)

    anonymizer = Anonymizer(id_prefix=args.id_prefix, id_suffix=args.id_suffix, seed=args.seed)

    ConvertedStudy = collections.namedtuple("ConvertedStudy", ["AccessionNumber", "PatientID", "PatientName"])

    def get_files_from_source(source):
        if os.path.isfile(source):
            yield source
        elif os.path.isdir(source):
            for (dirpath, dirnames, filenames) in os.walk(source):
                for filename in filenames:
                    yield os.path.join(dirpath, filename)
        else:
            for expanded_source in glob.glob(source):
                for file in get_files_from_source(expanded_source):
                    yield file

    def ensure_output_directory_exists(args):
        if args.output_directory and not os.path.isdir(args.output_directory):
            os.makedirs(args.output_directory)

    def calculate_output_filename(file, args, dataset):
        output_file = file
        if args.output_directory:
            output_file = os.path.join(args.output_directory, dataset.SOPInstanceUID + ".dcm")
        return output_file

    ensure_output_directory_exists(args)

    converted_studies = set()
    for source in args.sources:
        for file in get_files_from_source(source):
            try:
                with pydicom.dcmread(file, force=False) as dataset:
                    anonymizer.anonymize(dataset)
                    output_file = calculate_output_filename(file, args, dataset)
                    dataset.save_as(output_file, write_like_original=False)
                    converted_studies.add(
                        ConvertedStudy(
                            dataset.get("AccessionNumber", ""),
                            dataset.get("PatientID", ""),
                            str(dataset.get("PatientName", "")),
                        )
                    )
            except pydicom.errors.InvalidDicomError:
                logging.info("File %s appears not to be DICOM. Skipping.", file)
                continue

    if not args.quiet:
        headers = ("Accession Number", "Patient ID", "Patient Name")
        print("%-16s %-16s %s" % headers)
        print("%-16s %-16s %s" % tuple("-" * len(header) for header in headers))
        for converted_study in sorted(converted_studies, key=lambda k: (k.PatientID, k.AccessionNumber)):
            print("%-16s %-16s %s" % converted_study)


if __name__ == "__main__":
    main()
