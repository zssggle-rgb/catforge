"""Loopback-only sample BFF and optional static host for isolated frontend debugging."""
import argparse
import hashlib
import json
import re
import secrets
import threading
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

import fixtures as f

BASE = "/api/gtm/v1"
SESSIONS = {}
LOCK = threading.Lock()


class RequestError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


def validate(scope):
    if not isinstance(scope, dict) or scope.get("category_code") not in f.CATEGORIES:
        raise RequestError(422, "品类无效")
    if scope.get("period", "today") not in ("today", "yesterday", "7d", "30d", "custom"):
        raise RequestError(422, "时间周期无效")
    if scope.get("channel") and scope["channel"] not in f.CHANNELS:
        raise RequestError(422, "渠道无效")
    if scope.get("subcategory") not in (None, "", {"TV": "flat", "AC": "home"}[scope["category_code"]]):
        raise RequestError(422, "细分品类无效")
    try:
        start, end = f.window(scope)
        if start > end or not 1 <= int(scope.get("limit", 20)) <= 100 or int(scope.get("offset", 0)) < 0:
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise RequestError(422, "日期范围或分页无效") from None


def validate_view(page, scope):
    validate(scope)
    if page not in f.PAGES:
        raise RequestError(404, "页面不存在")
    if scope.get("tab", "") not in f.TABS.get(page, {""}):
        raise RequestError(422, "分析页签无效")
    if scope.get("model_id") and scope["model_id"] not in f.CATALOG["own-model"]:
        raise RequestError(422, "我品型号无效")
    for name, kind in [("competitor_ids", "competitor"), ("brand_ids", "brand")]:
        ids = scope.get(name, [])
        if not isinstance(ids, list) or len(ids) > (5 if page == "rival-monitor" else 10) or any(k not in f.CATALOG[kind] for k in ids):
            raise RequestError(422, "选择的对象无效或数量超过上限")


def chat_list(state, category):
    return [{"id": c["id"], "label": c["label"]} for c in reversed(list(state["chats"].values())) if c["category"] == category]


def read_chat(state, category, key):
    chat = state["chats"].get(key)
    if not chat or chat["category"] != category:
        raise RequestError(404, "对话不存在")
    return {k: chat[k] for k in ("id", "label", "messages")}


def answer(state, payload):
    scope = payload.get("scope")
    validate(scope)
    question = payload.get("question")
    if not isinstance(question, str) or not question.strip() or len(question) > 4000:
        raise RequestError(422, "请输入 1 至 4000 字的问题")
    key = payload.get("conversation_id")
    category = scope["category_code"]
    if key:
        read_chat(state, category, key)
    names = []
    for aid in payload.get("attachment_ids", []):
        ref = state["uploads"].get(aid, {})
        if ref.get("category") != category or ref.get("purpose") != "chat":
            raise RequestError(422, "附件不属于当前对话范围")
        names.append(ref["name"])
    daily = f.business_view("daily", scope, state)
    insights = daily["insights"]
    match = next((i for i in insights if i.get("question") == question or i["title"] in question), None)
    reply = match["body"] if match else "样例助手支持当前工作总览中的价格异常、竞品调价和上新追问。"
    question_with_files = question + ("\n附件：" + "、".join(names) if names else "")
    if not key:
        key = secrets.token_hex(8)
        state["chats"][key] = {"id": key, "category": category, "label": question[:32], "messages": []}
    state["chats"][key]["messages"].extend([{"role": "user", "text": question_with_files, "evidence": []},
        {"role": "assistant", "text": reply, "evidence": match["evidence"] if match else []}])
    return read_chat(state, category, key)


def perform(state, payload):
    scope, op, key = payload.get("scope", {}), payload.get("operation"), payload.get("row_id")
    page = scope.get("page")
    validate_view(page, scope)
    if scope.get("project_id") != f.PROJECT:
        raise RequestError(422, "项目范围不一致")
    view = f.business_view(page, scope, state)
    if payload.get("snapshot_id") != view["snapshot_id"]:
        raise RequestError(409, "快照已变化，请刷新后重试")
    actions = view["actions"] if key is None else [a for t in view["tables"] for r in t["rows"] if r["id"] == key for a in r["actions"]]
    offered = next((a for a in actions if a["operation"] == op), None)
    if not offered:
        raise RequestError(409, "操作不可用，请刷新页面")
    fields = payload.get("fields", {})
    if any(not isinstance(fields.get(x["key"]), str) or not fields[x["key"]].strip() for x in offered.get("fields", [])):
        raise RequestError(422, "请填写必填字段")
    if op == "complete-task":
        state["closed"].add(key)
    elif op == "acknowledge-alert":
        state["ack"].add(key)
    elif op == "ignore-alert":
        state["ignored"][key] = fields["reason"]
    elif op == "import-floor":
        aid = fields["attachment_id"]
        ref = state["uploads"].get(aid, {})
        if ref.get("category") != scope["category_code"] or ref.get("purpose") != "floor":
            raise RequestError(422, "底价附件无效")
        state["floor_imports"][aid] = f.row(aid, ref["name"], {"文件": ref["name"], "状态": "已接收，待解析"},
            f.evidence(aid, "样例导入回执", "样例服务仅接收文件，未验证或启用政策。"))
    elif op == "create-campaign":
        from datetime import date
        if date.fromisoformat(fields["start"]) > date.fromisoformat(fields["end"]):
            raise RequestError(422, "活动结束日须晚于或等于开始日")
        cid = secrets.token_hex(8)
        state["campaigns"][cid] = f.row(cid, fields["name"], {"活动": fields["name"], "开始日期": fields["start"],
            "结束日期": fields["end"], "状态": "待确认"}, f.evidence(cid, "样例活动草稿", fields["name"]))
    elif op == "subscribe-report":
        state["subscriptions"].add(key)
    elif op == "unsubscribe-report":
        state["subscriptions"].discard(key)
    elif op == "create-report":
        name = str(payload.get("input", "")).strip()
        if not name or len(name) > 120:
            raise RequestError(422, "报告名称限 1 至 120 字")
        state["reports"][secrets.token_hex(8)] = name
    elif op == "set-key-models":
        models = list(dict.fromkeys(x.strip() for x in re.split("[,，]", str(payload.get("input", ""))) if x.strip()))
        if not models or not set(models) <= set(i[0] for i in f.SALES):
            raise RequestError(422, "样例可选型号为 " + "、".join(i[0] for i in f.SALES))
        state["models"] = models
    elif op == "edit-report":
        state["content"][key] = fields["body"]
    elif op == "publish-report":
        state["published"].add(key)
    else:
        raise RequestError(422, "未知操作")
    state["revision"] += 1
    return {"id": secrets.token_hex(8), "message": "操作已保存"}


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if getattr(self, "cookie", None):
            self.send_header("Set-Cookie", f"gtm_sample={self.cookie}; HttpOnly; SameSite=Strict; Path=/api/gtm/v1")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def session(self):
        cookies = SimpleCookie(self.headers.get("Cookie", ""))
        token = cookies["gtm_sample"].value if "gtm_sample" in cookies else None
        if token not in SESSIONS:
            token = self.cookie = secrets.token_hex(24)
            now = time.monotonic()
            for key in [k for k, (_, at) in SESSIONS.items() if now - at > 86400]:
                del SESSIONS[key]
            SESSIONS[token] = (f.initial_state(), now)
        state, _ = SESSIONS[token]
        SESSIONS[token] = state, time.monotonic()
        return state

    def do_GET(self):
        path = urlsplit(self.path)
        if not path.path.startswith(BASE + "/"):
            return self.static(path.path)
        try:
            with LOCK:
                state = self.session()
                if path.path == BASE + "/context":
                    result = f.context()
                else:
                    resource = self.resource(path.path)
                    pairs = parse_qsl(path.query)
                    query = dict(pairs)
                    for key in ("competitor_ids", "brand_ids"):
                        if key in query:
                            query[key] = [v for k, v in pairs if k == key]
                    validate(query)
                    if resource.startswith("views/"):
                        page = resource[6:]
                        validate_view(page, query)
                        result = f.business_view(page, query, state)
                    elif resource == "catalog":
                        kind = query.get("kind")
                        if kind not in f.CATALOG:
                            raise RequestError(422, "目录类型无效")
                        result = [o for o in f.options(f.CATALOG[kind]) if query.get("query", "").casefold() in o["label"].casefold()][:int(query.get("limit", 50))] if query["category_code"] == "TV" else []
                    elif resource == "conversations":
                        result = chat_list(state, query["category_code"])
                    elif resource.startswith("conversations/"):
                        result = read_chat(state, query["category_code"], resource[14:])
                    else:
                        raise RequestError(404, "接口不存在")
            self.respond(200, result)
        except RequestError as err:
            self.respond(err.code, {"message": err.message})

    def resource(self, path):
        prefix = BASE + "/projects/" + f.PROJECT + "/"
        if not path.startswith(prefix):
            raise RequestError(404, "项目或接口不存在")
        return unquote(path[len(prefix):])

    def do_POST(self):
        try:
            endpoint = self.resource(urlsplit(self.path).path)
            if endpoint == "attachments":
                return self.upload()
            if endpoint not in ("messages", "actions"):
                raise RequestError(404, "接口不存在")
            if self.headers.get_content_type() != "application/json":
                raise RequestError(415, "需要 JSON 请求")
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 32768:
                raise RequestError(413, "请求大小无效")
            body = json.loads(self.rfile.read(size))
            key = body.get("request_id") if isinstance(body, dict) else None
            if not isinstance(key, str) or not 1 <= len(key) <= 100:
                raise RequestError(422, "缺少幂等键")
            digest = hashlib.sha256(json.dumps([endpoint, body], sort_keys=True).encode()).hexdigest()
            with LOCK:
                state = self.session()
                existing = state["receipts"].get(key)
                if existing and existing[0] != digest:
                    raise RequestError(409, "幂等键已用于不同请求")
                if existing:
                    result = existing[1]
                else:
                    result = answer(state, body) if endpoint == "messages" else perform(state, body)
                    state["receipts"][key] = (digest, json.loads(json.dumps(result)))
            self.respond(200, result)
        except RequestError as err:
            self.respond(err.code, {"message": err.message})
        except (ValueError, AttributeError, TypeError):
            self.respond(422, {"message": "JSON 请求格式无效"})

    def upload(self):
        query = dict(parse_qsl(urlsplit(self.path).query))
        validate(query)
        purpose = query.get("purpose")
        name = Path(query.get("filename", "")).name
        allowed = {".xlsx", ".csv"} if purpose == "floor" else {".csv", ".xlsx", ".pdf", ".txt", ".png", ".jpg", ".jpeg"}
        if purpose not in ("chat", "floor") or Path(name).suffix.lower() not in allowed:
            raise RequestError(422, "不支持的附件类型")
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= 10 * 1024 * 1024:
            raise RequestError(413, "样例附件上限为 10 MB")
        data = self.rfile.read(size)
        if len(data) != size:
            raise RequestError(422, "附件传输不完整")
        aid = secrets.token_hex(12)
        with LOCK:
            self.session()["uploads"][aid] = {"name": name, "size": size, "category": query["category_code"], "purpose": purpose}
        self.respond(201, {"id": aid, "name": name})

    def static(self, path):
        root = self.server.static_root
        if not root:
            return self.send_error(HTTPStatus.NOT_FOUND)
        if path in ("/", "/gtm", "/gtm/"):
            path = "/index.html"
        file = (root / unquote(path).lstrip("/")).resolve()
        if not file.is_relative_to(root) or not file.is_file():
            return self.send_error(HTTPStatus.NOT_FOUND)
        import mimetypes
        content = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(file.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18166)
    parser.add_argument("--dist", type=Path)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.static_root = args.dist.resolve() if args.dist else None
    server.serve_forever()
