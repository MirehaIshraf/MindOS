import json
import re
from uuid import uuid4

from app.schemas.file_tasks import (
    BrowserFilePlanSnapshotItem,
    FileOperation,
    FileTaskLlmPlanRequest,
    FileTaskPlan,
    SkippedFileItem,
)
from app.services.file_task_planner_service import TYPE_FOLDERS
from app.services.model_router_service import model_router_service


ALLOWED_BROWSER_PLAN_OPERATIONS = {"create_folder", "move_file"}
MOVE_CATEGORY_ALIASES = {
    "Installers": {"installer", "installers", "setup", "setups", "exe", "msi", "dmg"},
    "PDFs": {"pdf", "pdfs"},
    "Images": {"image", "images", "photo", "photos", "picture", "pictures", "screenshot", "screenshots"},
    "Videos": {"video", "videos"},
    "Audio": {"audio", "music", "sound"},
    "Archives": {"archive", "archives", "zip", "zips", "compressed"},
    "Documents": {"document", "documents", "docs", "office", "office files"},
    "Code": {"code", "developer", "source"},
    "Spreadsheets": {"spreadsheet", "spreadsheets", "excel", "csv"},
    "Presentations": {"presentation", "presentations", "slides", "powerpoint"},
}
FORBIDDEN_INSTRUCTION_TERMS = {
    "delete",
    "remove unnecessary",
    "remove all",
    "overwrite",
    "replace",
    "run ",
    "execute",
    "shell",
    "script",
}


class FileTaskLlmPlannerService:
    def plan_browser_file_task(self, request: FileTaskLlmPlanRequest) -> FileTaskPlan:
        if self._looks_unsafe(request.instruction):
            return self._blocked_plan(
                request,
                "This instruction asks for an unsafe operation. File task planning only allows creating folders and moving files.",
            )

        fallback = self._deterministic_plan(request, warning="AI planner unavailable. Using safe deterministic plan.")
        try:
            result = model_router_service.generate(
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": json.dumps(self._planner_payload(request), ensure_ascii=False)},
                ],
                requested_model_id=request.model_id,
                options={"temperature": 0.1},
            )
        except Exception:
            return fallback

        if result.provider == "fake":
            fallback.planner_warning = result.warning or fallback.planner_warning
            return fallback

        raw_plan = self._parse_json(result.reply)
        if raw_plan is None:
            fallback.planner_warning = "AI planner failed, so MindOS used a safe exact-intent fallback."
            fallback.planner_model = result.model_used
            fallback.planner_provider = result.provider
            return fallback

        plan = self._validated_plan_from_llm(request, raw_plan)
        plan.planner_model = result.model_used
        plan.planner_provider = result.provider
        if result.warning:
            plan.warnings.append(result.warning)
        return plan

    def _system_prompt(self) -> str:
        return (
            "You create safe local file organization plans. Return JSON only. "
            "Use only allowed operations: create_folder and move_file. "
            "Use only files from the provided list. Use relative paths only. "
            "All destinations must stay inside the selected folder. Never overwrite existing files. "
            "Never delete, edit, execute, run shell commands, read file contents, or move folders. "
            "If unsure, skip the file. Do not include markdown or explanations outside JSON."
        )

    def _planner_payload(self, request: FileTaskLlmPlanRequest) -> dict:
        files = [
            {
                "name": item.name,
                "relative_path": self._normalize_relative(item.relative_path),
                "extension": item.extension.lower(),
                "size_bytes": item.size_bytes,
                "modified_at": item.modified_at,
                "category": item.category or self._category_for_extension(item.extension),
            }
            for item in request.files[: request.max_operations]
            if not item.is_hidden
        ]
        folders = [
            {"name": folder.name, "relative_path": self._normalize_relative(folder.relative_path)}
            for folder in request.folders
            if not folder.is_hidden
        ]
        return {
            "instruction": request.instruction,
            "root_name": request.root_name,
            "files": files,
            "folders": folders,
            "allowed_operations": ["create_folder", "move_file"],
            "forbidden_operations": [
                "delete_file",
                "overwrite_file",
                "edit_file",
                "run_shell",
                "execute_file",
                "move_outside_selected_folder",
                "read_file_content",
                "upload_file_content",
            ],
            "rules": [
                "Use only files from the provided list.",
                "Use relative paths only.",
                "All destinations must stay inside selected folder.",
                "Never overwrite existing files.",
                "If unsure, skip the file.",
            ],
            "expected_json_shape": {
                "summary": "Move AI-related PDFs into an AI Research folder.",
                "risk_level": "low",
                "operations": [
                    {"type": "create_folder", "relative_path": "AI Research", "reason": "Folder requested by user."},
                    {
                        "type": "move_file",
                        "from_relative_path": "transformer_attention.pdf",
                        "to_relative_path": "AI Research/transformer_attention.pdf",
                        "reason": "Filename appears related to AI research.",
                    },
                ],
                "skipped": [{"relative_path": "invoice.pdf", "reason": "Not related to AI research."}],
                "warnings": [],
            },
        }

    def _validated_plan_from_llm(self, request: FileTaskLlmPlanRequest, raw_plan: dict) -> FileTaskPlan:
        existing_files = {self._normalize_relative(item.relative_path): item for item in request.files if not item.is_hidden}
        existing_folders = {self._normalize_relative(folder.relative_path) for folder in request.folders if not folder.is_hidden}
        planned_destinations: set[str] = set()
        operations: list[FileOperation] = []
        skipped: list[SkippedFileItem] = []
        blocked_reasons: list[str] = []
        warnings = [str(warning) for warning in raw_plan.get("warnings", []) if str(warning).strip()]

        for index, raw_operation in enumerate(raw_plan.get("operations", [])[: request.max_operations], start=1):
            operation_type = str(raw_operation.get("type", "")).strip()
            if operation_type not in ALLOWED_BROWSER_PLAN_OPERATIONS:
                blocked_reasons.append(f"Operation {index}: forbidden operation {operation_type or 'unknown'}.")
                continue

            if operation_type == "create_folder":
                folder_path = self._normalize_relative(str(raw_operation.get("relative_path") or ""))
                reason = str(raw_operation.get("reason") or "Create requested folder.")
                if not self._is_safe_relative(folder_path):
                    blocked_reasons.append(f"Operation {index}: unsafe folder path.")
                    continue
                if folder_path in existing_files:
                    skipped.append(SkippedFileItem(path=folder_path, relative_path=folder_path, reason="Destination exists as a file."))
                    continue
                if folder_path in existing_folders:
                    continue
                operations.append(
                    FileOperation(
                        type="create_folder",
                        tool="file.create_folder",
                        path=None,
                        relative_to=folder_path,
                        reason=reason,
                    )
                )
                existing_folders.add(folder_path)
                continue

            from_path = self._normalize_relative(str(raw_operation.get("from_relative_path") or ""))
            to_path = self._normalize_relative(str(raw_operation.get("to_relative_path") or ""))
            reason = str(raw_operation.get("reason") or "Move file according to instruction.")
            if not self._is_safe_relative(from_path) or not self._is_safe_relative(to_path):
                blocked_reasons.append(f"Operation {index}: unsafe move path.")
                continue
            if from_path not in existing_files:
                skipped.append(SkippedFileItem(path=from_path, relative_path=from_path, reason="Source file was not in the scan."))
                continue
            if to_path in existing_files or to_path in planned_destinations:
                skipped.append(SkippedFileItem(path=from_path, relative_path=from_path, reason="Destination already exists. No overwrite allowed."))
                continue
            if "/" not in to_path:
                skipped.append(SkippedFileItem(path=from_path, relative_path=from_path, reason="Destination folder was not specified."))
                continue
            operations.append(
                FileOperation(
                    type="move_file",
                    tool="file.move_file",
                    from_path=None,
                    to_path=None,
                    relative_from=from_path,
                    relative_to=to_path,
                    reason=reason,
                )
            )
            planned_destinations.add(to_path)

        for raw_skip in raw_plan.get("skipped", []):
            relative_path = self._normalize_relative(str(raw_skip.get("relative_path") or raw_skip.get("path") or ""))
            if relative_path:
                skipped.append(
                    SkippedFileItem(
                        path=relative_path,
                        relative_path=relative_path,
                        reason=str(raw_skip.get("reason") or "Skipped by AI planner."),
                    )
                )

        operations = self._assign_operation_ids(self._dedupe_create_folders(operations))
        folders_to_create = [operation for operation in operations if operation.type == "create_folder"]
        files_to_move = [operation for operation in operations if operation.type == "move_file"]
        category_counts = self._category_counts(request.files)
        if blocked_reasons and not operations:
            status = "blocked"
        elif operations:
            status = "awaiting_confirmation"
        else:
            status = "empty"
            if not skipped:
                warnings.append("AI planner did not find safe file moves for this instruction.")

        return FileTaskPlan(
            task_id=str(uuid4()),
            root_path=request.root_name,
            instruction=request.instruction,
            summary=str(raw_plan.get("summary") or self._summary_for(files_to_move, "AI-assisted plan")),
            risk_level="low" if len(operations) <= 100 else "medium",
            requires_confirmation=True,
            operations=operations,
            folders_to_create=folders_to_create,
            files_to_move=files_to_move,
            skipped=self._dedupe_skipped(skipped),
            warnings=self._dedupe(warnings),
            blocked_reasons=self._dedupe(blocked_reasons),
            status=status,
            total_operations=len(operations),
            create_folder_count=len(folders_to_create),
            move_file_count=len(files_to_move),
            copy_file_count=0,
            rename_file_count=0,
            category_counts=category_counts,
            preview_only=True,
            planner_warning=None,
        )

    def _deterministic_plan(self, request: FileTaskLlmPlanRequest, warning: str | None = None) -> FileTaskPlan:
        intent = self._classify_intent(request.instruction)
        if intent["intent"] == "move_category":
            return self._move_category_plan(request, intent["target_category"], warning)
        if intent["intent"] == "create_folders":
            return self._create_folders_plan(request, intent["folder_names"], warning)
        if intent["intent"] in {"rename_files", "unknown_or_unsupported"}:
            return self._blocked_plan(request, intent["reason"], warning=warning)

        include_other = "other" in request.instruction.lower() or "unknown" in request.instruction.lower()
        existing_folders = {self._normalize_relative(folder.relative_path) for folder in request.folders if not folder.is_hidden}
        existing_files = {self._normalize_relative(file.relative_path) for file in request.files if not file.is_hidden}
        destination_folders: set[str] = set()
        operations: list[FileOperation] = []
        skipped: list[SkippedFileItem] = []
        category_counts: dict[str, int] = {}

        for item in request.files:
            if item.is_hidden:
                skipped.append(SkippedFileItem(path=item.relative_path, relative_path=item.relative_path, reason="Hidden file skipped."))
                continue
            category = self._category_for_extension(item.extension)
            if category == "Other" and not include_other:
                skipped.append(SkippedFileItem(path=item.relative_path, relative_path=item.relative_path, reason="Unknown file type."))
                continue
            source_path = self._normalize_relative(item.relative_path)
            destination_path = self._normalize_relative(f"{category}/{item.name}")
            category_counts[category] = category_counts.get(category, 0) + 1
            if source_path == destination_path or self._parent_path(source_path) == category:
                skipped.append(SkippedFileItem(path=item.relative_path, relative_path=item.relative_path, reason="Already organized."))
                continue
            if destination_path in existing_files:
                skipped.append(SkippedFileItem(path=item.relative_path, relative_path=item.relative_path, reason="Destination already exists. No overwrite allowed."))
                continue
            destination_folders.add(category)
            operations.append(
                FileOperation(
                    type="move_file",
                    tool="file.move_file",
                    relative_from=source_path,
                    relative_to=destination_path,
                    reason=f"{self._category_singular(category)} file should be grouped under {category}.",
                )
            )

        create_operations = [
            FileOperation(
                type="create_folder",
                tool="file.create_folder",
                relative_to=folder,
                reason=f"Create {folder} folder for organized files.",
            )
            for folder in sorted(destination_folders)
            if folder not in existing_folders
        ]
        all_operations = self._assign_operation_ids([*create_operations, *operations])
        folders_to_create = [operation for operation in all_operations if operation.type == "create_folder"]
        files_to_move = [operation for operation in all_operations if operation.type == "move_file"]

        return FileTaskPlan(
            task_id=str(uuid4()),
            root_path=request.root_name,
            instruction=request.instruction,
            summary=self._summary_for(files_to_move, "Organize files by type"),
            risk_level="low" if len(all_operations) <= 100 else "medium",
            requires_confirmation=True,
            operations=all_operations,
            folders_to_create=folders_to_create,
            files_to_move=files_to_move,
            skipped=skipped,
            warnings=[],
            blocked_reasons=[],
            status="awaiting_confirmation" if all_operations else "empty",
            total_operations=len(all_operations),
            create_folder_count=len(folders_to_create),
            move_file_count=len(files_to_move),
            copy_file_count=0,
            rename_file_count=0,
            category_counts=category_counts,
            preview_only=True,
            planner_model=None,
            planner_provider=None,
            planner_warning=warning or "Fallback deterministic plan.",
        )

    def _move_category_plan(self, request: FileTaskLlmPlanRequest, category: str, warning: str | None = None) -> FileTaskPlan:
        existing_folders = {self._normalize_relative(folder.relative_path) for folder in request.folders if not folder.is_hidden}
        existing_files = {self._normalize_relative(file.relative_path) for file in request.files if not file.is_hidden}
        matched = [item for item in request.files if not item.is_hidden and self._category_for_extension(item.extension) == category]
        skipped = [
            SkippedFileItem(path=item.relative_path, relative_path=item.relative_path, reason=f"Not a {category} file.")
            for item in request.files
            if not item.is_hidden and self._category_for_extension(item.extension) != category
        ]
        if not matched:
            singular = self._category_singular(category).lower()
            return FileTaskPlan(
                task_id=str(uuid4()),
                root_path=request.root_name,
                instruction=request.instruction,
                summary=f"No {singular} files were found in this folder.",
                risk_level="low",
                requires_confirmation=True,
                operations=[],
                folders_to_create=[],
                files_to_move=[],
                skipped=skipped,
                warnings=[f"Scanned {len(request.files)} files but found 0 {singular} files."],
                blocked_reasons=[],
                status="empty",
                total_operations=0,
                create_folder_count=0,
                move_file_count=0,
                copy_file_count=0,
                rename_file_count=0,
                category_counts=self._category_counts(request.files),
                preview_only=True,
                planner_warning=warning,
            )

        moves: list[FileOperation] = []
        for item in matched:
            source_path = self._normalize_relative(item.relative_path)
            destination_path = self._normalize_relative(f"{category}/{item.name}")
            if source_path == destination_path or self._parent_path(source_path) == category:
                skipped.append(SkippedFileItem(path=item.relative_path, relative_path=item.relative_path, reason="Already in the requested folder."))
                continue
            if destination_path in existing_files:
                skipped.append(SkippedFileItem(path=item.relative_path, relative_path=item.relative_path, reason="Destination already exists. No overwrite allowed."))
                continue
            moves.append(
                FileOperation(
                    type="move_file",
                    tool="file.move_file",
                    relative_from=source_path,
                    relative_to=destination_path,
                    reason=f"{self._category_singular(category)} file matches the requested category.",
                )
            )
        creates = [
            FileOperation(type="create_folder", tool="file.create_folder", relative_to=category, reason=f"Create {category} for matching files.")
        ] if moves and category not in existing_folders else []
        operations = self._assign_operation_ids([*creates, *moves])
        folders_to_create = [operation for operation in operations if operation.type == "create_folder"]
        files_to_move = [operation for operation in operations if operation.type == "move_file"]
        return FileTaskPlan(
            task_id=str(uuid4()),
            root_path=request.root_name,
            instruction=request.instruction,
            summary=f"Move {len(files_to_move)} {self._category_singular(category).lower()} files into {category}." if files_to_move else f"No {self._category_singular(category).lower()} files need to be moved.",
            risk_level="low",
            requires_confirmation=True,
            operations=operations,
            folders_to_create=folders_to_create,
            files_to_move=files_to_move,
            skipped=self._dedupe_skipped(skipped),
            warnings=[],
            blocked_reasons=[],
            status="awaiting_confirmation" if operations else "empty",
            total_operations=len(operations),
            create_folder_count=len(folders_to_create),
            move_file_count=len(files_to_move),
            copy_file_count=0,
            rename_file_count=0,
            category_counts=self._category_counts(request.files),
            preview_only=True,
            planner_warning=warning,
        )

    def _create_folders_plan(self, request: FileTaskLlmPlanRequest, folder_names: list[str], warning: str | None = None) -> FileTaskPlan:
        existing_folders = {self._normalize_relative(folder.relative_path) for folder in request.folders if not folder.is_hidden}
        names = folder_names or ["Documents", "Images", "Code"]
        operations = self._assign_operation_ids([
            FileOperation(type="create_folder", tool="file.create_folder", relative_to=name, reason="Folder requested by user.")
            for name in names
            if name not in existing_folders
        ])
        return FileTaskPlan(
            task_id=str(uuid4()),
            root_path=request.root_name,
            instruction=request.instruction,
            summary=f"Create {len(operations)} folders: {', '.join(operation.relative_to or '' for operation in operations)}." if operations else "Requested folders already exist.",
            risk_level="low",
            requires_confirmation=True,
            operations=operations,
            folders_to_create=operations,
            files_to_move=[],
            skipped=[],
            warnings=[],
            blocked_reasons=[],
            status="awaiting_confirmation" if operations else "empty",
            total_operations=len(operations),
            create_folder_count=len(operations),
            move_file_count=0,
            copy_file_count=0,
            rename_file_count=0,
            category_counts=self._category_counts(request.files),
            preview_only=True,
            planner_warning=warning,
        )

    def _blocked_plan(self, request: FileTaskLlmPlanRequest, reason: str, warning: str | None = None) -> FileTaskPlan:
        return FileTaskPlan(
            task_id=str(uuid4()),
            root_path=request.root_name,
            instruction=request.instruction,
            summary="MindOS could not prepare a safe plan from that instruction.",
            risk_level="high",
            requires_confirmation=True,
            status="unsupported",
            blocked_reasons=[reason],
            total_operations=0,
            create_folder_count=0,
            move_file_count=0,
            copy_file_count=0,
            rename_file_count=0,
            category_counts=self._category_counts(request.files),
            preview_only=True,
            planner_warning=warning or "Unsupported file task request.",
        )

    def _classify_intent(self, instruction: str) -> dict:
        text = instruction.lower().strip()
        if not text or (re.search(r"\b(organize|sort|clean)\b", text) and re.search(r"\b(type|folder|downloads?)\b", text)):
            return {"intent": "organize_by_type"}
        if re.search(r"\b(delete|remove|compress|upload|email|run|execute|shell|script|overwrite|replace)\b", text):
            return {"intent": "unknown_or_unsupported", "reason": "This file task is not supported safely yet."}
        if re.search(r"\b(rename|renaming)\b", text):
            return {"intent": "rename_files", "reason": "Renaming files is not connected in this MVP."}
        category = self._detect_category(text)
        if category and re.search(r"\b(move|put|group|place)\b", text):
            return {"intent": "move_category", "target_category": category}
        if re.search(r"\b(create|make)\b", text) and re.search(r"\bfolders?\b", text):
            return {"intent": "create_folders", "folder_names": self._extract_folder_names(text)}
        if re.search(r"\b(organize|sort|clean)\b", text):
            return {"intent": "organize_by_type"}
        return {"intent": "unknown_or_unsupported", "reason": "MindOS could not identify a safe file task from that request."}

    def _detect_category(self, text: str) -> str | None:
        for category, terms in MOVE_CATEGORY_ALIASES.items():
            if any(re.search(rf"\b{re.escape(term)}\b", text) for term in terms):
                return category
        return None

    def _extract_folder_names(self, text: str) -> list[str]:
        return [category for category in TYPE_FOLDERS if re.search(rf"\b{re.escape(category.lower())}\b", text)]

    def _parse_json(self, text: str) -> dict | None:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        try:
            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if not match:
                return None
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None

    def _looks_unsafe(self, instruction: str) -> bool:
        text = instruction.lower()
        return any(term in text for term in FORBIDDEN_INSTRUCTION_TERMS)

    def _is_safe_relative(self, value: str) -> bool:
        if not value or value.startswith("/") or re.match(r"^[a-zA-Z]:", value):
            return False
        return all(segment not in {"", ".", ".."} and "\0" not in segment for segment in value.split("/"))

    def _normalize_relative(self, value: str) -> str:
        return value.replace("\\", "/").strip().strip("/").replace("//", "/")

    def _parent_path(self, value: str) -> str:
        parts = self._normalize_relative(value).split("/")
        return "/".join(parts[:-1])

    def _category_for_extension(self, extension: str) -> str:
        ext = extension.lower()
        for folder, extensions in TYPE_FOLDERS.items():
            if ext in extensions:
                return folder
        return "Other"

    def _category_counts(self, files: list[BrowserFilePlanSnapshotItem]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in files:
            if item.is_hidden:
                continue
            category = item.category or self._category_for_extension(item.extension)
            counts[category] = counts.get(category, 0) + 1
        return counts

    def _summary_for(self, moves: list[FileOperation], prefix: str) -> str:
        if not moves:
            return "No safe file moves are needed for this folder."
        folders = sorted({self._parent_path(operation.relative_to or "") for operation in moves if operation.relative_to})
        folder_text = ", ".join(folders[:5])
        if len(folders) > 5:
            folder_text += f", and {len(folders) - 5} more"
        return f"{prefix}: move {len(moves)} files into {folder_text}."

    def _assign_operation_ids(self, operations: list[FileOperation]) -> list[FileOperation]:
        return [
            operation.model_copy(update={"id": f"op_{index:03d}", "status": operation.status or "planned"})
            for index, operation in enumerate(operations, start=1)
        ]

    def _dedupe_create_folders(self, operations: list[FileOperation]) -> list[FileOperation]:
        seen_folders: set[str] = set()
        output: list[FileOperation] = []
        for operation in operations:
            if operation.type == "create_folder":
                folder = operation.relative_to or ""
                if folder in seen_folders:
                    continue
                seen_folders.add(folder)
            output.append(operation)
        return output

    def _dedupe_skipped(self, items: list[SkippedFileItem]) -> list[SkippedFileItem]:
        seen: set[tuple[str | None, str]] = set()
        output: list[SkippedFileItem] = []
        for item in items:
            key = (item.relative_path, item.reason)
            if key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output

    def _dedupe(self, values: list[str]) -> list[str]:
        output: list[str] = []
        for value in values:
            if value not in output:
                output.append(value)
        return output

    def _category_singular(self, category: str) -> str:
        if category == "PDFs":
            return "PDF"
        return category[:-1] if category.endswith("s") else category


file_task_llm_planner_service = FileTaskLlmPlannerService()
