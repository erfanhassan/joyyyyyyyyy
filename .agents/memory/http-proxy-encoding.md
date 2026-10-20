---
name: HTTP proxy encoding integrity
description: Preserve compressed response bytes and their encoding metadata together across the Python authentication proxy.
---

Proxy response bytes and Content-Encoding must stay consistent. When forwarding a browser's Accept-Encoding, do not assume the Python HTTP client can decompress every requested codec.

**Why:** The published sign-in page went blank even though health checks and script requests returned 200. Browser-requested compression produced a JavaScript payload that the proxy forwarded without its encoding header; ordinary uncompressed checks did not expose the failure.

**How to apply:** Buffer raw upstream bytes with the matching encoding header, and test raw responses for gzip, Brotli and Zstandard. When diagnosing an authentication blank screen, inspect the actual production browser error and script response, not only the development sign-in page.
