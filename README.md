# Bring your community to Basstok

Bring the discussions, members and history you have built into
[Basstok](https://basstok.com/), with publishing, private messaging, voice and
video calls, native apps and your own web presence.

**XenForo 2 imports are built in.** Other platforms can connect through the
[public import API](https://github.com/basstok/api/blob/main/reference.md#import-existing-data)
with a source-specific adapter.

[Start with Basstok](https://basstok.com/start) ·
[Import XenForo 2](#import-xenforo-2) ·
[Another platform](#another-platform)

## A good move starts with a copy

1. **Keep your original backup.** Export the database and its media files
   together. Keep these private; they may contain private messages and personal data.
2. **Try a separate Basstok first.** Leave the current site running while you
   check the import. Use a private audience and pause activity notifications
   in Administration while testing.
3. **Check the things that matter.** Open familiar discussions, older replies,
   images and links. Review member roles and private areas with appropriate
   accounts. Source permissions and extensions do not always map one-for-one.
4. **Choose your cutover.** Pause changes on the old site before taking the
   final export. Import it into a fresh Basstok, check the result, then connect
   your domain and invite members. This is an import, not continuous synchronization.

## Import XenForo 2

Basstok supports exports from **XenForo 2.0–2.3**. Sign in as a Manager and open
**Administration → Import**.

1. Upload your **SQL** database export — required.
2. Add **data/** and **internal_data/** — optional, for supported avatars
   and attachments.
3. Choose **Upload files**, then **Start import**, and follow progress in Administration.

Use a raw `.sql` file, or a ZIP with one SQL file at its top level:

```text
backup.zip
├── community.sql
├── data/             optional
└── internal_data/    optional
```

You can also upload `data/` and `internal_data/` as separate ZIPs, each containing
its named folder. Fill or replace the uploads before starting. Do not wrap the
backup in an extra outer folder.

Threads become posts with replies; forum names can become topics. The importer
preserves supported member identities, authorship, dates, private messages and
public URL paths, including supported pagination and reply links. Keeping your
old domain lets those preserved paths keep the same full address.

<details>
<summary>What to check before going live</summary>

- Review reported issues and sample your imported discussions and media.
- Check roles and private areas. Unsupported access rules may leave content
  more restricted; custom extensions and markup may need attention.
- Check attachments and avatars. Unsupported or missing media, files over the
  current 8 MiB per-file limit, and media whose access cannot be mapped safely
  may be left out.
- Members use Basstok sign-in. Existing XenForo passwords do not carry over;
  check that members have usable email addresses.

</details>

## Another platform

A developer can build an adapter that translates another platform's export
into members, posts, replies, private chats, media and public links. It submits
that data through the same **HTTPS/JSON import API** used by the XenForo importer.

XenForo 2 is ready to use today; other platforms need an adapter. Imports require
a current human Manager session, not an Agent token.

[Import API guide](https://github.com/basstok/api/blob/main/reference.md#import-existing-data) ·
[OpenAPI contract](https://github.com/basstok/api/blob/main/openapi.json)

---

[Explore Basstok](https://basstok.com/) ·
[Your data and storage](https://github.com/basstok/storage) ·
[Ask about an import](mailto:mail@basstok.com)

Please do not attach database exports, private messages or credentials to public
GitHub issues.
