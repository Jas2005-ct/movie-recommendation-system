# 🎬 CineMatch: Movie Recommendation & Discovery System

A powerful, full-stack Django-based movie discovery platform that leverages the **TMDB (The Movie Database)** API to provide a comprehensive and interactive cinematic experience. 

CineMatch features a deep database of Bollywood, South Indian, and International cinema, complete with automated data synchronization, user reviews with sentiment analysis, and a modern, responsive user interface.

---

## 🌟 Key Features

### 🚀 Data & Integration
- **TMDB Smart Sync**: Automated management commands to fetch and update movies, TV shows, and artist (cast/crew) metadata directly from TMDB.
- **Deep Metadata**: Comprehensive tracking of directors, main actors, music directors, and even specific roles like villains and comedians.
- **Genre Taxonomy**: Full support for movie and TV show genres with distinct landing pages for each.

### 🎭 User Experience
- **Emotion-Aware Discovery**: Moods can be logged through a small JSON API and mapped to genre-based recommendations. Webcam/facial emotion detection is not part of this build.
- **Dynamic Categorization**: Dedicated sections for Bollywood hits, South Indian blockbusters, and Top Rated global cinema.
- **Intelligent Search**: Real-time search functionality covering movie titles and cast/crew names.
- **Sentiment-Aware Reviews**: User rating and review system that automatically calculates review sentiment (Positive/Negative/Neutral) using Natural Language Processing (NLP) via `TextBlob`.
- **Responsive Design**: A sleek, card-based UI that works seamlessly across desktops, tablets, and mobile devices.

---

## 🛠️ Technology Stack

- **Backend**: Python 3.12+, Django 6.0
- **Package Manager**: [uv](https://docs.astral.sh/uv/) — dependencies declared in `pyproject.toml` and resolved in the committed `uv.lock`
- **Database**: PostgreSQL (with Full-Text Search integration)
- **Natural Language Processing**: TextBlob (Sentiment Analysis).
- **Note**: Heavy CV/ML packages (TensorFlow, OpenCV, MTCNN, RetinaFace) are not used by this application and are intentionally not installed.
- **External API**: TMDB (v3)
- **Storage & Media**: Cloudinary (Media hosting) & WhiteNoise (Static files)
- **Frontend**: HTML5, Vanilla CSS3 (Custom Design System), JavaScript

---

## 🚦 Getting Started

### Prerequisites
- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- PostgreSQL
- TMDB API Key

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Jas2005-ct/movie-recommendation.git
   cd movie-recommendation
   ```

2. **Install uv** (if you don't have it already):
   ```bash
   # Windows
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   # Linux/macOS
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. **Create the virtual environment and install dependencies:**
   ```bash
   uv sync --frozen
   ```
   This reads `pyproject.toml` and the committed `uv.lock`, creating a `.venv`
   with the exact pinned dependency versions. No manual virtual environment
   setup or activation is needed — prefix commands with `uv run` instead.

4. **Configure Environment Variables:**
   Create a `.env` file in the root directory based on `.env.example`:
   ```env
   SECRET_KEY=your_secret_key
   DEBUG=True
   TMDB_API_KEY=your_tmdb_api_key
   DATABASE_URL=postgresql://user:password@localhost:5432/movies
   ```

5. **Run Migrations:**
   ```bash
   uv run python manage.py migrate
   ```

6. **Initialize Data:**
   Use the custom sync scripts to populate your local database:
   ```bash
   # Sync movies from TMDB
   uv run python manage.py sync_movies
   
   # Sync artist/crew metadata
   uv run python manage.py sync_artists
   ```

7. **Start the Development Server:**
   ```bash
   uv run python manage.py runserver
   ```
   Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

8. **Run Tests:**
   ```bash
   uv run python manage.py test
   ```

### Using Watchmode instead of TMDB (optional)

Watchmode is supported as an alternative catalog source. It is useful if TMDB is
unreachable. The free Developer plan is **non-commercial use with attribution**
(the attribution is shown in the site footer).

1. Request a free key at <https://api.watchmode.com/requestApiKey/> (no credit card).
2. Add the key to `.env`:
   ```env
   WATCHMODE_API_KEY=your_watchmode_key
   MOVIE_DATA_PROVIDER=watchmode
   ```
3. Sync the catalog (Tamil by default):
   ```bash
   uv run python manage.py sync_watchmode --pages 2
   uv run python manage.py sync_watchmode --telugu          # Telugu only
   uv run python manage.py sync_watchmode --tamil --hindi   # combine languages
   uv run python manage.py sync_watchmode --all-languages   # all six
   uv run python manage.py sync_watchmode --languages ta,en # explicit codes
   ```
   Available flags: `--hindi`, `--tamil`, `--telugu`, `--malayalam`, `--kannada`
   (alias `--kannadam`), `--english`. They are additive; with no flag the command
   seeds Tamil titles only.
   `python manage.py sync_movies` also honours `MOVIE_DATA_PROVIDER` and delegates
   to Watchmode when it is set, so TMDB remains available as a fallback — just
   unset the variable to use TMDB again.

Notes:
- Free tier = 2,500 credits/month. A page of 50 titles costs roughly 1 (list) +
  50 (details) + 50 (cast) + a few person lookups. Use `--skip-cast` to save credits.
- Watchmode requires cached data to be refreshed within 30 days — run the sync
  monthly.
- Titles without a TMDB ID are skipped because `Movie.tmdb_id` is the primary key.
- Selected languages are requested server-side (to save credits) and then verified
  assigned locally so the existing HomeView categories keep working.
- Malformed titles/people are skipped with a warning instead of aborting the sync.

---

## 📁 Project Structure

```text
movie_recommondation/
├── movie/               # Core application logic
│   ├── management/      # Custom sync commands (sync_movies, sync_artists)
│   ├── services/        # TMDB client + recommendation engine
│   ├── templatetags/    # Custom template filters
│   ├── models.py        # Database schema for Movies, Persons, Reviews, etc.
│   ├── views.py         # Template-based discovery and search views
│   ├── urls.py          # App-specific routing
│   └── tests.py         # Regression tests
├── movies/              # Main project configuration (settings, asgi, wsgi)
├── static/              # CSS, JS, and global assets
├── Template/            # HTML templates
├── pyproject.toml       # Project metadata and pinned dependencies
├── uv.lock              # Reproducible dependency resolution (commit this)
├── .env.example         # Environment template
└── manage.py            # Django entry point
```

---

## 📝 Custom Management Commands

- `uv run python manage.py sync_movies`: Fetches popular and trending movies across various categories (Bollywood, South, etc.) and saves them to the local PostgreSQL database.
- `uv run python manage.py sync_artists`: Enriches the database by fetching detailed cast and crew information for existing movies.
- `uv run python manage.py get_tmdb`: Utility for manual TMDB API interaction.

---

## 🌐 Deployment

This project is configured for easy deployment on platforms like **Render** or **Heroku**. The included `Dockerfile` installs dependencies with `uv sync --frozen` from the committed `uv.lock`, and the `Procfile` starts Gunicorn via `uv run`. `runtime.txt` pins the Python version for buildpack-based deploys. It utilizes `dj-database-url` for easy database configuration and `cloudinary` for external media storage.

### Managing dependencies with uv

All dependencies are pinned in `pyproject.toml` (migrated verbatim from the old `requirements.txt`). To change them:

```bash
uv add <package>          # add a dependency and update pyproject.toml + uv.lock
uv remove <package>       # remove a dependency
uv lock --upgrade         # re-resolve the lockfile
uv sync --frozen          # install exactly what uv.lock specifies
uv run <command>          # run a command inside the managed environment
```

`uv.lock` should be committed so every environment (local, CI, Docker) installs identical versions.

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
