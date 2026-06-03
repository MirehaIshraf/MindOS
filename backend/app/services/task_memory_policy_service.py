from dataclasses import dataclass


DOCUMENT_SUMMARY_TASK_TYPE = "document_summary"

OPERATIONAL_FILE_TASK_TYPES = {
    "file_organize",
    "file_move",
    "file_copy",
    "file_rename",
    "create_folders",
    "folder_cleanup",
    "scan_folder",
    "prepare_plan",
    "execute_file_plan",
    "undo_file_plan",
}


@dataclass(frozen=True)
class TaskMemoryPolicy:
    create_memory: bool
    indexable: bool
    context_eligible: bool
    relationship_eligible: bool


def should_create_memory_for_task(task_type: str) -> bool:
    return normalize_task_type(task_type) == DOCUMENT_SUMMARY_TASK_TYPE


def get_task_memory_policy(task_type: str) -> TaskMemoryPolicy:
    if should_create_memory_for_task(task_type):
        return TaskMemoryPolicy(
            create_memory=True,
            indexable=True,
            context_eligible=True,
            relationship_eligible=True,
        )
    return TaskMemoryPolicy(
        create_memory=False,
        indexable=False,
        context_eligible=False,
        relationship_eligible=False,
    )


def is_operational_file_task(task_type: str) -> bool:
    return normalize_task_type(task_type) in OPERATIONAL_FILE_TASK_TYPES


def normalize_task_type(task_type: str) -> str:
    return (task_type or "").strip().lower()
