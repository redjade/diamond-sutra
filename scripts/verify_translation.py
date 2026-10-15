"""Check the Markdown structure; optionally compare Chinese with CBETA T235."""

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cbeta", action="store_true")
    args = parser.parse_args()
    files = sorted((ROOT / "translation").glob("[0-9][0-9]-*.md"))
    assert len(files) == 32, f"Expected 32 chapters, found {len(files)}"
    chinese = ""
    spans = []
    for number, path in enumerate(files, 1):
        assert path.name.startswith(f"{number:02d}-"), path.name
        text = path.read_text(encoding="utf-8")
        headings = re.findall(r"^## (.+)$", text, re.MULTILINE)
        assert headings == ["한글 번역", "번역 주", "한문과 현토 독음"], path.name
        section = text.split("## 한문과 현토 독음", 1)[1]
        lines = [line for line in section.splitlines() if line.strip()]
        assert len(lines) % 2 == 0, path.name
        start = len(chinese)
        for source, reading in zip(lines[::2], lines[1::2]):
            assert re.fullmatch(r"\*\*.+\*\*\s*", source), path.name
            assert not CJK.search(reading), (path.name, reading)
            assert not reading.startswith(">"), path.name
            chinese += han(source)
        spans.append((start, len(chinese), path.name))
    print(f"PASS: 32 chapters; headings and Chinese/reading pairs; {len(chinese)} Chinese characters")
    if not args.cbeta:
        return
    with urllib.request.urlopen(CBETA, timeout=30) as response:
        root = ET.fromstring(response.read())
    body = root.find(f".//{TEI}body")
    # The translation covers the sutra, including its verses, but excludes
    # the appended dharani, title, translator credit, and apparatus.
    remote = "".join(
        han("".join(node.itertext()))
        for node in body.iter()
        if node.tag in (TEI + "p", TEI + "l")
        and node.attrib.get(CB + "type") != "dharani"
    )
    changes = [
        item for item in difflib.SequenceMatcher(None, remote, chinese, autojunk=False).get_opcodes()
        if item[0] != "equal"
    ]
    for operation, a, b, c, d in changes:
        chapter = next((name for start, end, name in spans if start <= c < end), "end")
        print(f"{chapter}: {operation}; CBETA={remote[a:b]!r}; local={chinese[c:d]!r}")
        print("  CBETA context:", remote[max(0, a - 12):b + 12])
        print("  local context:", chinese[max(0, c - 12):d + 12])
    assert not changes, f"{len(changes)} Chinese text differences from CBETA"
    print(f"PASS: exact match to CBETA T235 sutra text ({len(remote)} characters)")


if __name__ == "__main__":
    main()
