"""Regression checks for preservation, source checks, navigation and archives."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location("reader",Path(__file__).with_name("reader.py"))
reader=importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.project,self.works=reader.read_data()
        self.glossary=json.loads((reader.ROOT/"data/terms.json").read_text(encoding="utf-8")) if self.project["mode"]=="diamond" else None

    def documents(self):
        return reader.documents(self.project,self.works,self.glossary)

    def test_lossless_import(self):
        with contextlib.redirect_stdout(io.StringIO()):
            reader.check_migration(self.works)

    def test_generated_reading_preserves_paragraph_order_and_source_pairs(self):
        output=self.documents()
        for work in self.works:
            reader.validate(work)
            text=output[reader.ROOT/"reader"/work["filename"]]
            text=re.sub(r'<a name="[^"]+"></a>',"",text)
            korean=text.split("## 한글 번역\n\n",1)[1].split("\n\n## ",1)[0]
            if work["mode"]=="diamond":
                self.assertEqual(korean,work["korean_markdown"].strip())
            else:
                lines=[line for line in korean.splitlines() if line.strip() and not line.startswith("### ")]
                self.assertEqual(lines,[u["korean"] for u in work["units"]])
            source=text.split("## 한문과 현토 독음\n\n",1)[1].split("\n\n## ",1)[0]
            lines=[line for line in source.splitlines() if line.strip() and not line.startswith(("### ","원문:"))]
            self.assertEqual(len(lines),len(work["units"])*2)
            for unit,chinese,reading in zip(work["units"],lines[::2],lines[1::2]):
                self.assertEqual(chinese,f'**{unit["source"]}**\\')
                self.assertEqual(reading,unit["reading"])

    def test_notes_and_term_records_are_preserved(self):
        output=self.documents()
        for work in self.works:
            path=reader.ROOT/"reader"/work["filename"]
            for note in work["notes"]:
                self.assertIn(reader.rebase(note["text"],work,path,self.project),output[path])
            if work["mode"]=="triples":
                path=reader.ROOT/"reader/terms"/work["filename"]
                for term in work["terms"]:
                    self.assertIn(reader.rebase(term["record"],work,path,self.project),output[path])
        if self.glossary:
            path=reader.ROOT/"reader/terms.md"
            for term in self.glossary["terms"]:
                self.assertNotEqual(term["cells"],term["headers"])
                for cell in term["cells"]:
                    self.assertIn(reader.rebase(cell,self.works[0],path,self.project,reader.ROOT/"SOURCES.md"),output[path])

    def test_source_comparison_and_tampering(self):
        raw=reader.source_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            reader.verify_sources(self.project,self.works,raw)
        unit=self.works[0]["units"][0]
        character=reader.checks.han(unit["source"])[0]
        unit["source"]=unit["source"].replace(character,"甲" if character!="甲" else "乙",1)
        with self.assertRaises((ValueError,AssertionError,SystemExit)):
            with contextlib.redirect_stdout(io.StringIO()):
                reader.verify_sources(self.project,self.works,raw)

    def test_cached_source_checksum_mismatch_fails(self):
        cache=reader.ROOT/".cache"
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            root=Path(temporary).resolve()
            self.assertTrue(root.is_relative_to(cache.resolve()))
            (root/"data").mkdir()
            (root/".cache/sources").mkdir(parents=True)
            entry={"url":"https://example.invalid/source","filename":"source.xml","sha256":hashlib.sha256(b"original").hexdigest()}
            (root/"data/source-lock.json").write_text(json.dumps({"files":[entry]}),encoding="utf-8")
            (root/".cache/sources/source.xml").write_bytes(b"tampered")
            with patch.object(reader,"ROOT",root):
                with self.assertRaisesRegex(ValueError,"checksum"):
                    reader.source_bytes()

    def test_dangling_note_and_duplicate_ids_fail(self):
        self.works[0]["units"][0]["note_ids"].append("missing")
        with self.assertRaisesRegex(ValueError,"Dangling note"):
            reader.validate(self.works[0])
        self.works[0]["units"][0]["note_ids"].pop()
        self.works[0]["units"][1]["id"]=self.works[0]["units"][0]["id"]
        with self.assertRaisesRegex(ValueError,"Duplicate ID"):
            reader.validate(self.works[0])

    def test_all_links_and_broken_destination(self):
        output=self.documents()
        active={p:p.read_text(encoding="utf-8") for p in reader.ROOT.rglob("*.md") if not {"archive",".cache",".git","dist"}.intersection(p.relative_to(reader.ROOT).parts)}
        reader.check_links({**active,**output})
        path=reader.ROOT/"reader/README.md"
        output[path]=output[path].replace(reader.anchor("top"),"",1)
        with self.assertRaisesRegex(ValueError,"Missing anchor"):
            reader.check_links(output)

    def test_archived_files_unchanged_and_outputs_are_markdown_only(self):
        manifest=json.loads((reader.ROOT/"data/import-manifest.json").read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            raw=(reader.ROOT/manifest["snapshot"]/entry["path"]).read_bytes().replace(b"\r\n",b"\n")
            self.assertEqual(hashlib.sha256(raw).hexdigest(),entry["sha256_lf"],entry["path"])
        self.assertFalse((reader.ROOT/"translation").exists())
        self.assertFalse((reader.ROOT/"dist").exists())
        self.assertFalse((reader.ROOT/".openai/hosting.json").exists())
        for path in self.documents():
            self.assertTrue(path.is_relative_to(reader.ROOT/"reader"))
            self.assertEqual(path.suffix,".md")

    def test_output_is_current_deterministic_and_menu_is_below_reading(self):
        output=self.documents()
        self.assertEqual(output,self.documents())
        for path,text in output.items():
            self.assertEqual(path.read_text(encoding="utf-8"),text)
        for work in self.works:
            text=output[reader.ROOT/"reader"/work["filename"]]
            beginning=text.split("## ",2)[0]
            self.assertNotIn("](",beginning)
            self.assertLess(text.index(work["units"][-1]["source"]),text.index("## 더 살펴보기"))
            self.assertNotRegex(text,re.compile(r"^#{1,6} [^\n]*>c\d{2}-\d{3}",re.M))


if __name__=="__main__":
    unittest.main()
