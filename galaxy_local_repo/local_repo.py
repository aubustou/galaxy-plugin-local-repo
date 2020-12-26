import asyncio
import json
import pathlib
import sys
import logging
from json import JSONDecodeError
from typing import List, Dict, Any, Optional
from uuid import uuid4

from galaxy.api.plugin import Plugin, create_and_run_plugin
from galaxy.api.consts import Platform, OSCompatibility
from galaxy.api.types import Authentication, Game, LicenseInfo, LicenseType

LOCAL_REPO_DIR = pathlib.Path("Z:\Jeux\Dépôt local")
OS_MAP = {
    "windows": OSCompatibility.Windows,
    "mac": OSCompatibility.MacOS,
    "linux": OSCompatibility.Linux,
}


class LocalRepoPlugin(Plugin):

    games_ids: List[str] = []
    checking_for_new_games: bool = False
    repo_metadata: Dict[str, Dict] = dict()
    repo_metadata_file: pathlib.Path = LOCAL_REPO_DIR / "local_repo.json"

    def __init__(self, reader, writer, token):
        super().__init__(
            Platform.Test,  # choose platform from available list
            "0.1",  # version
            reader,
            writer,
            token,
        )

        if not self.repo_metadata_file.exists():
            self.repo_metadata_file.touch()
            self.repo_metadata = dict()
        else:
            try:
                self.repo_metadata = json.load(self.repo_metadata_file.open())
            except JSONDecodeError:
                # Assume file is empty
                self.repo_metadata = dict()

    async def authenticate(self, stored_credentials=None) -> Authentication:
        return Authentication("local_user_id", "Local User Name")

    async def check_for_new_games(self) -> None:
        logging.debug("Checking for changes in the local repository")
        games_before = self.games_ids[:]
        games_after = await self.get_games()
        ids_after = [x.game_id for x in games_after]
        for game in games_after:
            if game.game_id not in games_before:
                self.add_game(game)
                logging.debug(
                    f"Game {game.game_id} ({game.game_title}) is new, adding to galaxy..."
                )

        for game in games_before:
            if game not in ids_after:
                self.remove_game(game)
                del self.repo_metadata[game]
                logging.debug(
                    f"Game {game} seems to be uninstalled, removing from galaxy..."
                )
        if games_before or games_after:
            json.dump(
                self.repo_metadata, self.repo_metadata_file.open(mode="w"), indent=4
            )

        logging.debug("Finished checking for changes in the local repository")

    def tick(self) -> None:
        self.create_task(self.check_for_new_games(), "yep")

    async def get_owned_games(self) -> List[Game]:
        logging.debug("Get owned games")
        games = await self.get_games()
        json.dump(self.repo_metadata, self.repo_metadata_file.open(mode="w"), indent=4)
        return games

    async def get_games(self) -> List[Game]:
        games = []
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
                    self.repo_metadata[game_uuid] = {
                        "title": game_title,
                        "location": str(item),
                        "installer": metadata.get("installer_file"),
                        "image_files": metadata.get("image_files", []),
                        "compatible_os": metadata.get("compatible_os", ["windows"]),
                    }

                    games.append(
                        Game(
                            game_uuid,
                            game_title,
                            None,
                            LicenseInfo(LicenseType.SinglePurchase),
                        )
                    )

        self.games_ids = [x.game_id for x in games]

        return games

    async def launch_game(self, game_id: str) -> None:
        return

    async def install_game(self, game_id: str) -> None:
        installer_file = self.repo_metadata[game_id].get("installer")
        if not installer_file:
            return

        cmd = str(
            pathlib.Path(self.repo_metadata[game_id]["location"])
            / pathlib.Path(installer_file)
        )
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await proc.communicate()

        logging.debug(f"[{cmd!r} exited with {proc.returncode}]")
        if stdout:
            logging.debug(f"[stdout]\n{stdout.decode()}")
        if stderr:
            logging.debug(f"[stderr]\n{stderr.decode()}")

    async def uninstall_game(self, game_id):
        return

    async def get_local_size(self, game_id: str, context: Any) -> Optional[int]:
        pass

    async def get_os_compatibility(
        self, game_id: str, context: Any
    ) -> Optional[OSCompatibility]:
        return OS_MAP[self.repo_metadata[game_id]["compatible_os"][0]]


def main():
    create_and_run_plugin(LocalRepoPlugin, sys.argv)


if __name__ == "__main__":
    main()
