# KidNotes-mobile
# RelatórioFácil Infantil

A mobile app written in pure Python with [Flet](https://flet.dev) for
teachers in early childhood education.

The app is **not about evaluating children**. Teachers use it to record
**significant events**: photos and comments about moments that show a
child's growth and learning. Each event is linked to one or more children and
becomes part of each child's **learning story**.

**Sign in → Home (classes) → Class screen (children) → Child screen (learning story)**
**Class screen → Reports → one report per student (AI draft → review → PDF)**

What the teacher can do today:

- **Sign in / create account:** the first time, the teacher creates a local
  account with **email and password**. From then on the app asks for the
  password every time it starts; the **email of the last account used on the
  device comes already filled in**. Each account has **its own data**, encrypted with a
  key that only the password unlocks (see [LGPD](#7-lgpd-data-protection)).
- **Home:** the signed-in teacher (email) with **Sign out**, their classes with
  the number of children, and a new class form (name + color).
- **Class screen:**
  - **Add event** (full-width button in the fixed action bar at the bottom):
    **take a photo or choose photos from the gallery**, describe what happened,
    set the date and **link the children** who took part. The teacher always
    selects the children (nothing is preselected from the class screen); the
    last option, **"Whole class"** ("Turma"), selects all of them. The event
    goes into each linked child's story. After saving, an **information
    message** confirms it, for example "Event saved to Clara Souza's learning
    story." or "... the learning stories of 3 students.".
  - **Add student**: an icon-only button (👤+) at the top, mostly used at the
    beginning of the year. Its tooltip says "Add student" ("Adicionar aluno").
  - **Reports** ("Relatórios"): an icon-only button (📄) at the top that opens
    the report screen (see [Reports](#8-reports-ai--pdf)).
  - The list of children (A→Z, with age and number of events). Tap a child to
    open their story. The ⋮ menu **edits** a child (name, birth date) or
    **removes** them from the class. Removing **deactivates** the child: their
    record and story are kept.
  - **Transferred students:** removed children **stay on the class screen**,
    after the active ones, under "Transferred students (n)" ("Alunos
    transferidos"). They are shown **grey**, with the subtitle "Transferred on
    <date>" ("Transferido(a) em"), and a **Reactivate** ("Reativar") button that
    brings them back to the class. They can't be linked to new events while
    transferred.
- **Child screen:**
  - **Bottom action bar with two buttons side by side**, within easy reach:
    **Extra information** ("Informações extras", left) and **Add event**
    ("Adicionar evento", right, the main action). Same width, icon above the
    label so both fit on a phone.
  - **Extra information** opens a **screen** where the teacher keeps free
    notes about the child, **without a date**, such as "She loves sleeping after lunch" or "He loves playing
    football with one friend". It has a big text area and a full-width **Save**
    button; leaving with unsaved text asks first. The saved text is shown in a
    card at the top of the child screen and saved encrypted.
  - The child's **learning story** (events newest first, with
  photos, comments and the other children involved) and an **Add event**
  button. On **phones** an event's text goes **below** its photos; on
  **tablets and computers** (wider screens) it goes **to the right** of the
  photos. The event form opens with that child **already selected**:
  highlighted, listed first, and named under the form's title.
  - **Edit an event:** the ✎ button on each event opens it in the same form
    ("Edit event"): change the text, the date, the children, and remove or add
    photos. Saving shows "Event updated."; leaving with unsaved changes asks
    first.
- **Start screen:** once the teacher has chosen a class, the app **opens
  directly on that class** the next time it starts (see
  [Start screen](#start-screen)).

Everything (accounts, classes, children, events **and photos**) is saved
**encrypted on the device** (see [Database](#6-database-local--encrypted) and
[LGPD](#7-lgpd-data-protection)). There is no server: accounts are local to the
device.

## Tech stack

| Item | Version / notes |
| --- | --- |
| Language | Python ≥ 3.10 |
| UI framework | Flet 1.0.5 (Flutter under the hood) |
| Targets | Android and iOS (desktop and web also work for development) |
| Database | SQLite (local, on the device) |
| Encryption | AES-256-GCM (`cryptography`); device key in Android Keystore / iOS Keychain (`flet-secure-storage`); account keys unlocked by the password (scrypt) |
| Photos | Camera: `flet-camera`; gallery: system photo picker (`ft.FilePicker`) |
| Reports | Draft by the **Groq** API (`httpx`, model `llama-3.3-70b-versatile`); PDF by a small built-in writer (no dependencies); saved with `ft.FilePicker`, shared with `ft.Share` |
| Tests | pytest |
| Languages | English (default) and Portuguese |

## 1. Setting up the local development environment

Do this once per computer. Every command runs **from the project folder**
(`KidNotes-mobile/`, where `main.py` and `pyproject.toml` are).

### 1.1 Requirements

| Tool | Version | Check with |
| --- | --- | --- |
| Python | **3.10 or newer** (3.12 recommended) | `python --version` (Windows) / `python3 --version` |
| pip | **25.1 or newer**: the first version that installs `[dependency-groups]`; step 1.2 upgrades it | `python -m pip --version` |
| Git | any | `git --version` |

### 1.2 Create the virtual environment and install

The virtual environment (`.venv/`, git-ignored) keeps the project's packages
separate from the rest of the computer.

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install --group dev
```

> If PowerShell says *"running scripts is disabled on this system"*, allow it
> once for your user and activate again:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

**Windows (cmd)**

```bat
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install --group dev
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install --group dev
```

When the environment is active, the prompt starts with `(.venv)`. **Activate
it in every new terminal** before running the app or the tests. To leave it,
run `deactivate`.

The `dev` group installs:
- the app's dependencies: `flet`, `flet-secure-storage`, `flet-camera`,
  `cryptography`, `httpx`;
- the `flet` CLI and the desktop runner (`flet[all]`);
- the test tools: `pytest`, `pypdf`, `pypdfium2`.

Only `[project].dependencies` go into the mobile package.

> **Using [uv](https://docs.astral.sh/uv/)?** Run `uv sync` instead of the
> steps above. It creates `.venv/` and installs the `dev` group. Then prefix
> commands with `uv run`, for example `uv run flet run -r --ignore-dirs .flet main.py`.

### 1.3 Check the installation

```bash
flet --version   # Flet: 1.0.5
pytest -q        # all tests pass
```

### 1.4 Local settings (environment variables)

The app needs **no configuration to run**. The only optional setting is the
Groq key for **Reports**, and it can also be typed inside the app (step 3 of
[Reports](#8-reports-ai--pdf)).

For development, keep local settings in a **`.env` file**:

```bash
copy .env.example .env     # Windows
cp .env.example .env       # macOS / Linux
```

Then edit `.env`:

```dotenv
GROQ_API_KEY=gsk_your_key_here
```

- **Who reads it:** `main.py` reads `.env` at start-up (`devenv.py`). Variables
  already set in the terminal win over the file.
- **Where it goes:** `.env` is **git-ignored** and is **never packaged** into
  the app (`flet build` leaves out `.env`, `.env.example` and `.flet/`).
  Inside a packaged app it is not read at all.
- **Without a file:** set the variable in the terminal for that session only:

  | Shell | Command |
  | --- | --- |
  | PowerShell | `$env:GROQ_API_KEY = "gsk_..."` |
  | cmd | `set GROQ_API_KEY=gsk_...` |
  | macOS / Linux | `export GROQ_API_KEY=gsk_...` |

| Variable | Required | What it does |
| --- | --- | --- |
| `GROQ_API_KEY` | no | Groq key used by **Reports** when no key is saved in the app. |
| `FLET_APP_STORAGE_DATA` | no (set by `flet run`) | Data folder. `flet run` points it to `.flet/storage/data`; set it only to use another folder. |
| `FLET_PLATFORM` | **don't set it** | Set only by packaged apps. It switches the app to the phone's Keystore/Keychain, which isn't available on a computer. |

### 1.5 Local data

While developing, everything the app saves goes to **`.flet/storage/data/`**:
the account registry, the encrypted databases and photos, and the development
key `dev-database.key` (see [Where the files are](#where-the-files-are)).
`.flet/` is git-ignored. The first time, the app asks you to **create an
account**; that account exists only on your computer.

To **start from scratch** (no accounts, no data), stop the app and delete
`.flet/storage/data/`.

## 2. Running the app

### On your computer (fastest way to develop)

```bash
flet run -r --ignore-dirs .flet main.py          # desktop window + hot reload
flet run --web -r --ignore-dirs .flet main.py    # same, in the browser
flet run main.py                                 # desktop window, no hot reload
```

**Hot reload:** with `-r`, the app restarts whenever a `.py` file changes
**in any folder** (`database/`, `screens/`, `reports/`...).
`--ignore-dirs .flet` stops restarts when the app itself saves data in
`.flet/`.

> Don't use `-d` for this project. It only watches the top folder, so changes
> in `database/`, `screens/` or `reports/` don't restart the app, and old and
> new code end up running together (see
> [Troubleshooting](#9-troubleshooting)).

In a desktop window, **Take photo** is disabled: the camera works on phones and
in the browser. Use **Gallery** to add photos.

### On your phone, without building

1. Install the **Flet** app from the Google Play Store or the Apple App Store.
2. Connect the phone and the computer to the same Wi-Fi network.
3. Run one of the commands below and scan the QR code with the phone:

```bash
flet run --android main.py
flet run --ios main.py
```

> **Camera and secure key storage need a built app.** `flet-camera` and
> `flet-secure-storage` are Flet extensions with native code, so they are
> included by `flet build`. With `flet run`:
> - `flet-camera` only works on **Android, iOS and the web**. In a desktop
>   window (`flet run main.py`), **Take photo** is shown **disabled (grey)**, with
>   a message to use the gallery; the camera screen is never opened there
>   (flet-camera would stop the app with "Camera is currently only supported
>   on Android, iOS and Web platforms"). Use **Gallery** on the desktop, or
>   `flet run --web`, `--android` or `--ios` to try the camera. If the Flet app
>   on the phone lacks the camera extension, the camera screen says the camera
>   is not available.
> - The database key is kept in a development key file (see
>   [Database](#6-database-local--encrypted)).

### Building the mobile packages

The build configuration lives in the `[tool.flet]` section of
[`pyproject.toml`](./pyproject.toml). Run `flet doctor` to check that your
machine has what the build needs. The first build downloads the Flutter SDK
automatically; Android builds also need the Android SDK/JDK.

```bash
flet build apk   # Android, for direct install
flet build aab   # Android, for the Google Play Store
flet build ipa   # iOS, requires macOS + Xcode
```

The output goes to `build/`. The `tests/` folder is excluded from the package.
`cryptography` is a native package: for Android/iOS, `flet build` downloads
its prebuilt binary from Flet's mobile package index.

**Permissions:** only the **camera** is requested (`permissions = ["camera"]`
in `pyproject.toml`). The gallery uses the system photo picker, which needs no
storage permission on Android. The iOS permission texts
(`NSCameraUsageDescription`, `NSPhotoLibraryUsageDescription`) are set in
`[tool.flet.ios.info]`.

> Before publishing, change `org` in `pyproject.toml` to your organization's
> reverse domain. The bundle id is `<org>.kidnotes_mobile`, and it cannot be
> changed once the app is in the stores.

## 3. Running the tests

```bash
pytest          # or: pytest -v
```

The tests run without a phone or a Flutter window. They render the screens
against a fake Flet page (`tests/conftest.py`) and check:

- [`tests/test_i18n.py`](./tests/test_i18n.py):
  - both languages have the same keys and `{placeholders}`;
  - the device language is detected correctly, with English as the fallback;
  - plurals work.
- [`tests/test_app.py`](./tests/test_app.py), the screens end to end:
  - the language and the start screen (last chosen class, or home);
  - home: the class list with counts, the empty state, and the "New class" form;
  - class screen layout: **"Add student" at the top**, **"Add event" in the
    fixed bottom action bar**;
  - students: add (with the date picker), edit, clear the birth date,
    validation, remove with confirmation (deactivate), cancel and errors;
  - transferred students: they stay on the class screen (grey, "Transferred on
    <date>", after the active children, not counted), can't be linked to new
    events, and can be reactivated (with a message, or an error message);
  - the child's learning story: newest first, decrypted photos, "With ...",
    "Show older events";
  - responsive events: text below the photos on phones, to the right on wider
    screens; full width when an event has only text or only photos;
  - events:
    - from the class screen (gallery photo + description + date + children);
    - from a child's story: the child is preselected, highlighted, listed
      first and named in the header;
    - both photo options (**Take photo** and **Gallery**) are always shown,
      side by side; where the camera can't work (desktop), **Take photo** is
      disabled and grey, with a message, and the camera screen is never opened (it would
      crash the app there);
    - the app's camera rule matches `flet-camera`'s own platform check on
      every platform;
    - the bottom action bar button uses the full width;
    - the **"Whole class"** option (**"Turma"** in Portuguese): the last chip,
      after all the children; it selects every child, is highlighted when all
      are selected, and clears them when tapped again;
    - the form fields ("What happened?", date) use the full width;
    - the "Students in this event" label ("Alunos neste evento");
    - after saving, an information message names the child (or the number of
      students); no message when the event isn't saved;
    - removing a photo, validation messages, a gallery error;
    - cancelling (asks before discarding photos or text);
  - camera: opens the back camera without microphone;
    the photo goes into the form, whose text and selection are kept; a clear
    message when the camera is not available;
  - a missing encryption key shows the error screen and deletes nothing.
- [`tests/test_app.py`](./tests/test_app.py), sign in and editing:
  - first use shows account creation with the password notice; validation
    messages (both languages); the same email can't be registered twice;
  - sign in, wrong password and unknown email (same message); switching
    between "Sign in" and "Create account"; **sign out closes the data**;
  - the sign-in screen comes with the last email filled in (also after sign
    out; the password field gets the focus); "Create account" starts empty;
  - the reports button through the full start-up path (sign up → class → 📄),
    and a check that every repository `app.py` uses exists in `Repositories`;
  - **each teacher only sees their own classes**;
  - editing an event: text, date, children, removing/adding photos, "Event
    updated.", a transferred child stays linked, cancel with/without changes;
  - the home header has no avatar circle; "Add student" is an icon-only button
    with a translated tooltip;
  - the child screen's bottom bar: "Extra information" and "Add event" side
    by side, same width, "Add event" as the main action;
  - extra information: a screen (not a dialog) with a big full-width text
    area; save (back to the child, with a message), edit, clear, back with or
    without changes, text kept on a rebuild, errors, Portuguese, per child.
- [`tests/test_accounts.py`](./tests/test_accounts.py), checked on the raw files:
  - **the password is never stored** (not even a hash); email and password
    never appear in plain text on disk;
  - **a teacher's data and photos can't be decrypted with the device key
    alone**, only with the key that the password unlocks; accounts can't open
    each other's data;
  - the real scrypt cost is used and stored per account; an unknown email
    costs the same work as a wrong password;
  - data created before accounts is re-encrypted into the first account.
- [`tests/test_reports.py`](./tests/test_reports.py):
  - **pseudonymization**: the child becomes `[NOME]`, classmates become "um(a)
    colega" (also in all caps or without accents); words that are also names
    ("tinta clara") are kept; the first name is put back on the device;
  - **what is sent**: only the period's events, in date order, the age (not
    the birth date), the extra information; **no names, no class name, no
    birth date, no photos**;
  - the Groq client against a mock HTTP server: the request (URL, key, model,
    messages) and each error (invalid key, rate limit, timeout, no internet,
    service error, empty answer);
  - the PDF, read back with `pypdf` (title, child, class, age, period, text,
    signature, "Page X of Y", more pages for long texts) and rendered to an
    image;
  - reports and the API key stored encrypted;
  - the screens: the reports button, period and counts per student, the API
    key, generating one report per selected student (students without events
    are skipped), errors per student, stopping on an invalid key, the review
    screen (edit → PDF with the edited text, save / share on phones, discard
    confirmation, empty text), reopening saved reports, Portuguese.
- [`tests/test_events.py`](./tests/test_events.py):
  - event repository: photo-only and text-only events, each child's story
    newest first, counts, every validation rule;
  - **events and photos are not readable on disk**, including which children
    an event is linked to;
  - a photo file swapped for another one is rejected;
  - a failed save leaves no orphan photo files;
  - editing: keep/remove/add photos (removed files are deleted only after the
    update), validation, a failed update keeps the old photos;
  - photo ids can't point outside the photos folder;
  - cleanup of plugin photo copies: only in packaged apps, only inside the
    app's cache/temp folders, never the user's original files.
- [`tests/test_students.py`](./tests/test_students.py):
  - student repository: add, update, deactivate, per-class alphabetical list,
    counts, validation;
  - student data (including the class link) is not readable on disk;
  - the "last class" setting;
  - an old database is upgraded without losing data, and a failed migration
    is rolled back;
  - dates: time-zone safe conversion of the picked date, age, date formats.
- [`tests/test_database.py`](./tests/test_database.py):
  - **no plain text reaches the disk**;
  - a wrong key, a modified value or a value moved to another row is rejected;
  - data survives reopening with the same key;
  - a new key is never created over existing data;
  - it works from worker threads;
  - packaged apps use the OS secure storage.
- [`tests/test_devenv.py`](./tests/test_devenv.py): the `.env` loader
  (quotes, comments, `export`, the terminal wins, ignored in packaged apps).
- [`tests/test_project_config.py`](./tests/test_project_config.py): the `dev`
  dependency group contains every app dependency, and `tests/` is excluded from
  the mobile package.

The phone's camera and photo picker are replaced by fakes in the tests. Check
them on a real phone with a build (`flet build apk` / `ipa`).

**Manual test of the languages:** change the phone's (or the computer's) system
language to Portuguese and open the app again. It should show Portuguese. Any
other language shows English.

## 4. Languages (i18n)

The app supports **English** (default) and **Portuguese**. The language comes
from the device's **primary** language:

- the device is in Portuguese (`pt`, `pt_BR`, `pt_PT`...) → Portuguese;
- any other language → English.

If the device language changes while the app is open, the interface updates.
Flutter's built-in texts, such as the copy/paste menu and tooltips, follow the
same language through `page.locale_configuration`.

All texts live in [`i18n.py`](./i18n.py). To add a new text:

1. Add the same key to both the `"en"` and the `"pt"` dictionaries.
2. In the screen, use `self.tr.t("my.key")`. For parameters, use
   `self.tr.t("my.key", name=...)`; for counts, use `self.tr.plural("my.key", count)`.
3. Run `pytest`. It fails if a key or placeholder is missing in one of the
   languages.

## 5. Architecture

The app uses a **layered architecture with a single app controller and
state-driven rendering** (unidirectional data flow):

```
                 ┌──────────────────────────────┐
 main.py ──────► │ i18n.detect_device_language  │  reads the device locale
          │      └──────────────────────────────┘
          │      ┌──────────────────────────────┐
          └────► │ database.open_account_store  │  device key + accounts.db
                 └──────────────┬───────────────┘
                                ▼
                 ┌──────────────────────────────┐
                 │ AppRoot (app.py)             │  sign-in gate: AuthScreen →
                 │                              │  the teacher's Session
                 └──────────────┬───────────────┘  (their own database)
                                ▼
                 ┌──────────────────────────────┐
                 │ KidNotesApp (app.py)         │  controller:
                 │  state: route, selected      │  - holds the session state
                 │  class/child, event draft,   │  - navigation
                 │  story page, tr              │
                 │  render() ───────────────────┼──► builds the current screen
                 └───────▲──────────────┬───────┘     (+ its fixed bottom bar)
             callbacks   │              │  data + Translator
     (on_open_child,     │              ▼
      on_saved, ...)  ┌──┴──────────────────────────────────────────┐
                      │ screens/  DashboardScreen · NewClassForm ·  │  views
                      │   ClassScreen · StudentForm ·               │
                      │   RemoveStudentDialog · ChildScreen ·       │
                      │   EventFormScreen · CameraScreen            │
                      └──────────────────────┬──────────────────────┘
                                             ▼
           components.py (shared widgets) · theme.py (design tokens)
           i18n.py (texts) · dates.py (ages) · media.py (gallery)

 KidNotesApp + forms ──► Repositories ────────► EncryptedDatabase ──► SQLite file
                         ClassRepository         (AES-256-GCM)
                         StudentRepository
                         EventRepository ─────► PhotoStore ─────────► photos/*.enc
                         AppSettings
```

### Layers

| Layer | File(s) | Responsibility |
| --- | --- | --- |
| Entry point | `main.py` | Starts Flet, detects the device language, opens the account store and creates `AppRoot` (or shows the "data can't be opened" screen). |
| Sign-in gate | `app.py` (`AppRoot`), `screens/auth.py` | Shows sign-in / registration; on success opens the teacher's `Session` (their own database) in `KidNotesApp`; on sign-out closes it. |
| Controller | `app.py` (`KidNotesApp`) | The only place that holds state (`route`, `selected_class`, `selected_student`, `draft`, `story_limit`, `tr`). It handles navigation, chooses the start screen, re-renders the page and reads the lists from the `Repositories` it receives. |
| Views | `screens/*.py` | Each screen is a class with a `build()` method that returns Flet controls. A screen can also have `bottom_bar()` (a fixed action bar) and `scrollable = False` (the camera preview). Screens get data, a `Translator` and callbacks; they never navigate or change app state themselves. The forms and dialogs also receive the repository they save to, and report back through `on_saved` / `on_removed`. |
| Repositories | `database/classes.py`, `students.py`, `events.py`, `settings.py`, `repositories.py` | `ClassRepository`, `StudentRepository`, `EventRepository` and `AppSettings`, bundled in `Repositories`. They validate input, read and write the database, and return plain dicts, so the views don't know about the database. |
| Storage | `database/connection.py`, `photos.py`, `crypto.py`, `keys.py`, `accounts.py`, `bootstrap.py` | Encrypted SQLite access, encrypted photo files, AES-256-GCM, the device key, accounts and their keys, and startup (see [Database](#6-database-local--encrypted)). |
| Reports | `reports/` (`prompt.py`, `ai.py`, `generate.py`, `document.py`, `pdf.py`, `export.py`), `screens/reports.py`, `database/reports.py` | Builds the pseudonymized prompt, calls Groq, restores the name, stores the draft (encrypted), builds the PDF and saves/shares it (see [Reports](#8-reports-ai--pdf)). |
| Media | `media.py`, `screens/camera.py` | The gallery picker and the camera; removes plain photo copies left by the plugins (see [Photos](#photos)). |
| UI components | `components.py` | Reusable widgets: `page_header`, `avatar`, `section_title`, `empty_state`, `bottom_action_bar`, `photo`. |
| Design tokens | `theme.py` | Color palette shared by every screen. |
| i18n | `i18n.py` | Translation tables, `Translator` (`t`, `plural`, `format_date`, `format_age`) and device language detection. |
| Dates | `dates.py` | Time-zone safe conversion of the picked date and age calculation. |

### How an interaction flows

1. The user taps something, for example a class card.
2. The screen calls the callback it received, `on_class_selected(class_data)`.
3. `KidNotesApp` updates its state (`selected_class`, `route = "class"`) and
   calls `render()`.
4. `render()` clears the page and builds the screen for the current route.

Saving works the same way. For example, when the teacher saves the student
form:

1. `StudentForm` calls `StudentRepository.add()` or `update()`. Validation
   errors are shown on the field, and the dialog stays open.
2. On success, it calls `on_saved`. `KidNotesApp` closes the dialog and
   calls `render()`, which reads the student list again from the database.

Adding an event uses an **`EventDraft`** kept by the controller: the photos
(in memory), the text, the date and the selected children. That's why nothing
is lost when the teacher goes to the camera screen and comes back. Small
changes (typing, tapping a child) update the form in place instead of
re-rendering, so the photos are not sent to the screen again. When the event
is saved, or discarded after confirmation, the draft is dropped and the app
goes back to the screen it came from (class screen or child's story).

Because views are rebuilt from the controller state, screens stay simple and
easy to test: `tests/` renders them with a fake page and inspects the
resulting controls.

### Start screen

When the teacher opens a class, its id is saved (encrypted) in the `settings`
table (`AppSettings.set_last_class_id`). On the next start, `KidNotesApp`
opens directly on that class screen. If the class no longer exists, or no
class was ever chosen, the app starts on the home. Going back to the home does
not forget the class: the app keeps opening the last class the teacher
*chose*, until they choose another one.

### Adding a new screen

1. Create `screens/my_screen.py` with a class that receives data, `tr` and
   callbacks, and exposes `build() -> ft.Control`.
2. Add the route to `KidNotesApp._current_screen()` and a method that sets the
   state and calls `navigate("my-route")`.
3. Add the screen's texts to both languages in `i18n.py`.

## 6. Database (local + encrypted)

The app keeps its data in **SQLite database files inside the app's private
storage on the phone**. There is no server. Python's built-in `sqlite3` is used,
and it is available in Flet's Python runtime for Android and iOS.

### Accounts and keys

```
device key ── Android Keystore / iOS Keychain (random, 256-bit)
  └─ encrypts accounts.db: for each account, the email, the password salt
     and the account key wrapped (encrypted) with the password
password ──scrypt (n=2^15, r=8, p=1)──► key-encryption key
  └─ unwraps the account key (random, 256-bit)
       └─ encrypts accounts/<id>/kidnotes.db and accounts/<id>/photos/*.enc
```

- **Creating an account** (`AccountStore.register`): validates the email
  (normalized to lowercase) and the password (at least 8 characters, typed
  twice), creates a random account key, and wraps it with a key derived from
  the password by **scrypt** with a random salt.
- **Signing in** (`AccountStore.login`): derives the key from the typed
  password and unwraps the account key. A wrong password fails the AES-GCM
  check. **The password is never stored, not even as a hash**. An unknown
  email costs the same work, so the response time doesn't reveal which emails
  have an account.
- **Separate data:** each account has its own database and photos, encrypted
  with its own key. Teachers sharing a device can't see each other's data.
- **Signing out** closes the teacher's database; their data can't be
  decrypted again until the next sign-in.
- **Data from before accounts** (a `kidnotes.db` encrypted with the device key)
  is **re-encrypted into the first account** created on the device, photos
  included, and the old files are removed.
- **Forgotten password:** the account key can't be unwrapped, so **that
  account's data can't be recovered**. The registration screen warns about
  this.

### How the data is encrypted

- **Every record is encrypted** with **AES-256-GCM** before it is written. The
  `payload` column holds the ciphertext of a JSON document with all the
  fields: names, birth dates, colors, the class a student belongs to, whether
  a student is active, event descriptions and dates, which children and photos
  an event is linked to...
- **Only structural data is stored in plain text:** the table names, the
  random record ids (UUIDs), setting names and the insertion order. No names,
  dates or other content. Even the link between a student and a class is
  encrypted, so filtering students by class happens in memory after
  decryption. That is fast for the expected size (hundreds to a few thousand
  records per device).
- **Each value is tied to its location** (`<table>:<id>`) as authenticated
  data. Changing one byte, or copying an encrypted value to another row or
  table, is detected; such records are skipped and logged.
- **The key is checked at startup:** a small encrypted "key check" value in the
  `meta` table confirms the key matches the database. With a wrong key, the
  app refuses to open the data instead of mixing keys.
- **The schema is versioned** with `PRAGMA user_version`. To change it, append
  a new entry to `MIGRATIONS` in `database/connection.py`; never edit a
  released one.

### Tables

| Table | Plain-text columns | Encrypted payload |
| --- | --- | --- |
| `meta` | `name` | key check value |
| `classes` | `seq`, `id` | `name`, `color`, `created_at` |
| `students` | `seq`, `id` | `class_id`, `name`, `birth_date`, `notes` (extra information), `active`, `created_at`, `updated_at`, `deactivated_at` |
| `settings` | `seq`, `id` (setting name) | the value (e.g. `{"class_id": ...}` for `last_class`) |
| `events` | `seq`, `id` | `class_id`, `student_ids`, `description`, `occurred_on`, `photo_ids`, `created_at`, `updated_at` |
| `reports` | `seq`, `id` | `class_id`, `student_id`, `period_start`, `period_end`, `text`, `event_count`, `model`, `created_at`, `updated_at` |

Students are **never deleted**. "Remove from class" sets `active = false` and
`deactivated_at`; the class screen lists them as **transferred**
(`StudentRepository.list_inactive()`), and **Reactivate**
(`StudentRepository.reactivate()`) sets `active = true` again. The record **and
its learning story** stay in the database, but no new events can be linked to
a child while they are transferred.

Schema history: **v1** added `meta` and `classes`; **v2** added `students` and
`settings`; **v3** added `events`; **v4** added `reports`. Existing databases are upgraded
automatically at startup, each migration in a single transaction.

### Photos

- **Storage:** photos are kept **outside SQLite**, one file per photo, at
  `<app data>/photos/<id>.enc`. Each file is AES-256-GCM ciphertext, made with
  the same key and bound to the photo id. The event record holds the photo ids
  (encrypted).
- **Writing:** each file goes to a temporary file first and is then renamed,
  so a photo is never half-written. If saving an event fails, its photo files
  are deleted.
- **Reading:** photos are decrypted **only in memory** to be displayed
  (`ft.Image(src=bytes)`). A child's story shows 10 events at a time, so only
  those photos are decrypted.
- **Limits:** up to 10 photos per event and 15 MB per photo. Accepted formats:
  JPEG, PNG, HEIC (iPhone), WebP and GIF, detected from the file content.
  Gallery photos are re-compressed by the picker (JPEG quality 80), and camera
  photos are 1080p.
- **Plain copies left by plugins:** the photo picker and the camera plugin may
  leave a plain copy of a photo in the app's private cache/temp folders. In a
  packaged app, `media.py` deletes those copies right after reading them, and
  after each capture. This is best effort, and it only touches image files
  created by those plugins inside the app's own folders.

### Where the device key is kept

| Mode | Key storage |
| --- | --- |
| Packaged app (`flet build apk/aab/ipa`) | **Android Keystore / iOS Keychain** through `flet-secure-storage`. A random 256-bit key is created on first start. It never leaves the secure storage and is never written to the app's files. |
| Development (`flet run`, `pytest`) | A **development key file**, `dev-database.key`, in the data folder, readable only by your user. |

The mode is chosen automatically. Flet sets `FLET_PLATFORM` only inside
packaged apps, so the development key file can never be used by a real build.

If the device key is missing but data already exists, for example because the
Keystore entry was lost, the app **does not create a new key and does not
delete anything**. It shows a "Your data can't be opened" screen instead.

### Where the files are

```
<data folder>/
├── accounts.db                  # account registry (device key)
├── dev-database.key             # development only: the device key
└── accounts/<account id>/
    ├── kidnotes.db              # the teacher's classes, students, events (account key)
    └── photos/<photo id>.enc    # the teacher's photos (account key)
```

| Mode | Data folder |
| --- | --- |
| Phone | App private storage (`FLET_APP_STORAGE_DATA`) |
| `flet run` | `.flet/storage/data/` |

`.flet/` is git-ignored. To start over in development (no accounts, no data),
delete `.flet/storage/data/`.

### Using it in code

```python
from datetime import date
from database import Repositories, open_account_store

accounts = await open_account_store()                       # device key + registry
session = accounts.register("ana@school.org", "password", "password")  # or .login(...)
repos = Repositories.from_database(session.database)        # this teacher's data

new_class = repos.classes.add("Preschool I", "#F8C8D8")   # validates, encrypts, saves
maya = repos.students.add(new_class["id"], "Maya Rocha", date(2021, 8, 5))
repos.students.update(maya["id"], "Maya Rocha Lima", None)  # birth date is optional
repos.students.deactivate(maya["id"])                      # "remove from class"
repos.students.list_active(new_class["id"])                # active students, A→Z
repos.students.list_inactive(new_class["id"])              # transferred students, A→Z
repos.students.reactivate(maya["id"])                      # back to the class
repos.students.update_notes(maya["id"], "Loves sleeping after lunch.")  # extra information
repos.settings.set_last_class_id(new_class["id"])          # start screen

event = repos.events.add(                                  # photos: list of bytes
    new_class["id"], [maya["id"]], "Counted to ten while building a tower",
    date.today(), [jpeg_bytes],
)
repos.events.story(maya["id"], limit=10)                   # newest first
repos.events.load_photo(event["photo_ids"][0])             # decrypted bytes
repos.events.update(                                       # photos: ids to keep + new bytes
    event["id"], [maya["id"]], "Counted to twenty", date.today(),
    [event["photo_ids"][0], other_jpeg_bytes],
)
session.close()                                            # sign out
```

Invalid input raises `AccountError`, `ClassValidationError`,
`StudentValidationError` or `EventValidationError`. The error's `code` (for example `name_required`,
`birth_date_in_future` or `no_students`) maps to a translated message:
`auth.error.<code>`, `class_form.error.<code>`, `student_form.error.<code>` or
`event_form.error.<code>`.

To store a new kind of data: add its table in a new migration, add the table
name to `RECORD_TABLES`, and create a repository like `database/students.py`.

## 7. LGPD (data protection)

The app handles personal data of **children** (names, birth dates, photos,
descriptions of their development), so it is designed to protect it on the
device. Technical measures (LGPD art. 46: security measures to protect
personal data):

| Measure | How |
| --- | --- |
| **Photos encrypted** | Every photo taken with the app (camera) or chosen from the gallery is encrypted with **AES-256-GCM** before it's written, as `accounts/<id>/photos/<id>.enc`. It is decrypted **only in memory** to be shown. |
| **No copies left behind** | Camera photos go straight to the app (they are **not saved to the phone's gallery**). Plain copies that the camera/picker plugins may leave in the app's private cache are deleted right after reading (see [Photos](#photos)). |
| **All data encrypted** | Names, birth dates, events, the links between children, classes and events: all encrypted; only random ids and table names are in plain text. |
| **Access control** | The data only opens after **signing in**, every time the app starts. **Signing out** closes it. |
| **Encryption tied to the password** | Without the teacher's password, the data and photos **can't be decrypted**, even by someone with the unlocked phone and access to the Keystore/Keychain. The password is never stored. |
| **Separation between teachers** | Each account has its own key, database and photos. |
| **Data stays on the device** | No server, no cloud, no analytics. The only exception is **report drafts** (next row). |
| **Reports: minimum data to the AI** | Only when the teacher taps "Generate reports": the **descriptions and dates of the period's events**, the **extra information** and the child's **age** are sent to **Groq** (an AI service outside Brazil). **Names are replaced** before sending (`[NOME]`, "um(a) colega") and put back on the device; **photos, birth dates and class names are never sent**. The screen says this before generating. |
| **Integrity** | Authenticated encryption: modified or swapped data/photos are detected and rejected. |

What the app **doesn't** cover (organizational measures for the school):

- **Consent:** LGPD art. 14 requires specific consent from a parent or legal
  guardian to process children's data. The school should collect it before
  teachers record a child. The app doesn't manage consent yet.
- **Photos chosen from the gallery** are encrypted inside the app, but the
  original stays in the phone's gallery: the teacher should delete it there
  if needed. Photos taken with the app's camera don't have this issue.
- **Retention and deletion:** there's no "delete all of a child's data"
  function yet (data subjects' rights, art. 18).
- **AI service (international transfer):** sending event descriptions to
  Groq is an international transfer of personal data (LGPD art. 33) to a data
  processor. Even pseudonymized, the descriptions are about a child. The
  school should check Groq's terms (data retention, use for training) and
  include this use in its privacy notice and in the families' consent.
- **Device security:** the phone should have a screen lock. Android's
  automatic backups don't carry the device key (see limitations).

## 8. Reports (AI + PDF)

**One report per student**, written from the events of a period, the way a
teacher writes a descriptive development report.

1. **Class screen → 📄 (Reports).**
2. Choose the **period** ("From" / "To"; the default is the last ~6 months)
   and the **students**. Each chip shows how many events the child has in the
   period, and "Whole class" selects everyone.
3. The first time, paste a **Groq API key** (create one at
   [console.groq.com](https://console.groq.com)). It is stored **encrypted** in
   the teacher's account. For development, the `GROQ_API_KEY` environment
   variable is used if no key is saved.
4. **Generate reports**: the students are processed one by one, and the screen
   shows each status (waiting, writing, ready, no events in the period, or the
   error). Students without events are skipped: nothing is sent for them.
5. **Open** a report: the **draft is editable**. The teacher reviews it, then
   taps **Save PDF** (system "save as" dialog, or a download on the web) or,
   on phones, **Share PDF** (WhatsApp, e-mail, Drive...). Edits are saved
   before the PDF is made. Generated reports stay listed under "Generated
   reports" to reopen later.

**What the AI is asked** (`reports/prompt.py`): to write like an
early-childhood teacher. The text should be descriptive and warm, not
evaluative, with no grades, comparisons or diagnoses. It must **use only the
records**, never invent, and link experiences to the **BNCC fields of
experience**. It must refer to the child only as `[NOME]` / "a criança", with
no gendered words (the app doesn't record gender), and be 3 to 6 paragraphs
ending with next steps.

**What is sent and what isn't**: see [LGPD](#7-lgpd-data-protection). Example
of what Groq receives:

```
Período: 01/02/2025 a 30/06/2025
Idade da criança no fim do período: 4 anos

Informações da professora sobre a criança:
[NOME] adora dormir depois do almoço.

Registros de momentos significativos (2):
- 01/03/2025: [NOME] pintou o sol.
- 02/05/2025: [NOME] contou os blocos com um(a) colega. (com 1 colega(s))
```

**The PDF** (`reports/document.py`): the title, the child's name, class, age,
period and issue date, the text, and a signature line for the teacher, with
"Page X of Y" at the bottom. A4, standard Helvetica font (all Portuguese
accents). It is written by `reports/pdf.py`, a small pure-Python PDF writer.
The common PDF libraries need Pillow (native code), which is one more binary
package for Android/iOS. The PDF is made in memory and goes straight to where
the teacher saves or shares it.

**Model:** `GROQ_MODEL` in `reports/ai.py` (`llama-3.3-70b-versatile`). Change
it there if Groq retires the model.

## 9. Troubleshooting

| Problem | Cause and fix |
| --- | --- |
| `The application encountered an error: 'Repositories' object has no attribute 'reports'` (or any `... has no attribute ...` right after updating the code) | The running app mixed new and old code. It happens with `flet run -d`, which doesn't restart when files in `database/`, `screens/` or `reports/` change. **Stop the app (Ctrl+C) and start it again**, and use `flet run -r --ignore-dirs .flet main.py` from now on. |
| The app restarts all the time while running | Hot reload is watching `.flet/`, where the app saves its data. Add `--ignore-dirs .flet`. |
| `pip install --group dev` fails with *no such option: --group* | pip is older than 25.1: `python -m pip install --upgrade pip`. |
| PowerShell: *running scripts is disabled on this system* | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then activate again. |
| `flet: command not found` / `No module named flet` | The virtual environment isn't active in this terminal: activate it (step 1.2). |
| "Your data can't be opened" at start-up | The development key (`.flet/storage/data/dev-database.key`) was deleted but the data is still there. In development, delete `.flet/storage/data/` to start over. |
| Reports: "Add your Groq API key first." | Save a key in the report screen, or set `GROQ_API_KEY` in `.env` (step 1.4) and restart the app. |
| Reports: "Invalid API key." / "Too many requests" | Check the key at console.groq.com. The free tier has rate limits: wait a minute and try again. |
| "Take photo" is grey | Expected in a desktop window: the camera works on phones and in the browser. Use **Gallery**. |

## Project structure

```
KidNotes-mobile/
├── main.py              # Flet entry point
├── app.py               # KidNotesApp: state + navigation (controller)
├── i18n.py              # translations (en/pt) + language detection
├── theme.py             # design tokens (colors, class/avatar colors)
├── components.py        # shared UI components
├── dates.py             # birth date / age helpers
├── media.py             # gallery picker + cleanup of plain photo copies
├── devenv.py            # development only: loads .env
├── .env.example         # local settings template (copy to .env)
├── reports/
│   ├── prompt.py        # what is sent to the AI + pseudonymization
│   ├── ai.py            # Groq API client
│   ├── generate.py      # events of the period → draft
│   ├── document.py      # the report PDF layout
│   ├── pdf.py           # small PDF writer (+ font_metrics.py)
│   └── export.py        # save / share the PDF
├── database/
│   ├── bootstrap.py     # opens the database at startup (folder + key)
│   ├── keys.py          # device key storage: Keystore/Keychain or dev key file
│   ├── accounts.py      # AccountStore: register / sign in, account keys
│   ├── crypto.py        # AES-256-GCM record encryption
│   ├── connection.py    # encrypted SQLite access + migrations
│   ├── classes.py       # ClassRepository
│   ├── students.py      # StudentRepository (add, update, deactivate)
│   ├── events.py        # EventRepository (learning story)
│   ├── photos.py        # PhotoStore: encrypted photo files
│   ├── reports.py       # ReportRepository (generated reports)
│   ├── settings.py      # AppSettings (last opened class)
│   └── repositories.py  # Repositories bundle
├── screens/
│   ├── auth.py          # sign in / create account
│   ├── dashboard.py     # home: class list (from the database), sign out
│   ├── class_form.py    # "New class" form (saves to the database)
│   ├── class_screen.py  # class screen: children, Add student, Add event
│   ├── student_form.py  # add / edit student (name, birth date)
│   ├── child.py         # child screen: extra information + learning story
│   ├── extra_info.py    # extra information screen (notes about the child)
│   ├── event_form.py    # new / edit event: photos, description, date, children
│   ├── camera.py        # camera preview + capture
│   └── reports.py       # report screen + review screen
├── tests/               # pytest suite (not bundled into the app)
└── pyproject.toml       # dependencies, mobile build and pytest config
```

## Current limitations

- **Forgotten password = data that can't be opened.** There is no recovery
  (there's no server). A recovery code shown once at registration would be a
  good next step.
- Accounts are local to each device: there is no sync or backup to a server.
- Events can be added and edited, but not deleted yet.
- **Reports:** the real Groq API was not called during development (no
  network access to it); the request follows Groq's OpenAI-compatible API and
  is tested against a mock. Try it first with a real key. Each teacher needs
  their own Groq key (the free tier has rate limits: on "Too many requests",
  wait a minute). A generated report can be edited and exported, but not
  deleted yet.
- Classes can be created and listed, but not edited or deactivated yet.
- A transferred child's learning story can't be opened from the class screen
  yet (only reactivating them brings the story back into reach).
- The report PDF has no photos; a PDF of the learning story with photos
  doesn't exist yet.
- **Photo display performance:** full photos are decrypted and sent to the
  screen; there are no thumbnails yet. This is fine for 10 events at a time,
  but thumbnails would make long stories faster.
- **Android backups:** the Android Keystore key is not included in Android's
  automatic backups. If a backup is restored on a new phone, the database and
  photos come back but their key doesn't, and the app shows the "data can't be
  opened" screen. Decide between disabling auto-backup or adding a "start
  over" option.
