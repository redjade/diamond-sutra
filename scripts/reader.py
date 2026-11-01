"""Generate Markdown reading editions from structured Chinese/Korean data."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote,urlsplit
import urllib.request
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("source_checks",ROOT/"scripts/source_checks.py")
checks=importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


def require(condition,message):
    if not condition:
        raise ValueError(message)


def read_data():
    project=json.loads((ROOT/"data/project.json").read_text(encoding="utf-8"))
    works=[json.loads((ROOT/"data"/Path(name).with_suffix(".json")).read_text(encoding="utf-8")) for name in project["files"]]
    return project,works


def legacy_markdown(work):
    values={}
    for section in work["sections"]:
        values["section:"+section["id"]]="### "+section["heading"]
    for unit in work["units"]:
        value=f'**{unit["source"]}**  \n{unit["reading"]}'
        if unit["korean"] is not None:
            value+="  \n"+unit["korean"]
        values["unit:"+unit["id"]]=value
    for note in work["notes"]:
        values["note:"+note["id"]]=f'{note["number"]}. {note["text"]}'
    for term in work["terms"]:
        values["term:"+term["id"]]=f'- **{term["label"]}**: {term["record"]}'
    text="# "+work["title"]+"\n"+work["introduction"]
    for item in work["legacy_sections"]:
        body=item["template"]
        if item["role"]=="korean":
            body=work["korean_markdown"]
        body=re.sub(r"@@([^@]+)@@",lambda m:values[m[1]],body)
        text+="## "+item["heading"]+"\n"+body
    return text


def validate(work):
    ids=[item["id"] for kind in ("sections","units","notes","terms") for item in work[kind]]
    require(len(ids)==len(set(ids)),"Duplicate ID")
    require(all(re.fullmatch(r"[a-z0-9-]+",x) for x in ids),"Unsafe ID")
    sections={s["id"] for s in work["sections"]}
    notes={n["id"]:n for n in work["notes"]}
    require([n["number"] for n in work["notes"]]==list(range(1,len(notes)+1)),"Note numbering differs")
    used=set()
    for unit in work["units"]:
        require(unit["section_id"] is None or unit["section_id"] in sections,"Unknown section")
        require(unit["source"] and unit["reading"],"Empty source or reading")
        require(not checks.CJK.search(unit["reading"]),"Chinese character in reading")
        require(set(unit["note_ids"])<=set(notes),"Dangling note link")
        if unit["korean"] is not None:
            refs=[int(n) for n in re.findall(r"\(주 (\d+)\)",unit["korean"])]
            require([notes[n]["number"] for n in unit["note_ids"]]==refs,"Note marker differs")
            used.update(unit["note_ids"])
    if work["mode"]=="triples":
        require(used==set(notes),"Unreferenced note")
    for term in work["terms"]:
        require(term["link_method"]=="literal_lookup","Unreviewed semantic alignment")
        require(set(term["unit_ids"])<={u["id"] for u in work["units"]},"Dangling term lookup")


def source_bytes(fetch=False):
    lock=json.loads((ROOT/"data/source-lock.json").read_text(encoding="utf-8"))
    result={}
    for entry in lock["files"]:
        path=ROOT/".cache/sources"/entry["filename"]
        if fetch or not path.exists():
            raw=urllib.request.urlopen(entry["url"],timeout=30).read()
            require(hashlib.sha256(raw).hexdigest()==entry["sha256"],"Downloaded source checksum differs")
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(raw)
        raw=path.read_bytes()
        require(hashlib.sha256(raw).hexdigest()==entry["sha256"],"Cached source checksum differs")
        result[entry["url"]]=raw
    return result


def chapter_sections(work):
    return [(s["heading"],s["first"],s["last"],[(u["source"],u["reading"],u["korean"]) for u in work["units"] if u["section_id"]==s["id"]]) for s in work["sections"]]


def verify_sources(project,works,raw):
    if project["mode"]=="diamond":
        local="".join(checks.han(u["source"]) for w in works for u in w["units"])
        root=ET.fromstring(raw[checks.CBETA])
        body=root.find(f".//{checks.TEI}body")
        expected="".join(checks.han("".join(node.itertext())) for node in body.iter() if node.tag in (checks.TEI+"p",checks.TEI+"l") and node.attrib.get(checks.CB+"type")!="dharani")
        require(local==expected,"Chinese text differs from CBETA T235")
        print(f"PASS: exact CBETA T235 sutra text, {len(local)} characters")
    else:
        chapters=[(w["filename"],chapter_sections(w)) for w in works]
        if project["source_kind"]=="seal":
            checks.check_cbeta(chapters,raw)
        else:
            checks.check_cbeta(chapters,raw[checks.CBETA])


def anchor(identifier):
    return f'<a name="{identifier}"></a>'


def heading(level,text,identifier):
    return "#"*level+" "+anchor(identifier)+text


def slug(text):
    return "".join(c for c in text.lower() if c.isalnum() or c in " _-").replace(" ","-")


def rebase(text,work,target,project,source_path=None):
    old=source_path or ROOT/"translation"/work["filename"]
    def change(match):
        parsed=urlsplit(match[1])
        if parsed.scheme or parsed.netloc:
            return match[0]
        dest=(old.parent/unquote(parsed.path)).resolve() if parsed.path else old
        fragment=unquote(parsed.fragment)
        if dest.parent==ROOT/"translation":
            if dest.name=="STYLE.md":
                dest=ROOT/"STYLE.md"
            elif dest.name=="README.md":
                dest=ROOT/"reader/README.md"
            elif dest.name in project["files"]:
                folder="reader/terms" if fragment=="전통-용어" else "reader"
                dest=ROOT/folder/dest.name
                fragment={"전통-용어":"top","경문":"translation","본문":"translation","한글-번역":"translation","말씀-주":"notes","번역-주":"notes","한문과-현토-독음":"source"}.get(fragment,fragment)
        if dest==ROOT/"README.md" and fragment and (ROOT/"REFERENCE.md").exists():
            current={slug(h) for h in re.findall(r"^#{1,6} (.+)$",(ROOT/"README.md").read_text(encoding="utf-8"),re.M)}
            reference={slug(h) for h in re.findall(r"^#{1,6} (.+)$",(ROOT/"REFERENCE.md").read_text(encoding="utf-8"),re.M)}
            if fragment not in current and fragment in reference:
                dest=ROOT/"REFERENCE.md"
        relative="" if dest==target else os.path.relpath(dest,target.parent).replace("\\","/")
        return "]("+relative+("#"+fragment if fragment else "")+")"
    return re.sub(r"\]\(([^)\n]+)\)",change,text)


def link(label,target,destination,identifier="top"):
    relative="" if destination==target else os.path.relpath(destination,target.parent).replace("\\","/")
    return f"[{label}]({relative}#{identifier})"


def footer(project,work,target):
    filename=work["filename"]
    primary=ROOT/"reader"/filename
    terms=ROOT/"reader/terms.md" if project["mode"]=="diamond" else ROOT/"reader/terms"/filename
    neighbors=[]
    index=project["files"].index(filename)
    for offset,label in [(-1,"앞 문서"),(1,"다음 문서")]:
        if 0<=index+offset<len(project["files"]):
            neighbors.append(link(label,target,ROOT/"reader"/project["files"][index+offset]))
    notes_label="번역 주" if project["mode"]=="diamond" else "말씀 주"
    return "\n\n".join(["---","## 더 살펴보기",
        " · ".join(link(label,target,primary,key) for label,key in [("한글 번역","translation"),(notes_label,"notes"),("한문·현토","source"),("원전 안내","guide")]),
        " · ".join([link("구절별 대조",target,ROOT/"reader/parallel"/filename),link("주석 찾아보기",target,ROOT/"reader/notes"/filename),link("용어 대응",target,terms)]),
        " · ".join(neighbors+[link("읽기 목록",target,ROOT/"reader/README.md")]),
        " · ".join(f'[{label}]({os.path.relpath(ROOT/name,target.parent).replace(chr(92),"/")})' for label,name in [("저장소 처음으로","README.md"),("번역 원칙","STYLE.md"),("원문과 근거","SOURCES.md")]),
        "[맨 위로](#top) · 번역·검토 중인 초안입니다."])


def render_sectioned(work,mode):
    out=[]
    sections={s["id"]:s for s in work["sections"]}
    previous=None
    for unit in work["units"]:
        sid=unit["section_id"]
        if sid and sid!=previous:
            out.append("### "+sections[sid]["heading"])
            if mode=="source":
                out.append(sections[sid]["source_ref"])
        previous=sid
        if mode=="korean":
            out.append(anchor(unit["id"])+unit["korean"])
        else:
            out.append(anchor("source-"+unit["id"])+f'**{unit["source"]}**\\\n{unit["reading"]}')
    return "\n\n".join(out)


def documents(project,works,glossary=None):
    result={}
    for work in works:
        filename=work["filename"]
        primary=ROOT/"reader"/filename
        note_label="번역 주" if work["mode"]=="diamond" else "말씀 주"
        korean=work["korean_markdown"].strip() if work["mode"]=="diamond" else render_sectioned(work,"korean")
        notes="\n\n".join(f'{n["number"]}. {anchor(n["id"])}{rebase(n["text"],work,primary,project)}' for n in work["notes"])
        guide="\n".join(line for line in work["introduction"].strip().splitlines() if not line.startswith("- 읽는 법:"))
        content=["<!-- Generated from data; edit the JSON, not this document. -->",heading(1,work["title"],"top"),heading(2,"한글 번역","translation"),korean,heading(2,note_label,"notes"),notes,heading(2,"한문과 현토 독음","source"),render_sectioned(work,"source"),heading(2,"원문과 읽는 법","guide")]
        if guide.strip():
            content.append(rebase(guide,work,primary,project))
        content.extend(["한글 번역을 이어 읽고 같은 문서의 주석·한문·현토를 살펴봅니다. 한문과 현토는 원래 의미 단위와 표기를 보존했습니다. 편집상 소제목·주 표식과 경문을 구별합니다. 판본 차이와 대조 범위는 기존 주석·근거 기록에 따릅니다.",footer(project,work,primary)])
        result[primary]="\n\n".join(x for x in content if x).rstrip()+"\n"

        target=ROOT/"reader/parallel"/filename
        output=[heading(1,work["title"]+" · 대조","top")]
        if work["mode"]=="diamond":
            output.extend(["기존 한글 문단과 한문·현토 단위의 수가 다릅니다. 분 전체를 대조하며, 문단과 원문 단위가 일대일로 정렬되었다고 표시하지 않습니다.","## 한글 번역",work["korean_markdown"].strip(),"## 한문과 현토 독음",render_sectioned(work,"source"),link("읽기판 번역으로",target,primary,"translation")])
        else:
            sections={s["id"]:s for s in work["sections"]}
            previous=None
            notes_by_id={n["id"]:n for n in work["notes"]}
            for number,unit in enumerate(work["units"],1):
                if unit["section_id"]!=previous:
                    section=sections[unit["section_id"]]
                    output.extend(["## "+section["heading"],section["source_ref"]])
                previous=unit["section_id"]
                output.extend([heading(3,f"구절 {number}",unit["id"]),"**한글 번역**",unit["korean"],"**한문**",unit["source"],"**현토 독음**",unit["reading"]])
                if unit["note_ids"]:
                    output.append("주석: "+" · ".join(link(f'주 {notes_by_id[nid]["number"]}',target,ROOT/"reader/notes"/filename,nid) for nid in unit["note_ids"]))
                output.append(link("한글 본문으로",target,primary,unit["id"]))
        output.append(footer(project,work,target))
        result[target]="\n\n".join(output).rstrip()+"\n"

        target=ROOT/"reader/notes"/filename
        output=[heading(1,work["title"]+" · 주석","top")]
        for note in work["notes"]:
            output.extend([heading(2,f'{note_label} {note["number"]}',note["id"]),rebase(note["text"],work,target,project)])
            if work["mode"]=="diamond":
                output.append(link("해당 분의 번역으로",target,primary,"translation"))
            else:
                ids=[u["id"] for u in work["units"] if note["id"] in u["note_ids"]]
                output.append("본문으로: "+" · ".join(link(f'구절 {next(i for i,u in enumerate(work["units"],1) if u["id"]==uid)}',target,primary,uid) for uid in dict.fromkeys(ids)))
        output.append(footer(project,work,target))
        result[target]="\n\n".join(output).rstrip()+"\n"

        if work["mode"]=="triples":
            target=ROOT/"reader/terms"/filename
            output=[heading(1,work["title"]+" · 용어 대응","top"),"기존 전통 용어 기록을 보존했습니다. 새 원어·판본·일반 한국어 번역본의 대응을 조사해 채운 표가 아닙니다. 구절 연결은 번역 표현의 문자 일치를 이용한 찾아보기이며 의미 대응 확정과는 구별합니다."]
            output.append("\n".join(["| 이 번역의 표현 | 대응 기록 |","| --- | --- |"]+[f'| {link(t["label"],target,target,t["id"])} | {link("설명 보기",target,target,t["id"])} |' for t in work["terms"]]))
            for term in work["terms"]:
                output.extend([heading(2,term["label"],term["id"]),rebase(term["record"],work,target,project)])
                output.append("표기를 찾은 본문: "+" · ".join(link(f'구절 {next(i for i,u in enumerate(work["units"],1) if u["id"]==uid)}',target,primary,uid) for uid in term["unit_ids"]) if term["unit_ids"] else link("경의 번역으로",target,primary,"translation"))
            output.append(footer(project,work,target))
            result[target]="\n\n".join(output).rstrip()+"\n"
    if project["mode"]=="diamond":
        target=ROOT/"reader/terms.md"
        output=[heading(1,"금강경 · 용어 대응 기록","top"),"SOURCES의 주요 용어 검토 표를 그대로 반입했습니다. 한문·위치, 산스크리트 대조·관련어, 현재 표현과 판단을 구별합니다. 일반 번역본의 용례 조사나 새로운 구절별 의미 대응을 추가하지 않았습니다."]
        output.append("\n".join(["| 한문과 위치 | 기록 |","| --- | --- |"]+[f'| {link(t["cells"][0],target,target,t["id"])} | {link("대조와 판단",target,target,t["id"])} |' for t in glossary["terms"]]))
        for i,term in enumerate(glossary["terms"],1):
            output.append(heading(2,f"용어 기록 {i}",term["id"]))
            for label,cell in zip(term.get("headers",glossary["headers"]),term["cells"]):
                output.extend(["**"+label+"**",rebase(cell,works[0],target,project,ROOT/"SOURCES.md")])
        output.append("[읽기 목록](README.md) · [원문과 근거](../SOURCES.md) · [맨 위로](#top)")
        result[target]="\n\n".join(output).rstrip()+"\n"
    index=ROOT/"reader/README.md"
    result[index]="\n\n".join([heading(1,project["title"]+" 읽기","top"), "\n".join(f'{i}. [{w["title"]}]({w["filename"]})' for i,w in enumerate(works,1)),"각 문서는 한글 번역 → 주석 → 한문·현토 순서입니다. 메뉴와 원전 안내는 아래에 두었습니다.","[저장소 처음으로](../README.md) · [자료 편집과 생성](EDITING.md)"])+"\n"
    return result


def check_links(documents):
    for path,text in documents.items():
        names=re.findall(r'<a name="([^"]+)"',text)
        require(len(names)==len(set(names)),f"Duplicate anchor: {path}")
        for value in re.findall(r"\]\(([^)\n]+)\)",text):
            parsed=urlsplit(value)
            if parsed.scheme or parsed.netloc:
                continue
            dest=(path.parent/unquote(parsed.path)).resolve() if parsed.path else path
            require(dest in documents or dest.exists(),f"Missing link: {path}: {value}")
            if parsed.fragment and (dest in documents or dest.is_file()):
                content=documents[dest] if dest in documents else dest.read_text(encoding="utf-8")
                names=re.findall(r'<a name="([^"]+)"',content)
                names += [slug(re.sub(r'<[^>]+>',"",h)) for h in re.findall(r"^#{1,6} (.+)$",content,re.M)]
                require(unquote(parsed.fragment) in names,f"Missing anchor: {path}: {value}")


def check_migration(works):
    for work in works:
        baseline=subprocess.check_output(["git","show",f'{work["import"]["commit"]}:{work["import"]["path"]}'],cwd=ROOT).decode("utf-8").replace("\r\n","\n")
        require(hashlib.sha256(baseline.encode()).hexdigest()==work["import"]["sha256_lf"],"Baseline checksum differs")
        require(legacy_markdown(work)==baseline,f'Migration differs: {work["filename"]}')
    print(f"PASS: lossless reconstruction of {len(works)} original documents")


def build(project,works,check=False):
    glossary=json.loads((ROOT/"data/terms.json").read_text(encoding="utf-8")) if project["mode"]=="diamond" else None
    output=documents(project,works,glossary)
    active={p:p.read_text(encoding="utf-8") for p in ROOT.rglob("*.md") if not {".git",".cache","archive","dist"}.intersection(p.relative_to(ROOT).parts)}
    check_links({**active,**output})
    for path,text in output.items():
        require(path.is_relative_to(ROOT/"reader"),"Output outside reader")
        if check:
            require(path.is_file() and path.read_text(encoding="utf-8")==text,f"Stale generated file: {path}")
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(text,encoding="utf-8",newline="\n")
    return output


def run(check=False,source=True,fetch=False,unihan=None,migration=False):
    project,works=read_data()
    for work in works:
        validate(work)
    if source:
        verify_sources(project,works,source_bytes(fetch))
    if unihan:
        require(project["mode"]=="triples","No Unihan comparison was previously defined")
        checks.check_readings([(w["filename"],chapter_sections(w)) for w in works],checks.load_unihan(unihan))
    if migration:
        check_migration(works)
    build(project,works,check)
    print(f'PASS: {len(works)} documents; {sum(len(w["units"]) for w in works)} source units; Markdown only')


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check",action="store_true")
    parser.add_argument("--check-migration",action="store_true")
    parser.add_argument("--fetch-source",action="store_true")
    args=parser.parse_args()
    run(args.check,True,args.fetch_source,migration=args.check_migration)


if __name__=="__main__":
    main()
