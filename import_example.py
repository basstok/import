"""A tiny, bounded historical import: preview locally, or explicitly apply via REST."""

import argparse
from datetime import datetime
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import urlsplit
import uuid


SOURCE_SYSTEM = "fictional-messages"
MAX_SOURCE = 1024 * 1024
MAX_RESPONSE = 64 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON field.")
        result[key] = value
    return result


def decoded(data):
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=unique_object,
                          parse_constant=lambda value: require(False, "Invalid JSON number."))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError("Expected bounded UTF-8 JSON.") from None


def fields(value, names):
    require(type(value) is dict and set(value) == set(names.split()),
            "Missing or unsupported source fields; this example accepts only public history.")


def text(value, limit=16384):
    require(isinstance(value, str) and 0 < len(value) <= limit and value.strip(),
            "Expected nonempty bounded text.")
    require(not any(ord(character) < 32 and character not in "\n\t" or
                    0xD800 <= ord(character) <= 0xDFFF for character in value),
            "Invalid text characters.")
    return value


def timestamp(value):
    require(isinstance(value, str) and
            re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value),
            "Use UTC timestamps: YYYY-MM-DDTHH:MM:SSZ.")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("Invalid calendar timestamp.") from None
    return value


def records(value):
    require(type(value) is list and len(value) <= 100, "Each collection is limited to 100 records.")
    return value


def canonical_id(organization, import_id, kind, source_id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL,
                         encoded([organization, import_id, kind, source_id]).decode()))


def build_plan(source, organization="example-community", import_id="fictional-messages-v1"):
    text(organization, 128)
    require(isinstance(import_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,109}", import_id),
            "Use a short import ID containing ASCII letters, digits, hyphens or underscores.")
    with Path(source).open("rb") as stream:
        original = stream.read(MAX_SOURCE + 1)
    require(0 < len(original) <= MAX_SOURCE, "Source must contain 1 byte to 1 MiB.")
    document = decoded(original)
    fields(document, "members posts")
    seen = set()

    def identity(kind, value):
        source_id = text(value, 128)
        require((kind, source_id) not in seen, "Duplicate source ID within a record kind.")
        seen.add((kind, source_id))
        return canonical_id(organization, import_id, kind, source_id)

    members, authors = [], {}
    for member in records(document["members"]):
        fields(member, "id name created_at")
        mapped = {"id": identity("member", member["id"]),
                  "display_name": text(member["name"], 100),
                  "created_at": timestamp(member["created_at"])}
        members.append(mapped)
        authors[member["id"]] = mapped

    def authored(record, kind):
        require(isinstance(record["author_id"], str) and record["author_id"] in authors,
                "Unknown author ID.")
        author = authors[record["author_id"]]
        created_at = timestamp(record["created_at"])
        require(created_at >= author["created_at"], "History predates its author.")
        return {"id": identity(kind, record["id"]), "body": text(record["body"]),
                "authorship": {"member_id": author["id"], "display_name": author["display_name"]},
                "created_at": created_at}

    contents, comment_count = [], 0
    for post in records(document["posts"]):
        fields(post, "id title body author_id created_at visibility comments")
        require(post["visibility"] == "public", "Only explicitly public posts are supported.")
        content = authored(post, "content")
        content.update(title=text(post["title"], 200), engagement={"views": 0})
        comments, previous_date = [], content["created_at"]
        for sequence, comment in enumerate(records(post["comments"]), 1):
            fields(comment, "id body author_id created_at")
            mapped = authored(comment, "comment")
            require(mapped["created_at"] >= previous_date, "Comments must be chronological after their post.")
            previous_date = mapped["created_at"]
            mapped["sequence"] = sequence
            comments.append(mapped)
        comment_count += len(comments)
        require(comment_count <= 100, "At most 100 comments are supported in total.")
        contents.append({"content": content, "comments": comments})
    counts = dict.fromkeys(("members", "labels", "contents", "comments", "chats",
                            "messages", "assets", "route_aliases", "quarantined"), 0)
    counts.update(members=len(members), contents=len(contents), comments=comment_count)
    report = {"source_system": SOURCE_SYSTEM, "source_id": import_id,
              "source_snapshot_sha256": digest(original), "counts": counts,
              "issue_counts": [], "issues": []}
    content_bytes = encoded(contents)
    batches = [("source", original), ("members", encoded({"members": members, "accounts": []})),
               ("stage-content", content_bytes), ("publish-content", content_bytes),
               ("report", encoded(report))]
    chain = "0" * 64
    for kind, body in batches:
        chain = digest(f"{chain}:{kind}:{digest(body)}".encode())
    declaration = {"source_system": SOURCE_SYSTEM, "source_name": Path(source).name,
                   "source_size": len(original), "source_sha256": digest(original),
                   "batch_count": len(batches), "plan_sha256": chain,
                   "disclosure": "organization_managers"}
    return {"organization": organization, "import_id": import_id,
            "declaration": declaration, "batches": batches, "counts": counts}


def validate_origin(origin):
    try:
        parsed = urlsplit(origin)
        require(parsed.scheme in ("https", "http") and parsed.hostname and
                not parsed.username and not parsed.password and not parsed.path and
                not any(character in origin for character in "?#@\\") and
                not any(character.isspace() or ord(character) < 32 for character in origin),
                "Expected an origin without credentials, path, query or fragment.")
        require(parsed.scheme == "https" or parsed.hostname in ("localhost", "127.0.0.1", "::1"),
                "HTTPS is required except for exact loopback hosts.")
        parsed.port
        return parsed
    except ValueError:
        raise ValueError("Invalid origin; use HTTPS or HTTP on exact loopback hosts.") from None


def read_session(path):
    require(os.name == "posix", "Applying this example requires POSIX session-file permissions.")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and
                info.st_uid == os.getuid(), "Session file must be owned by you, regular and mode 600.")
        token = stream.read(4098).removesuffix(b"\n")
    require(0 < len(token) <= 4096 and all(33 <= byte <= 126 for byte in token),
            "Invalid session file.")
    return token.decode("ascii")


def request(origin, method, path, token=None, body=None, content_type="application/json", status=200):
    connection_type = http.client.HTTPSConnection if origin.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(origin.hostname, origin.port, timeout=30)
    headers = {"Accept": "application/json", "Content-Type": content_type}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    try:
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        require(response.status == status,
                f"Import HTTP {response.status} at {method} {path}; stopped without retry.")
        data = response.read(MAX_RESPONSE + 1)
        require(len(data) <= MAX_RESPONSE, "Import response exceeded 64 KiB.")
        return decoded(data)
    except (OSError, http.client.HTTPException):
        raise ValueError("Import connection failed; stopped without retry.") from None
    finally:
        connection.close()


def check_receipt(receipt, plan, completed):
    require(type(receipt) is dict and receipt.get("id") == plan["import_id"] and
            receipt.get("declaration") == plan["declaration"] and
            receipt.get("completed") is completed, "Invalid import receipt.")
    if completed:
        require(type(receipt.get("next_batch")) is int and
                receipt["next_batch"] == len(plan["batches"]) and
                receipt.get("chain_sha256") == plan["declaration"]["plan_sha256"] and
                receipt.get("source_verified") is True and receipt.get("report_received") is True,
                "Incomplete or mismatched completion receipt.")


def apply_plan(plan, origin, session_file):
    parsed = validate_origin(origin)
    token = read_session(session_file)
    context = request(parsed, "GET", "/api/v1/context")
    require(type(context) is dict and context.get("organization_id") == plan["organization"],
            "Target Organization mismatch; no writes sent.")
    print("Applying history. If this run fails, ordinary access remains fenced.", file=sys.stderr)
    endpoint = "/api/v1/imports/" + plan["import_id"]
    receipt = request(parsed, "PUT", endpoint, token, encoded(plan["declaration"]))
    if type(receipt) is dict and receipt.get("completed") is True:
        check_receipt(receipt, plan, True)
        return receipt
    check_receipt(receipt, plan, False)
    require(type(receipt.get("next_batch")) is int and receipt["next_batch"] == 0,
            "Expected a fresh run; this example does not resume.")
    for sequence, (kind, body) in enumerate(plan["batches"]):
        request(parsed, "PUT", f"{endpoint}/batches/{sequence}/{kind}", token, body,
                "application/octet-stream" if kind == "source" else "application/json", status=202)
    receipt = request(parsed, "POST", endpoint + "/complete", token)
    check_receipt(receipt, plan, True)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).with_name("example.json"))
    parser.add_argument("--import-id", default="fictional-messages-v1")
    parser.add_argument("--organization")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--origin")
    parser.add_argument("--session-file", type=Path)
    args = parser.parse_args(argv)
    if args.apply and not all((args.origin, args.organization, args.session_file)):
        parser.error("--apply requires --origin, --organization and --session-file")
    try:
        plan = build_plan(args.source, args.organization or "example-community", args.import_id)
        counts = plan["counts"]
        print(f"Historical messages · Members: {counts['members']} · Posts: {counts['contents']} · Comments: {counts['comments']}")
        print("Phases: source → members → stage-content → publish-content → report → complete")
        print("Plan SHA-256: " + plan["declaration"]["plan_sha256"])
        if args.apply:
            apply_plan(plan, args.origin, args.session_file)
            print("Import completed.")
        else:
            print("Offline preview. Nothing sent or changed.")
        return 0
    except (ValueError, OSError) as error:
        print("Import stopped: " + (str(error) if isinstance(error, ValueError) else "Cannot read a required file."),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
