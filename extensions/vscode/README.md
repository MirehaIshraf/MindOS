# MindOS VSCode Connector

The MindOS VSCode Connector sends selected local editor activity to your local MindOS backend. The MindOS app toggle is the source of truth: install the extension once, then turn collection on or off from the MindOS Connectors page.

## Install Locally

```powershell
npm install
npm run compile
npm run package
code --install-extension mindos-vscode-0.1.0.vsix
```

## Demo Flow

1. Start the MindOS backend.
2. Start the MindOS frontend.
3. Install the VSCode extension.
4. Open normal VSCode.
5. Open a workspace.
6. In MindOS, go to Connectors.
7. Toggle VSCode on.
8. Save a file in VSCode.
9. See the event in MindOS Memory and Connectors.

No debugger or Extension Development Host is required for the normal demo.

## What It Captures By Default

- Workspace opened.
- File saved.
- Lightweight metadata such as workspace name, relative path, language, repo name, and Git branch when available.

## What It Does Not Capture By Default

- File open events.
- Terminal commands.
- Full file content.
- Secrets.

## Privacy

- Data is sent only to the local MindOS backend configured by `mindos.backendUrl`.
- File contents are off by default.
- `.env`, private keys, build folders, virtualenvs, `.git`, and `node_modules` are ignored by default.
- Even when content capture is enabled, obvious secret markers and private key content are blocked.
- `mindos.enabled` is a local emergency kill switch. When false, the extension sends no events even if the MindOS backend connector is enabled.

## Runtime Behavior

- The extension polls `GET /connectors/vscode/runtime` every 5 seconds.
- It sends `POST /connectors/vscode/heartbeat` every 30 seconds while active.
- Heartbeats update connector status only; they do not create memory events.
- When the MindOS app toggle changes from off to on, the installed extension detects it and sends the current workspace event without reopening VSCode.

## Commands

- `MindOS: Test Connection`
- `MindOS: Open MindOS`
- `MindOS: Open Settings`
- `MindOS: Enable Local Collection`
- `MindOS: Disable Local Collection`
- `MindOS: Flush Queue`

The status bar shows:

- `MindOS: Connected`
- `MindOS: Off`
- `MindOS: Offline`

## Development

Use F5 only when developing the extension itself. For product demos, install the packaged VSIX into normal VSCode.
