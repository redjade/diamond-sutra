"""Check current reading documents; optionally compare pinned CBETA and Unihan."""
import argparse
import importlib.util
from pathlib import Path
import sys

spec=importlib.util.spec_from_file_location("reader",Path(__file__).with_name("reader.py"))
reader=importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cbeta",action="store_true")
    parser.add_argument("--unihan")
    args=parser.parse_args()
    reader.run(check=True,source=args.cbeta,unihan=args.unihan)


if __name__=="__main__":
    main()
