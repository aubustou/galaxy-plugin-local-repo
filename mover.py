import json
import pathlib
import shutil

LOCAL_REPO_DIR = pathlib.Path("Z:\Jeux\Dépôt local")


def main():
    metadata = json.load((LOCAL_REPO_DIR / "game_template.json").open())

    for file in LOCAL_REPO_DIR.iterdir():
        if file.is_file() and file.stem.startswith("Download "):
            game_name = file.stem[len("Download ") :]
            new_folder = LOCAL_REPO_DIR / game_name
            new_folder.mkdir(exist_ok=True)
            shutil.move(file, new_folder)
            metadata["title"] = game_name
            json_file = new_folder / "game.json"
            json_file.touch()
            json.dump(metadata, json_file.open("w"))


if __name__ == "__main__":
    main()
