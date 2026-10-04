# Bring your community. Keep its history.

Move existing discussions into [Basstok](https://basstok.com/) through an ordinary
HTTPS API. Your importer reads the old data; Basstok handles storage and permissions.
This small Python example is ready to read, run, and adapt.

**[Try the Python example](#try-it-in-one-minute)** ·
[Import XenForo 2](#import-xenforo-2) · [API reference](https://github.com/basstok/api)

## Try it in one minute

A **fictional conversation**: two Members, one post, and one Comment, with their
original authors and dates. Python 3.10 or later. No packages or account needed.

```sh
git clone https://github.com/basstok/import.git
cd import
python3 import_example.py
```

**The default is a local preview. No network requests. Nothing changes.**

Read [the fictional export](example.json), then [the Python importer](import_example.py).
There is no SDK or framework to learn:

```text
Read the export → map the records → preview → send through REST
```

| Old data | Basstok |
| --- | --- |
| People | Members |
| Posts | Content |
| Replies | Comments owned by their Content |

Historical Members are **not sign-in credentials**. Posts do not need Labels.
Bodies use CommonMark Markdown. No source roles or private access rules are invented.

## Import into a test community

Use a separate, disposable community, its exact Organization ID, and a **current
human Admin session**. App/OAuth tokens cannot import. Obtain a session using
the authentication supported by that community; the example adds no login system.

Save the token in a private file outside this repository. Never put it in command
arguments, source code, screenshots, or public issues.

```sh
chmod 600 /private/admin-session
python3 import_example.py \
  --organization YOUR_ORGANIZATION_ID \
  --origin https://community.example \
  --session-file /private/admin-session \
  --apply
```

Only `--apply` writes. The importer checks the hostname's Organization first.

**An unfinished import can make ordinary community access unavailable until the
same import completes.** Keep the source and options unchanged. After an error,
deliberately rerun the entire command; do not change the recipe or invent a new
import ID. There are no automatic retries or saved positions. HTTP `202` means
received, not completed.

## The whole protocol

```text
GET  /api/v1/context                                  check the Organization
PUT  /api/v1/imports/{importId}                        declare the recipe
PUT  /api/v1/imports/{importId}/batches/{sequence}/{kind}
     source → members → stage-content
            → publish-content → report               send in order from zero
POST /api/v1/imports/{importId}/complete                require completed: true
```

- **Stable IDs:** the same source IDs, Organization and import ID produce the same
  opaque Member, Content and Comment IDs.
- **Original evidence:** the first batch preserves the exact source bytes.
- **One recipe:** a SHA-256 chain binds the ordered batch bodies before writing.
- **One boundary:** every import request uses the public, Admin-authorized API.

The [import guide](https://github.com/basstok/api/blob/main/reference.md#import-existing-data)
and [OpenAPI contract](https://github.com/basstok/api/blob/main/openapi.json) describe
the larger API. A community's `/openapi.json` is authoritative for its installed
release; check it before adapting the example.

### Small on purpose

This accepts only its fictional JSON shape. It does **not** parse XenForo SQL,
convert BBCode, map permissions, import private discussions or media, or preserve
old URLs. Unsupported fields are rejected, not silently discarded. Small input
limits keep the example readable; they are not Basstok capacity limits.

To adapt it, replace the source transformation, not the REST protocol. Never make
private data public to fit the example. Content is staged before publication even
without media. For Assets, upload them after staging their owner and before
publishing it. This text-only example keeps those two Content batches identical.

**Using an AI assistant?** Start with [AGENTS.md](AGENTS.md), the fictional input,
and the importer. This is a source-to-domain mapping, not a new backend.

```sh
python3 -m unittest discover -s tests -v
```

These checks are offline, not evidence of a production migration.

## Import XenForo 2

For an actual XenForo community, use the **XenForo 2.0–2.3** import workflow.
Sign in as an Admin and open
**Administration → Import**.

1. Upload your **SQL** export.
2. Add **data/** and **internal_data/** for supported avatars and attachments.
3. Choose **Upload files**, then **Start import**.

Use raw `.sql`, or a ZIP with one SQL file at its top level:

```text
backup.zip
├── community.sql
├── data/             optional
└── internal_data/    optional
```

Separate media ZIPs must contain their named folder. Do not add an outer folder.
Keep the original export private and unchanged.

Threads become Content with Comments. Supported authorship, dates, Chats and
legacy public routes can be retained. Review reported mapping losses, member
authority, private areas, media and old links before cutover. Unsupported or
missing media and unresolved access mappings need particular attention; this is
not a promise of lossless conversion. Source passwords do not carry over.

## Before moving real history

Keep a private backup and the old site running while you test. Inspect familiar
discussions as both ordinary and privileged Members. Consider pausing optional
activity notifications. Freeze source changes before the final export; imports
are not continuous synchronization.

---

[Explore Basstok](https://basstok.com/) ·
[Your data and storage](https://github.com/basstok/storage) ·
[Ask about an import](mailto:mail@basstok.com) · [MIT](LICENSE)

Never attach real exports, private messages, or credentials to public issues.
