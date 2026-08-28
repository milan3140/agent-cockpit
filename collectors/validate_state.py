# -*- coding: utf-8 -*-
"""驗證 state.json 是否符合 config/schema.json(collector↔UI 的契約)。
寫新資料源時跑這支,確保 UI 讀得懂;CI 也可以掛。
零依賴:內建輕量檢查(type/required/enum/items/$ref/$defs),不需要 pip install jsonschema。

用法:py validate_state.py [state 檔路徑]   預設 ~/.config/agent_cockpit/state.json
回傳碼:0=通過(可能有 warning)、1=有 error
"""
import io, os, sys, json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(HERE, "..", "config", "schema.json")
STATE = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.config/agent_cockpit/state.json")

TYPES = {"object": dict, "array": list, "string": str, "integer": int,
         "number": (int, float), "boolean": bool, "null": type(None)}
errors, warns = [], []


def resolve(node, root):
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        if not ref.startswith("#/"):
            return node
        cur = root
        for part in ref[2:].split("/"):
            cur = cur.get(part, {})
        node = cur
    return node


def type_ok(val, spec):
    t = spec.get("type")
    if t is None:
        return True
    tl = t if isinstance(t, list) else [t]
    for name in tl:
        py = TYPES.get(name)
        if py is None:
            continue
        if name == "integer" and isinstance(val, bool):
            continue
        if name == "number" and isinstance(val, bool):
            continue
        if isinstance(val, py):
            return True
    return False


def check(val, spec, root, path):
    spec = resolve(spec, root)
    if not isinstance(spec, dict):
        return
    if not type_ok(val, spec):
        errors.append("%s:型別應為 %s,實際 %s" % (path, spec.get("type"), type(val).__name__))
        return
    if "enum" in spec and val not in spec["enum"]:
        errors.append("%s:值 %r 不在允許清單 %s" % (path, val, spec["enum"]))
    if isinstance(val, dict):
        for req in spec.get("required", []):
            if req not in val:
                errors.append("%s:缺必要欄位 `%s`" % (path, req))
        props = spec.get("properties", {})
        for k, v in val.items():
            if k.startswith("_"):
                continue
            if k in props:
                check(v, props[k], root, path + "." + k)
            elif "additionalProperties" in spec and isinstance(spec["additionalProperties"], dict):
                check(v, spec["additionalProperties"], root, path + "." + k)
            elif props and spec.get("additionalProperties") is not True:
                warns.append("%s.%s:schema 未定義此欄位(不影響執行,但建議補進 schema)" % (path, k))
    elif isinstance(val, list) and "items" in spec:
        for i, item in enumerate(val):
            check(item, spec["items"], root, "%s[%d]" % (path, i))


def main():
    try:
        schema = json.load(open(SCHEMA, encoding="utf-8"))
    except Exception as e:
        print("讀不到 schema:", e); sys.exit(1)
    try:
        state = json.load(open(STATE, encoding="utf-8"))
    except Exception as e:
        print("讀不到 state(%s):%s" % (STATE, e)); sys.exit(1)

    check(state, schema, schema, "state")
    known = [k for k in schema.get("properties", {}) if k in state]
    print("驗證 %s" % STATE)
    print("  區段:%s" % (", ".join(known) or "(空)"))
    for w in warns[:20]:
        print("  ⚠ " + w)
    if warns[20:]:
        print("  ⚠ …另有 %d 則" % len(warns[20:]))
    for e in errors:
        print("  ✗ " + e)
    if errors:
        print("結果:✗ %d 個錯誤" % len(errors)); sys.exit(1)
    print("結果:✓ 通過(%d 個提醒)" % len(warns))


if __name__ == "__main__":
    main()
