"""Base handler for file-based extensions (skill, subagent, command)."""

import shutil
from pathlib import Path

from vibelens.models.extension import ExtensionItem
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class FileBasedHandler:
    """Shared install/uninstall logic for file-based extension types.

    Skills and subagents install as flat files ({name}.md).
    Subclasses override to customize behavior.
    """

    def install(self, item: ExtensionItem, target_dir: Path, overwrite: bool = False) -> Path:
        """Write install_content to the target directory.

        Args:
            item: ExtensionItem with install_content populated.
            target_dir: Parent directory for installation.
            overwrite: If True, overwrite existing files.

        Returns:
            Path where the item was installed.

        Raises:
            FileExistsError: If target exists and overwrite is False.
        """
        target = self._resolve_target(item=item, target_dir=target_dir)
        if target.exists() and not overwrite:
            raise FileExistsError(
                f"Already exists: {target}. Use overwrite=true to replace."
            )
        self._write_content(item=item, target=target)
        logger.info("Installed %s to %s", item.extension_id, target)
        return target

    def uninstall(self, name: str, target_dir: Path) -> bool:
        """Remove an installed extension.

        Args:
            name: Extension name.
            target_dir: Parent directory to remove from.

        Returns:
            True if removed, False if not found.
        """
        target = target_dir / name
        if target.is_dir():
            shutil.rmtree(target)
            return True
        target_md = target_dir / f"{name}.md"
        if target_md.is_file():
            target_md.unlink()
            return True
        return False

    def _resolve_target(self, item: ExtensionItem, target_dir: Path) -> Path:
        """Resolve the install target path. Override in subclasses.

        Args:
            item: Extension item being installed.
            target_dir: Parent directory.

        Returns:
            Target path (file for commands/skills, directory for subagents).
        """
        return target_dir / f"{item.name}.md"

    def _write_content(self, item: ExtensionItem, target: Path) -> None:
        """Write the extension content to disk. Override in subclasses.

        Args:
            item: Extension item with install_content.
            target: Resolved target path.
        """
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.install_content or "", encoding="utf-8")
