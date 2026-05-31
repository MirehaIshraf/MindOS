import * as path from "node:path";
import * as vscode from "vscode";
import type { GitInfo } from "./types";

export async function getGitInfo(resource?: vscode.Uri): Promise<GitInfo> {
  try {
    const gitExtension = vscode.extensions.getExtension("vscode.git");
    const gitApi = gitExtension ? gitExtension.exports?.getAPI?.(1) ?? (await gitExtension.activate()).getAPI(1) : null;
    const repositories = gitApi?.repositories ?? [];
    const repository = repositories.find((repo: { rootUri: vscode.Uri }) => {
      if (!resource) {
        return true;
      }
      return resource.fsPath.toLowerCase().startsWith(repo.rootUri.fsPath.toLowerCase());
    });
    if (!repository) {
      return {};
    }
    const repoRoot = repository.rootUri.fsPath;
    return {
      branch: repository.state?.HEAD?.name,
      repoRoot,
      repoName: path.basename(repoRoot),
    };
  } catch {
    return {};
  }
}
