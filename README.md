# galaxy-plugin-local-repo
Plugin for GOG Galaxy handling DRM-free game installers on your local storage.


## How it works:
The plugin looks for a game.json file in all subfolders located in a LOCAL_REPO_DIR folder.
game.json contains the title of a game, the path and name to the installer executable and the compatible OSes.
Your game is then recognized with an UUID written in the game.json. You can provide an ID.

Installers must be in subfolders. One game per subfolder.

## How to use it:
Copy galaxy-plugin-local-repo to your GOG Galaxy plugins folder. Well the normal plugin installation process.

Change LOCAL_REPO_DIR in galaxy-plugin-local-repo/local_repo.py to your own folder with dozens of game installers.
Copy game_template.json to a game subfolder, change title and installer_file and rename game_template.json to game.json.
If your plugin is running, new games will be added directly.
