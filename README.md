# remaju

A collector for Peru's REMAJU judicial auction listings and a static web explorer for the collected data.

## Data

- [Explorer](https://remaju.mejora.me/)
- [Available auctions (JSON)](https://data.remaju.mejora.me/available.json)
- [Auction history (JSON)](https://data.remaju.mejora.me/history.json)

## Usage

Everything runs through the Makefile:

```sh
make help
```

## Source verification

Blocked refreshes preserve published data and record the verification provider in the run trace and Actions summary. A separate, credential-free Chromium job checks whether normal browser navigation works and whether an explicit CAPTCHA is present.

This diagnostic never solves CAPTCHAs, resumes collection, or publishes data. Its `browser-verification-*` artifact contains only `browser-probe.json`, without browser cookies, page HTML, or screenshots.
