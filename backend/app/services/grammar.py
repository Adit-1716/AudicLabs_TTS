import re

COMMON = {
    "teh": "the",
    "recieve": "receive",
    "seperate": "separate",
    "occured": "occurred",
    "adress": "address",
    "becuase": "because",
    "enviroment": "environment",
}


def check_and_fix(text: str) -> tuple[str, list[dict]]:
    issues = []
    out = text
    for wrong, right in COMMON.items():
        pattern = re.compile(rf"\b{wrong}\b", re.I)
        for m in pattern.finditer(out):
            issues.append({"start": m.start(), "end": m.end(), "from": m.group(), "to": right, "type": "spelling"})
        out = pattern.sub(right, out)
    if re.search(r"[.?!]\s+[a-z]", out):
        issues.append({"type": "grammar", "from": "lowercase after sentence", "to": "Capitalize"})
        out = re.sub(r"([.?!]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)
    doubled = re.findall(r"\b(\w+)\s+\1\b", out, flags=re.I)
    for w in doubled:
        issues.append({"type": "grammar", "from": f"{w} {w}", "to": w})
    out = re.sub(r"\b(\w+)\s+\1\b", r"\1", out, flags=re.I)
    return out, issues
