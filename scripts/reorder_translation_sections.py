"""Historical migration for the former '한문' section layout.

The current '한문과 현토 독음' layout is not a supported input.
This script is retained as a record; use verify_translation.py for checks.
"""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
TRANSLATION_DIR = ROOT / "translation"

HANJA_TITLES = {
    1: "法會因由分",
    2: "善現起請分",
    3: "大乘正宗分",
    4: "妙行無住分",
    5: "如理實見分",
    6: "正信希有分",
    7: "無得無說分",
    8: "依法出生分",
    9: "一相無相分",
    10: "莊嚴淨土分",
    11: "無爲福勝分",
    12: "尊重正教分",
    13: "如法受持分",
    14: "離相寂滅分",
    15: "持經功德分",
    16: "能淨業障分",
    17: "究竟無我分",
    18: "一體同觀分",
    19: "法界通化分",
    20: "離色離相分",
    21: "非說所說分",
    22: "無法可得分",
    23: "淨心行善分",
    24: "福智無比分",
    25: "化無所化分",
    26: "法身非相分",
    27: "無斷無滅分",
    28: "不受不貪分",
    29: "威儀寂靜分",
    30: "一合理相分",
    31: "知見不生分",
    32: "應化非真分",
}


def sections(text: str) -> tuple[str, dict[str, str]]:
    title, body = text.split("\n", 1)
    matches = list(re.finditer(r"^## (한문|한글 번역|번역 주)\s*$", body, re.MULTILINE))
    found: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        found[match.group(1)] = body[match.end():end].strip()
    return title, found


for path in sorted(TRANSLATION_DIR.glob("[0-9][0-9]-*.md")):
    number = int(path.name[:2])
    title, found = sections(path.read_text(encoding="utf-8"))
    if set(found) != {"한문", "한글 번역", "번역 주"}:
        raise ValueError(f"Unexpected sections in {path.name}: {sorted(found)}")
    if f"({HANJA_TITLES[number]})" not in title:
        title = re.sub(
            rf"^(# 제{number}분 [^—]+?)(\s+—)",
            rf"\1({HANJA_TITLES[number]})\2",
            title,
        )
    reordered = (
        f"{title}\n\n"
        f"## 한글 번역\n\n{found['한글 번역']}\n\n"
        f"## 번역 주\n\n{found['번역 주']}\n\n"
        f"## 한문\n\n{found['한문']}\n"
    )
    path.write_text(reordered, encoding="utf-8")
