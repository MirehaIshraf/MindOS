# MindOS Browser Connector

The MindOS Browser Connector lets you save useful pages, notes, selected text, and privacy-filtered research activity into local MindOS memory.

## What It Captures

- Current page title, URL, and domain.
- Optional selected text when you click the extension popup.
- Optional note you type before saving.
- In Smart capture mode, search queries and important developer/research pages after a short active dwell time.
- Readable page context for captured important pages, including headings and visible text excerpts when extraction succeeds.
- Repeat visits to the same important page update the same MindOS memory item instead of creating duplicate visible captures.

## What It Does Not Capture

- Browsing history.
- Full unrestricted browsing history.
- Full page text by default.
- Raw HTML, forms, password fields, or input values.
- Password fields or browser-internal pages.
- Private/login/payment pages.
- YouTube/social/entertainment feeds by default.

## Privacy

The connector is local-first and sends data only to your configured local MindOS backend. The extension does not request browser history permission.

Manual mode only sends data when you click **Save to MindOS** or **Capture this page**. Smart capture mode runs in the background, observes the active tab, waits for dwell time, and filters aggressively before sending anything.

Blocked page schemes include `chrome://`, `edge://`, `about:`, and `file:`. Sensitive domains such as mail, account, banking, billing, login, and payment pages are blocked or warned on manual save. Smart capture ignores noisy/private domains by default.

## Capture Modes

- **Manual only**: save pages only when you click the popup button.
- **Smart capture**: automatically records search queries and important developer/research pages after dwell time.
- **Off**: the extension does not capture browser events.

Change the mode from MindOS -> Connectors -> Browser -> Configure.

Important pages include developer docs, GitHub, patents/research pages, and Hugging Face model/dataset/docs pages. Manual capture uses the same generic visible-text extraction path as smart capture.

Captured pages include meta description, headings, selected text, readable visible text excerpts, and extraction diagnostics when available. MindOS does not run an LLM automatically for browser pages.

If extraction fails, the event can still save the page title and URL, but MindOS marks it as `page_context_missing=true` and does not treat the placeholder message as captured page text or pending summary material.

Use **Debug extraction** -> **Test DOM access** in the popup first. This runs a direct `chrome.scripting.executeScript` check against `document.body.innerText`. If `bodyTextLength` is `0` or an error is shown, reload the extension in `chrome://extensions`, check permissions, and confirm the page is not a restricted browser/internal URL.

Use **Debug extraction** -> **Test actual capture extraction** after DOM access works. This runs the same `extractReadablePageContext()` path used by manual and smart capture, and shows the readable extractor result, selected selector, candidate lengths, preview, and any extraction error. Placeholder failure text does not count as captured content.

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

After rebuilding, go to `chrome://extensions` and click **Reload** on the MindOS extension before testing. Reopen the target page after reload so the current build and permissions are active.

## Demo Flow

1. Start the MindOS backend and frontend.
2. In MindOS, go to Connectors and toggle **Browser** on.
3. Choose **Manual only** or **Smart capture** in the Browser connector settings.
4. Open a useful web page.
5. Select text if you want to include it.
6. Click the MindOS extension icon.
7. Add an optional note.
8. Click **Save to MindOS**.
9. Check Memory and filter by Browser.

In Smart capture mode, try a developer/research page such as a GitHub repository, docs page, or Hugging Face dataset page and keep it active for the configured dwell time. You do not need to open the popup for automatic capture.

## Settings

The popup includes the backend URL. The default is:

```text
http://localhost:8000
```

Browser connector collection is controlled by the MindOS Connectors page toggle. If Browser is off in MindOS, saves are rejected with a clear message.

Smart capture settings are also controlled from MindOS:

- Capture search queries
- Capture important pages
- Capture page context
- Max context characters
- Ignored domains
- Important domains

Smart capture needs host permission for normal `http://` and `https://` pages so it can run the same safe DOM extraction used by manual capture. The extension still does not request browser history, cookies, or webRequest permissions.

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
- **Could not extract page text**: open the popup, expand **Debug extraction**, and click **Test DOM access**. If `bodyTextLength` is `0` or an error appears, reload the extension in `chrome://extensions`, check page permissions, and avoid restricted pages such as `chrome://`, `edge://`, `about:`, `file:`, and extension pages. If DOM access works but **Test actual capture extraction** has no text, the generic extractor logic needs debugging.
