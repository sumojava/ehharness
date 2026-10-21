# Security policy

This tool handles API keys, so security reports matter.

To report a vulnerability, please do not open a public issue. Email the maintainer privately at the address on the GitHub profile for sumojava, with the subject line "ehharness security", and describe the problem and steps to reproduce.

Expected handling:
- Keys are stored only in the OS keychain.
- The settings server listens only on 127.0.0.1 and rejects cross-origin requests.
- Key values are never returned to the browser or written to logs.
