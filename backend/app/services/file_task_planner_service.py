from pathlib import Path
from uuid import uuid4

from app.schemas.file_tasks import FileOperation, FileSnapshotItem, FileTaskPlan, FileTaskPrepareRequest, SkippedFileItem
from app.services.file_snapshot_service import file_snapshot_service
from app.services.file_task_safety_service import file_task_safety_service


TYPE_FOLDERS = {
    "PDFs": {".pdf"},
    "Images": {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp"},
    "Videos": {".mp4", ".mov", ".avi", ".mkv", ".webm"},
    "Audio": {".mp3", ".wav", ".m4a", ".flac", ".aac"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "Installers": {".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm"},
    "Code": {".py", ".java", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".xml", ".yml", ".yaml"},
    "Documents": {".doc", ".docx", ".txt", ".md", ".rtf"},
    "Spreadsheets": {".xls", ".xlsx", ".csv"},
    "Presentations": {".ppt", ".pptx"},
}


class FileTaskPlannerService:
    def prepare_deterministic_file_plan(self, request: FileTaskPrepareRequest) -> FileTaskPlan:
        snapshot = file_snapshot_service.scan_folder(
            root_path=request.root_path,
            max_depth=request.max_depth,
            max_files=request.max_files,
            include_hidden=request.include_hidden,
        )
        root = Path(snapshot.root_path).resolve()
        include_others = should_include_others(request.instruction)

        category_counts: dict[str, int] = {}
        skipped: list[SkippedFileItem] = []
        move_operations: list[FileOperation] = []
        destination_folders: set[str] = set()

        for item in snapshot.files:
            category = folder_for_extension(item.extension, include_others=include_others)
            if category is None:
                skipped.append(to_skipped(item, "Unknown file type."))
                continue
            category_counts[category] = category_counts.get(category, 0) + 1
            source = Path(item.path).resolve()
            destination_folder = root / category
            destination = destination_folder / source.name

            if is_already_organized(source, destination_folder):
                skipped.append(to_skipped(item, "Already organized."))
                continue
            if destination.exists():
                skipped.append(to_skipped(item, "Destination already exists. No overwrite allowed."))
                continue

            destination_folders.add(category)
            move_operations.append(
                FileOperation(
                    type="move_file",
                    tool="file.move_file",
                    from_path=str(source),
                    to_path=str(destination),
                    relative_from=str(source.relative_to(root)),
                    relative_to=str(destination.relative_to(root)),
                    reason=f"{category_singular(category)} file should be grouped under {category}.",
                )
            )

        create_operations: list[FileOperation] = []
        for category in sorted(destination_folders):
            folder_path = root / category
            if folder_path.exists():
                continue
            create_operations.append(
                FileOperation(
                    type="create_folder",
                    tool="file.create_folder",
                    path=str(folder_path),
                    relative_to=str(folder_path.relative_to(root)),
                    reason=f"Create {category} folder for organized files.",
                )
            )

        operations = assign_operation_ids([*create_operations, *move_operations])
        validation = file_task_safety_service.validate_plan(str(root), operations)
        blocked_reasons = validation["blocked_reasons"]
        warnings = [*snapshot.warnings, *validation["warnings"]]
        status = status_for_plan(operations, blocked_reasons, skipped)

        return FileTaskPlan(
            task_id=str(uuid4()),
            root_path=str(root),
            instruction=request.instruction,
            summary=build_summary(move_operations, category_counts),
            risk_level="low" if len(operations) <= 100 else "medium",
            requires_confirmation=True,
            operations=operations,
            folders_to_create=create_operations,
            files_to_move=move_operations,
            skipped=skipped,
            warnings=dedupe(warnings),
            blocked_reasons=dedupe(blocked_reasons),
            status=status,
            total_operations=len(operations),
            create_folder_count=len(create_operations),
            move_file_count=len(move_operations),
            copy_file_count=0,
            rename_file_count=0,
            category_counts=category_counts,
            preview_only=True,
            planner_model=None,
            planner_provider=None,
            planner_warning="Deterministic preview only. No LLM planner was used.",
        )

    def plan(self, *, root_path: str, instruction: str, snapshot=None, model_id: str | None = None) -> FileTaskPlan:
        return self.prepare_deterministic_file_plan(
            FileTaskPrepareRequest(root_path=root_path, instruction=instruction)
        )


def folder_for_extension(extension: str, *, include_others: bool) -> str | None:
    ext = extension.lower()
    for folder, extensions in TYPE_FOLDERS.items():
        if ext in extensions:
            return folder
    return "Other" if include_others and ext else None


def should_include_others(instruction: str) -> bool:
    text = instruction.lower()
    return "unknown" in text or "others" in text or "other files" in text


def is_already_organized(source: Path, destination_folder: Path) -> bool:
    return source.parent.resolve() == destination_folder.resolve()


def to_skipped(item: FileSnapshotItem, reason: str) -> SkippedFileItem:
    return SkippedFileItem(path=item.path, relative_path=item.relative_path, reason=reason)


def assign_operation_ids(operations: list[FileOperation]) -> list[FileOperation]:
    output: list[FileOperation] = []
    for index, operation in enumerate(operations, start=1):
        output.append(operation.model_copy(update={"id": f"op_{index:03d}", "status": operation.status or "planned"}))
    return output


def status_for_plan(operations: list[FileOperation], blocked_reasons: list[str], skipped: list[SkippedFileItem]) -> str:
    if blocked_reasons:
        return "blocked"
    if operations:
        return "awaiting_confirmation"
    return "empty"


def build_summary(move_operations: list[FileOperation], category_counts: dict[str, int]) -> str:
    if not move_operations:
        return "No file moves are needed for this folder."
    categories = sorted(category_counts)
    category_text = ", ".join(categories[:5])
    if len(categories) > 5:
        category_text += f", and {len(categories) - 5} more"
    return f"Organize {len(move_operations)} files into {len(categories)} folders by file type: {category_text}."


def category_singular(category: str) -> str:
    if category == "PDFs":
        return "PDF"
    if category.endswith("s"):
        return category[:-1]
    return category


def dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value not in output:
            output.append(value)
    return output


file_task_planner_service = FileTaskPlannerService()
