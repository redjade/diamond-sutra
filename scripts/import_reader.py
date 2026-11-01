"""Import a pinned Chinese/Korean translation snapshot once, without retyping."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("reader",ROOT/"scripts/reader.py")
reader=importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title",required=True)
    parser.add_argument("--commit",required=True,help="full Git commit of the original translation snapshot")
    args=parser.parse_args()
    snapshot="archive/2026-11-02"
    if (ROOT/"data").exists() or (ROOT/snapshot).exists():
        raise SystemExit("Refusing to overwrite data or archive")
    commit=subprocess.check_output(["git","rev-parse",args.commit+"^{commit}"],cwd=ROOT,text=True).strip()
    def original(path):
        return subprocess.check_output(["git","show",f"{commit}:{path}"],cwd=ROOT)
    def text(path):
        return original(path).decode("utf-8").replace("\r\n","\n")
    tree=subprocess.check_output(["git","ls-tree","-r","--name-only",commit],cwd=ROOT,text=True).splitlines()
    filenames=sorted(Path(path).name for path in tree if re.fullmatch(r"translation/[0-9]{2}-.+\.md",path))
    assert filenames,"No original translation files in the selected commit"
    works=[]
    for filename in filenames:
        raw=text("translation/"+filename)
        parts=re.split(r"^## (.+)\n",raw,flags=re.M)
        sections=dict(zip(parts[1::2],parts[2::2]))
        mode="diamond" if list(sections)==["한글 번역","번역 주","한문과 현토 독음"] else "triples"
        prefix="c"+filename[:2]
        title,introduction=parts[0].split("\n",1)
        work={"schema_version":1,"filename":filename,"mode":mode,"title":title[2:],"introduction":introduction,"import":{"commit":commit,"path":"translation/"+filename,"sha256_lf":hashlib.sha256(raw.encode()).hexdigest()},"sections":[],"units":[],"notes":[],"terms":[],"korean_markdown":sections.get("한글 번역"),"legacy_sections":[]}
        note_name="번역 주" if mode=="diamond" else "말씀 주"
        notes=sections[note_name]
        notes_template=notes
        for match in re.finditer(r"^(\d+)\. (.+(?:\n(?!\d+\. |\s*$).+)*)",notes,re.M):
            number,content=match.groups()
            nid=f"{prefix}-note-{int(number):02}"
            work["notes"].append({"id":nid,"number":int(number),"text":content})
            notes_template=notes_template.replace(match[0],f"@@note:{nid}@@",1)
        note_ids={n["number"]:n["id"] for n in work["notes"]}
        body_name="한문과 현토 독음" if mode=="diamond" else next(iter(sections))
        body=sections[body_name]
        body_template=body
        section_id=None
        lines=body.splitlines()
        i=0
        while i<len(lines):
            line=lines[i]
            if not line.strip():
                i+=1
                continue
            if line.startswith("### "):
                section_id=f"{prefix}-section-{len(work['sections'])+1:02}"
                work["sections"].append({"id":section_id,"heading":line[4:],"source_ref":"","first":"","last":""})
                body_template=body_template.replace(line,f"@@section:{section_id}@@",1)
                i+=1
                continue
            if line.startswith("원문:"):
                found=reader.checks.SOURCE_LINE.fullmatch(line.strip())
                assert found,(filename,line)
                work["sections"][-1].update(source_ref=line,first=found[1],last=found[2])
                i+=1
                continue
            assert line.startswith("**") and line.endswith("**  "),(filename,line)
            source=line[2:-4]
            reading=lines[i+1].strip()
            korean=lines[i+2].strip() if mode=="triples" else None
            count=3 if mode=="triples" else 2
            uid=f"{prefix}-{len(work['units'])+1:03}"
            refs=[note_ids[int(n)] for n in re.findall(r"\(주 (\d+)\)",korean or "")]
            work["units"].append({"id":uid,"section_id":section_id,"source":source,"reading":reading,"korean":korean,"note_ids":refs})
            original_group="\n".join(lines[i:i+count])
            body_template=body_template.replace(original_group,f"@@unit:{uid}@@",1)
            i+=count
        term_template=sections.get("전통 용어","")
        for match in re.finditer(r"^- \*\*(.+?)\*\*: (.+)$",term_template,re.M):
            label,record=match.groups()
            tid=f"{prefix}-term-{len(work['terms'])+1:02}"
            ids=[u["id"] for u in work["units"] if label in (u["korean"] or "")]
            work["terms"].append({"id":tid,"label":label,"record":record,"unit_ids":ids,"link_method":"literal_lookup"})
        for term in work["terms"]:
            term_template=term_template.replace(f'- **{term["label"]}**: {term["record"]}',f'@@term:{term["id"]}@@',1)
        for name,content in sections.items():
            role="korean" if name=="한글 번역" else "body" if name==body_name else "notes" if name==note_name else "terms"
            template={"korean":content,"body":body_template,"notes":notes_template,"terms":term_template}[role]
            work["legacy_sections"].append({"heading":name,"role":role,"template":template})
        reader.validate(work)
        assert reader.legacy_markdown(work)==raw,filename
        works.append(work)
    mode=works[0]["mode"]
    source_kind="diamond" if mode=="diamond" else "seal" if hasattr(reader.checks,"SEAL_URL") else "sections"
    urls=[reader.checks.SEAL_URL,reader.checks.XINXIN_URL] if source_kind=="seal" else [reader.checks.CBETA]
    downloads=[]
    for url in urls:
        raw=urllib.request.urlopen(url,timeout=30).read()
        downloads.append((url,raw))
    project={"schema_version":1,"title":args.title,"mode":mode,"source_kind":source_kind,"commit":commit,"snapshot":snapshot,"files":filenames}
    if mode=="diamond":
        source=text("SOURCES.md")
        body=source.split("## 주요 용어 검토\n",1)[1].split("\n## ",1)[0]
        terms=[]
        headers=None
        lines=body.splitlines()
        for index,line in enumerate(lines):
            if not line.startswith("|"):
                continue
            cells=[cell.strip() for cell in line.strip("|").split("|")]
            if index+1<len(lines) and re.match(r"\|\s*:?-{3,}",lines[index+1]):
                headers=cells
            elif cells[0].startswith("---"):
                continue
            else:
                assert len(cells)==3,line
                terms.append({"id":f"term-{len(terms)+1:03}","headers":headers[:],"cells":cells})
        assert headers and terms
        write_json(ROOT/"data/terms.json",{"headers":headers,"terms":terms,"origin":"SOURCES.md · 주요 용어 검토 · "+commit})
    for work in works:
        write_json(ROOT/"data"/Path(work["filename"]).with_suffix(".json"),work)
    write_json(ROOT/"data/project.json",project)
    entries=[]
    for url,raw in downloads:
        name=url.rsplit("/",1)[1]
        cache=ROOT/".cache/sources"/name
        cache.parent.mkdir(parents=True,exist_ok=True)
        cache.write_bytes(raw)
        entries.append({"url":url,"filename":name,"sha256":hashlib.sha256(raw).hexdigest()})
    write_json(ROOT/"data/source-lock.json",{"files":entries,"preservation":"Original XML and complete headers are retained unchanged in the local source cache."})
    manifest=[]
    for path in subprocess.check_output(["git","ls-tree","-r","--name-only",commit],cwd=ROOT,text=True).splitlines():
        raw=original(path)
        archived=ROOT/snapshot/path
        archived.parent.mkdir(parents=True,exist_ok=True)
        archived.write_bytes(raw)
        manifest.append({"path":path,"sha256_lf":hashlib.sha256(raw.replace(b"\r\n",b"\n")).hexdigest()})
    write_json(ROOT/"data/import-manifest.json",{"commit":commit,"snapshot":snapshot,"files":manifest})
    reader.verify_sources(project,works,reader.source_bytes())
    print(f'Imported {len(works)} documents, {sum(len(w["units"]) for w in works)} source units, {sum(len(w["notes"]) for w in works)} notes')


if __name__=="__main__":
    main()
