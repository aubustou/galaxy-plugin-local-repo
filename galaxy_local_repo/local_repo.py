import asyncio
import copy
import json
import operator
import pathlib
import sys
import logging
from asyncio import Event
from dataclasses import dataclass, field
from json import JSONEncoder
from typing import List, Dict, Any, Optional
from uuid import uuid4

from galaxy.api.plugin import Plugin, create_and_run_plugin
from galaxy.api.consts import Platform, OSCompatibility, LocalGameState, LicenseType
from galaxy.api.types import Authentication, Game, LicenseInfo, LocalGame

LOCAL_REPO_DIR = pathlib.Path("Z:\Jeux\Dépôt local")
OS_MAP = {
    "windows": OSCompatibility.Windows,
    "mac": OSCompatibility.MacOS,
    "linux": OSCompatibility.Linux,
}


@dataclass
class LocalRepoGame(Game):
    location: str
    installer: Optional[str]
    installed: bool = False
    running: bool = False
    image_files: List[Optional[str]] = field(default_factory=list)
    compatible_os: List[Optional[str]] = field(default_factory=list)

    @property
    def full_installer_path(self):
        return pathlib.Path(self.location) / pathlib.Path(self.installer)

    def get_installation_status(self):
        status = LocalGameState.None_
        if self.installed:
            status |= LocalGameState.Installed
        if self.running:
            status |= LocalGameState.Running
        return status

    def get_os_compatibility(self):
        compatibility = OSCompatibility(0)
        for os in self.compatible_os:
            compatibility |= OS_MAP.get(os, OSCompatibility(0))
        return compatibility if compatibility else None


class GameEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, LocalRepoGame):
            return {
                "title": obj.game_title,
                "location": obj.location,
                "installer": obj.installer,
                "image_files": obj.image_files,
                "compatible_os": obj.compatible_os,
                "installed": obj.installed,
            }
        return JSONEncoder.default(self, obj)


class LocalRepoPlugin(Plugin):
    games_ids: List[str] = []
    checking_for_new_games: bool = False
    repo_metadata: Dict[str, LocalRepoGame] = dict()
    previous_repo_metadata: Dict[str, LocalRepoGame] = dict()
    repo_metadata_file: pathlib.Path = LOCAL_REPO_DIR / "local_repo.json"
    new_game_task_running: Event = Event()
    installed_task_running: Event = Event()

    def __init__(self, reader, writer, token):
        super().__init__(
            Platform.Test,  # choose platform from available list
            "0.1",  # version
            reader,
            writer,
            token,
        )

        self.repo_metadata_file.touch()

    async def authenticate(self, stored_credentials=None) -> Authentication:
        return Authentication("local_user_id", "Local User Name")

    async def check_for_new_games(self, running: Event) -> None:
        if running.is_set():
            # Task is already running
            return
        running.set()
        logging.debug("Checking for changes in the local repository")

        games_before = list(self.repo_metadata.values())
        ids_before = {x.game_id for x in games_before}
        games_after = await self.get_games()
        ids_after = {x.game_id for x in games_after}

        if ids_after == ids_before:
            return

        new_game_ids = ids_before ^ ids_after
        removed_game_ids = ids_before - ids_after
        any_change = False

        for id_ in new_game_ids:
            any_change = True
            game = self.repo_metadata[id_]
            self.add_game(game)
            logging.debug(
                f"Game {game.game_id} ({game.game_title}) is new, adding to galaxy..."
            )

        for id_ in removed_game_ids:
            any_change = True
            game = copy.copy(self.repo_metadata[id_])
            self.remove_game(game)
            del self.repo_metadata[id_]
            logging.debug(
                f"Game {game.game_id} ({game.game_title}) seems to be uninstalled, removing from galaxy..."
            )

        if any_change:
            json.dump(
                self.repo_metadata,
                self.repo_metadata_file.open(mode="w"),
                indent=4,
                cls=GameEncoder,
            )

        logging.debug("Finished checking for changes in the local repository")
        await asyncio.sleep(5)
        running.clear()

    async def check_for_installed(self, running: Event) -> None:
        if running.is_set():
            # Task is already running
            return
        running.set()

        self.previous_repo_metadata = copy.deepcopy(self.repo_metadata)

        if sorted(
            [x for x in self.repo_metadata.values() if x.installed],
            key=operator.attrgetter("game_id"),
        ) != sorted(
            [x for x in self.previous_repo_metadata.values() if x.installed],
            key=operator.attrgetter("game_id"),
        ):
            json.dump(
                self.repo_metadata,
                self.repo_metadata_file.open(mode="w"),
                indent=4,
                cls=GameEncoder,
            )
        asyncio.sleep(5)
        running.clear()

    def tick(self) -> None:
        self.create_task(self.check_for_new_games(self.new_game_task_running), "new")
        self.create_task(
            self.check_for_installed(self.installed_task_running), "installed"
        )

    async def get_owned_games(self) -> List[Game]:
        logging.debug("Get owned games")
        games = await self.get_games()
        json.dump(
            self.repo_metadata,
            self.repo_metadata_file.open(mode="w"),
            indent=4,
            cls=GameEncoder,
        )
        return games

    async def get_games(self) -> List[Game]:
        for item in LOCAL_REPO_DIR.iterdir():
            if item.is_dir():
                metadata_file: pathlib.Path = item / "game.json"
                if metadata_file.exists():
                    metadata = json.load(metadata_file.open())
                    game_uuid = metadata.get("uuid")
                    if not game_uuid:
                        game_uuid = str(uuid4())
                        metadata["uuid"] = game_uuid
                        json.dump(metadata, metadata_file.open("w"), indent=4)
                    game_title = metadata["title"]
                    self.repo_metadata[game_uuid] = LocalRepoGame(
                        game_id=game_uuid,
                        game_title=game_title,
                        dlcs=None,
                        license_info=LicenseInfo(LicenseType.SinglePurchase),
                        location=str(item),
                        installer=metadata.get("installer_file"),
                        image_files=metadata.get("image_files", []),
                        compatible_os=metadata.get("compatible_os"),
                    )

        return list(self.repo_metadata.values())

    async def launch_game(self, game_id: str) -> None:
        return

    async def install_game(self, game_id: str) -> None:
        game = self.repo_metadata[game_id]
        installer_file = game.installer
        if not installer_file:
            return

        cmd = str(game.full_installer_path)
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await proc.communicate()

        logging.debug(f"[{cmd!r} exited with {proc.returncode}]")
        if proc.returncode == 0:
            game.installed = True

        if stdout:
            logging.debug(f"[stdout]\n{stdout.decode()}")
        if stderr:
            logging.debug(f"[stderr]\n{stderr.decode()}")

    async def uninstall_game(self, game_id):
        pass

    async def get_local_size(self, game_id: str, context: Any) -> Optional[int]:
        pass

    async def get_local_games(self) -> List[Optional[LocalGame]]:
        local_games = []
        for game in self.repo_metadata.values():
            local_game = LocalGame(
                game_id=game.game_id, local_game_state=game.get_installation_status()
            )
            local_games.append(local_game)
        return local_games

    async def get_os_compatibility(
        self, game_id: str, context: Any
    ) -> Optional[OSCompatibility]:
        game = self.repo_metadata[game_id]
        return game.get_os_compatibility() if game else None


def main():
    create_and_run_plugin(LocalRepoPlugin, sys.argv)


if __name__ == "__main__":
    main()
