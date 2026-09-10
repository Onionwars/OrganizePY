# OrganizePY

A desktop app that automatically tidies up a messy Downloads folder — sorting files into categories like Images, Documents, and Archives, and even detecting game install folders and moving them into a dedicated `Games` folder using the IGDB database.

## Features

- **Automatic file sorting** by extension into configurable categories (Images, Videos, Audio, Documents, Spreadsheets, Presentations, Code, Archives, Fonts, Executables, Data, and more)
- **Keyword-based rules** that can route files/folders into nested subcategories (e.g. anything mentioning "INSY" goes into `Documents/College/INSY`), which always take priority over plain extension matching
- **Game folder detection** — unrecognized folders are checked against [IGDB](https://www.igdb.com/) (the Internet Game Database) using a fuzzy name-matching algorithm, so a folder like `ReadyorNot` gets identified as *Ready or Not* and filed under `Games`
- **Result caching** — once a folder has been identified as a game, it's remembered, so repeat runs don't need another IGDB lookup
- **Safe moves** — never overwrites an existing file; if a folder already exists at the destination, its contents are merged in instead
- **Simple desktop GUI** built with tkinter, with a live log view and folder history
- **Local storage only** — all rules and cached data live in a small JSON-based database on your machine; nothing is uploaded anywhere except the IGDB search requests

## How it works

For every item in the folder you point it at, OrganizePY decides where it belongs in this order:

1. **Keyword/subcategory rules** — an explicit rule you've configured always wins
2. **Cached or freshly-detected game match** (folders only) — via IGDB, using [`igdb.py`](igdb.py)'s scoring algorithm
3. **File extension** — falls back to whichever category owns that extension
4. **`Other`** — the catch-all if nothing else matched

## Getting started

### Requirements

- Python 3.10+
- An IGDB/Twitch API key (free) — needed for game detection to work

### Installation

```bash
git clone <this-repo>
cd OrganizePY
pip install -r requirements.txt
```

### Configuration

Game detection needs an IGDB API key, which is issued through Twitch's developer portal:

1. Go to <https://dev.twitch.tv/login> and log in (two-factor authentication must be enabled on the account)
2. Register a new application:
   - Name: anything, e.g. `OrganizePY`
   - OAuth Redirect URL: `http://localhost`
   - Category: any
   - Client Type: `Confidential`
3. Copy your Client ID and generate a Client Secret

Then create a `.env` file in the project root (you can copy `.env.example`):

```
IGDB_CLIENT_ID=your_client_id_here
IGDB_CLIENT_SECRET=your_client_secret_here
```

If these aren't set, everything still works except game-folder detection — unmatched game folders will just be left alone instead of being filed under `Games`.

### Running it

```bash
python main.py
```

This opens the GUI: pick a folder, review/edit your category rules if needed, and run the organizer.

## Building a standalone executable

The project ships with PyInstaller spec files, so you can build a double-clickable app with no Python install required:

```bash
pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name OrganizePY main.py
```

The build only runs on the OS it's built on (PyInstaller doesn't cross-compile) — a build made on Windows won't run on macOS or Linux and vice versa. To get all three without owning three machines, this repo includes a GitHub Actions workflow at [`.github/workflows/build.yml`](.github/workflows/build.yml) that builds a Windows, macOS, and Linux version automatically on every push. Find the results under the repo's **Actions** tab → your workflow run → **Artifacts**.

## Project structure

```
OrganizePY/
├── main.py         # Entry point — launches the GUI
├── gui.py          # tkinter interface: folder picker, rule editor, log view
├── organizer.py    # Core sorting logic: deciding where things go and moving them
├── igdb.py         # IGDB API client + game-name matching/scoring
├── database.py     # TinyDB-backed storage for categories, rules, and the game cache
├── config.py       # App paths, environment variables, default categories
├── logger.py       # Logging setup (file + in-GUI log feed)
├── data/           # Created at runtime: database.json, organizer.log, last folder used
└── .github/workflows/build.yml   # CI: builds Windows/macOS/Linux executables
```

## Notes

- `game_matcher.py` is an earlier, unused version of the game-matching logic — the active implementation lives in `igdb.py`. It's kept in the repo for reference but nothing imports it.
- All data (your category rules, the game-name cache, and logs) is stored locally under `data/` — delete that folder (or use the in-app "clear database" option) to reset everything.

## License

No license specified yet — add one (MIT is a common choice for a project like this) if you plan to share the source publicly.
