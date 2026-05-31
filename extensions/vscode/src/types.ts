export type MindOSEvent = {
  source: "vscode_extension";
  type: string;
  title: string;
  content: string;
  metadata: Record<string, unknown>;
  timestamp: string | null;
  client_id: string;
  session_id: string;
};

export type MindOSConfig = {
  backendUrl: string;
  enabled: boolean;
  clientId: string;
  captureFileOpen: boolean;
  captureFileSave: boolean;
  captureWorkspaceOpen: boolean;
  captureTerminalCommands: boolean;
  includeFileContentOnSave: boolean;
  maxContentChars: number;
  excludeGlobs: string[];
};

export type VSCodeRuntime = {
  id: "vscode";
  enabled: boolean;
  configured: boolean;
  status: string;
  accepted_event_types: string[];
  capture_file_open: boolean;
  capture_file_save: boolean;
  capture_workspace_open: boolean;
  capture_terminal_commands: boolean;
  include_file_content_on_save: boolean;
  max_content_chars: number;
};

export type GitInfo = {
  branch?: string;
  repoRoot?: string;
  repoName?: string;
};

export type QueueFlushResult = {
  sent: number;
  failed: number;
  remaining: number;
};
