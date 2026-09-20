# A small, runnable import example

Read `README.md`, `example.json`, `import_example.py`, then the tests. This is a
teaching example using fictional public data, not a complete migration tool.

- Keep Python standard-library-only, explicit, and easy to read. Do not add an
  SDK, database, service, plugin system, or generic migration framework.
- Preserve the offline default. Only explicit `--apply` may write to a server.
- Preserve original bytes, deterministic IDs, exact ordered batch digests,
  bounded input/network work, and completed-receipt verification.
- Use only the public import REST API with a current human Manager session.
  Never introduce direct storage writes, credential bootstrapping, auth bypasses,
  automatic retries, or saved-position recovery.
- Keep sample data fictional. Never commit tokens, real exports, or account data.
- Reject unsupported input rather than silently discarding records or widening
  private access. Historical Members do not gain sign-in or Manager authority.
- Read the target community's `/openapi.json` before extending request shapes.
  The public reference is https://github.com/basstok/api.
- Public documentation describes this example and public API behavior only.
  Never disclose Basstok's private implementation languages, technology stack,
  infrastructure, installation procedures, or deployment details, including in
  commit messages, issue text, workflow output, or repository metadata.
- Run `python3 -m unittest discover -s tests -v` and
  `python3 import_example.py`. Neither command should use the network.
- Do not run `--apply` against a real community without explicit authorization.

Explain a source mapping with small examples. Keep the README's first experience
short, inviting, and truthful; place unusual migration details after the demo.
