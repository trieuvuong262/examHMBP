"""Cây thư mục NAS (gốc → con → cháu…)."""

from __future__ import annotations

from dataclasses import dataclass, field

from nas_storage.models import NasShareFolder


@dataclass
class FolderTreeNode:
    folder: NasShareFolder
    depth: int
    children: list[FolderTreeNode] = field(default_factory=list)

    @property
    def has_children(self) -> bool:
        return bool(self.children)


def build_folder_tree(folders: list[NasShareFolder]) -> list[FolderTreeNode]:
    by_parent: dict[int | None, list[NasShareFolder]] = {}
    for folder in folders:
        by_parent.setdefault(folder.parent_id, []).append(folder)

    for siblings in by_parent.values():
        siblings.sort(key=lambda f: (f.sort_order, (f.sub_path or ''), f.share_name))

    def walk(parent_id: int | None, depth: int) -> list[FolderTreeNode]:
        nodes: list[FolderTreeNode] = []
        for folder in by_parent.get(parent_id, []):
            nodes.append(
                FolderTreeNode(
                    folder=folder,
                    depth=depth,
                    children=walk(folder.pk, depth + 1),
                ),
            )
        return nodes

    return walk(None, 0)
