# UN Comtrade JSON response

The controlled development fixtures contain the complete, small JSON response
envelopes returned for Tunisia's annual SITC Rev.4 total imports from World for
2022, 2023, and 2024. They are preserved as canonical UTF-8 JSON so fixture
changes and checksums are deterministic and reviewable.

## Provider HTTP behavior

HTTP `200` was returned for each of the three tested requests, and each body
contained valid JSON with one observation. The `Content-Type` response header
was absent in these tested responses.

Clients therefore verify these responses by successfully parsing the body as
JSON rather than depending only on the HTTP `Content-Type` header. This records
observed behavior for these specific UN Comtrade preview requests; it does not
imply that every UN Comtrade endpoint or response omits `Content-Type`.
