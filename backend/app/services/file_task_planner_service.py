import json
import re
from pathlib import Path
from uuid import uuid4

from app.schemas.file_tasks import FileOperation, FileSnapshotResponse, FileTaskPlan, SkippedFileItem
from app.services.model_router_service import model_router_service

TYPE_FOLDERS = {
    "PDFs": {".pdf"},
    "Images": {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"},
    "Videos": {".mp4", ".mov", ".avi", ".mkv", ".webm"},
    "Audio": {".mp3", ".wav", ".m4a", ".flac"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "Installers": {".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm"},
    "Code": {".py", ".java", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".xml", ".yml", ".yaml"},
    "Documents": {".doc", ".docx", ".txt", ".md", ".rtf"},
    "Spreadsheets": {".xls", ".xlsx", ".csv"},
    "Presentations": {".ppt", ".pptx"},
}


class FileTaskPlannerService:
    def plan(self, *, root_path: str, instruction: str, snapshot: FileSnapshotResponse, model_id: str | None = None) -> FileTaskPlan:
        llm_plan, warning, model, provider = self._try_llm_plan(root_path, instruction, snapshot, model_id)
        if llm_plan is not None:
            llm_plan.planner_warning = warning
            llm_plan.planner_model = model
            llm_plan.planner_provider = provider
            return llm_plan
        plan = self._deterministic_plan(root_path, instruction, snapshot)
        plan.planner_warning = warning or "Used deterministic file organization fallback."
        plan.planner_model = model
        plan.planner_provider = provider
        return plan

    def _try_llm_plan(
        self,
        root_path: str,
        instruction: str,
        snapshot: FileSnapshotResponse,
        model_id: str | None,
    ) -> tuple[FileTaskPlan | None, str | None, str | None, str | None]:
        compact_files = [
            {
                "path": item.path,
                "relative_path": item.relative_path,
                "extension": item.extension,
                "size_bytes": item.size_bytes,
            }
            for item in snapshot.files[:200]
        ]
        prompt = (
            "You are creating a safe local file organization plan. Return JSON only. "
            "Allowed operations: create_folder, move_file, copy_file, rename_file. "
            "Never delete, overwrite, execute, edit content, or move outside root. "
            "Use only files from the provided snapshot. If unsure, skip.\n\n"
            f"Root: {root_path}\nInstruction: {instruction}\nFiles: {json.dumps(compact_files)}\n\n"
            "Return keys: summary, risk_level, operations, skipped, warnings."
        )
        try:
            result = model_router_service.generate(
                messages=[
                    {"role": "system", "content": "Return strict JSON only. No markdown."},
                    {"role": "user", "content": prompt},
                ],
                requested_model_id=model_id,
                options={"temperature": 0},
            )
            data = parse_json_object(result.reply)
            operations = [FileOperation(**operation) for operation in data.get("operations", []) if isinstance(operation, dict)]
            skipped = [SkippedFileItem(**item) for item in data.get("skipped", []) if isinstance(item, dict)]
            if not operations:
                return None, result.warning or "Planner returned no operations; using deterministic fallback.", result.model_used, result.provider
            return (
                FileTaskPlan(
                    task_id=str(uuid4()),
                    root_path=root_path,
                    instruction=instruction,
                    summary=str(data.get("summary") or "Prepared file organization task."),
                    risk_level=data.get("risk_level") if data.get("risk_level") in {"low", "medium", "high"} else "medium",
                    operations=operations,
                    skipped=skipped,
                    warnings=[str(item) for item in data.get("warnings", []) if item],
                    status="draft",
                    planner_model=result.model_used,
                    planner_provider=result.provider,
                    planner_warning=result.warning,
                ),
                result.warning,
                result.model_used,
                result.provider,
            )
        except Exception as error:
            return None, f"LLM planner unavailable or invalid; using deterministic fallback. {error}", None, None

    def _deterministic_plan(self, root_path: str, instruction: str, snapshot: FileSnapshotResponse) -> FileTaskPlan:
        text = instruction.lower()
        operations: list[FileOperation] = []
        skipped: list[SkippedFileItem] = []
        organize_by_type = any(phrase in text for phrase in ["organize by file type", "organize this folder", "sort by type", "by file type"])
        if not organize_by_type:
            return FileTaskPlan(
                task_id=str(uuid4()),
                root_path=root_path,
                instruction=instruction,
                summary="No deterministic planner matched this instruction.",
                risk_level="medium",
                operations=[],
                skipped=[SkippedFileItem(path=item.path, reason="No matching deterministic rule") for item in snapshot.files[:50]],
                warnings=["Try: Organize this folder by file type."],
                blocked_reasons=[],
                status="blocked",
            )
        root = Path(root_path).resolve()
        folders_needed: set[str] = set()
        moves: list[tuple[str, str, str]] = []
        include_others = "others" in text or "unknown" in text
        for item in snapshot.files:
            folder = folder_for_extension(item.extension, include_others=include_others)
            if folder is None:
                skipped.append(SkippedFileItem(path=item.path, reason="No matching file type rule"))
                continue
            source = Path(item.path).resolve()
            destination = root / folder / source.name
            if source.parent == root / folder:
                skipped.append(SkippedFileItem(path=item.path, reason="Already in target folder"))
                continue
            folders_needed.add(folder)
            moves.append((item.path, str(destination), folder))
        for folder in sorted(folders_needed):
            operations.append(FileOperation(type="create_folder", path=str(root / folder), reason=f"Create {folder} folder."))
        for source, destination, folder in moves:
            operations.append(FileOperation(type="move_file", from_path=source, to_path=destination, reason=f"Move into {folder}."))
        return FileTaskPlan(
            task_id=str(uuid4()),
            root_path=str(root),
            instruction=instruction,
            summary="Organize files by type.",
            risk_level="low" if len(operations) <= 100 else "medium",
            operations=operations,
            skipped=skipped,
            warnings=[],
            status="draft",
        )


def folder_for_extension(extension: str, *, include_others: bool) -> str | None:
    ext = extension.lower()
    for folder, extensions in TYPE_FOLDERS.items():
        if ext in extensions:
            return folder
    return "Others" if include_others and ext else None


def parse_json_object(value: str) -> dict:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("Planner did not return JSON.")
    return json.loads(match.group(0))


file_task_planner_service = FileTaskPlannerService()
