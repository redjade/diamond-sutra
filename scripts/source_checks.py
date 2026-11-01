"""Preserved source comparison and optional Unihan rules.

The legacy Markdown parser remains as a migration reference. Current validation
uses scripts/reader.py and scripts/verify_translation.py; no archived file is a
live input. Source selection and comparison algorithms retain their old rules.
"""
import argparse
import difflib
from pathlib import Path
import re
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CBETA = "https://raw.githubusercontent.com/cbeta-org/xml-p5/dbdea41071e1e260ad84b72faefd4587333cf76d/T/T08/T08n0235.xml"
CJK = re.compile(r"[\u3400-\u9fff]")
TEI = "{http://www.tei-c.org/ns/1.0}"
CB = "{http://www.cbeta.org/ns/1.0}"


def han(text):
    return "".join(CJK.findall(text))
