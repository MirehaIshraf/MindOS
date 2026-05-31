# MindOS Browser Connector

The MindOS Browser Connector lets you manually save useful pages, notes, and selected text into local MindOS memory.

## What It Captures

- Current page title, URL, and domain.
- Optional selected text when you click the extension popup.
- Optional note you type before saving.

## What It Does Not Capture

- Browsing history.
- Background tab changes.
- Full page text by default.
- Password fields or browser-internal pages.

## Privacy

The connector is manual and local-first. It only sends data when you click **Save to MindOS**, and it sends data only to your configured local MindOS backend. The extension does not request browser history permission.

Blocked page schemes include `chrome://`, `edge://`, `about:`, and `file:`. Sensitive domains such as mail, account, banking, billing, and payment pages show a warning before save.

## Install Locally

From this folder:

```bash
npm install
npm run build
```

Then in Chrome or Edge:

1. Open the Extensions page.
2. Enable Developer mode.
3. Choose **Load unpacked**.
4. Select `extensions/browser`.

## Demo Flow

1. Start the MindOS backend and frontend.
2. In MindOS, go to Connectors and toggle **Browser** on.
3. Open a useful web page.
4. Select text if you want to include it.
5. Click the MindOS extension icon.
6. Add an optional note.
7. Click **Save to MindOS**.
8. Check Memory and filter by Browser.

## Settings

The popup includes the backend URL. The default is:

```text
http://localhost:8000
```

Browser connector collection is controlled by the MindOS Connectors page toggle. If Browser is off in MindOS, saves are rejected with a clear message.

## Build Commands

```bash
npm run build
npm run watch
npm run zip
```

The zip command creates `mindos-browser-0.1.0.zip` for manual distribution.

## Troubleshooting

- **Offline**: confirm MindOS backend is running at the configured backend URL.
- **Connector disabled**: toggle Browser on from the MindOS Connectors page.
- **Cannot save this page**: browser-internal and local file pages are intentionally blocked.
