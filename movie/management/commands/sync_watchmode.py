"""Management command: sync_watchmode.

Fetches movie/TV metadata from Watchmode and upserts it into the same local
PostgreSQL tables used by `sync_movies`. Views still never call an external API.

Usage:
    uv run python manage.py sync_watchmode                    # Tamil (default)
    uv run python manage.py sync_watchmode --telugu          # Telugu
    uv run python manage.py sync_watchmode --tamil --hindi   # multiple
    uv run python manage.py sync_watchmode --all-languages   # all six
    uv run python manage.py sync_watchmode --languages ta,en # explicit codes
    uv run python manage.py sync_watchmode --skip-cast       # save credits

Free Developer plan notes: non-commercial use with attribution, 2,500 credits
per month, and cached data must be refreshed within 30 days. Run this command
monthly to satisfy the refresh rule.
"""

import re
import time
from datetime import datetime

from django.core.exceptions import ValidationError
from django.core.management import CommandError, BaseCommand
from django.db import DataError, IntegrityError, transaction

from movie.models import Genre, Movie, MovieCrew, Person
from movie.services import watchmode

LANGUAGE_FLAGS = {
    'hindi': 'hi',
    'tamil': 'ta',
    'telugu': 'te',
    'malayalam': 'ml',
    'kannada': 'kn',
    'english': 'en',
}
LANGUAGE_CODES = set(LANGUAGE_FLAGS.values())
DEFAULT_LANGUAGE = 'ta'  # Tamil is the default seed language.
DATE_FORMATS = (
    '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y',
    '%B %d, %Y', '%b %d, %Y', '%d %B %Y', '%d %b %Y',
)


def parse_watchmode_date(value):
    """Return YYYY-MM-DD, or None if the value lacks a usable year."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r'\d{4}', text):
        return f'{text}-01-01'
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def resolve_language_codes(options):
    """Combine --hindi/--tamil/... with --languages; default to Tamil."""
    codes = set(options.get('language_codes') or [])
    if options.get('all_languages'):
        codes.update(LANGUAGE_CODES)
    for code in (options.get('languages') or '').split(','):
        code = code.strip().lower()
        if code:
            codes.add(code)
    if not codes:
        codes = {DEFAULT_LANGUAGE}
    return ','.join(sorted(codes))
CONTENT_TYPE_MAP = {
    'movie': 'movie',
    'tv_movie': 'movie',
    'short_film': 'movie',
    'tv_series': 'tv',
    'tv_miniseries': 'tv',
    'tv_special': 'tv',
}


def movie_defaults_from_watchmode(item, details):
    """Pure mapping: Watchmode JSON -> Movie model defaults (easy to test)."""
    media_type = details.get('type') or item.get('type') or 'movie'
    content_type = CONTENT_TYPE_MAP.get(media_type, 'movie')

    language = details.get('original_language') or 'other'
    if language not in LANGUAGE_CODES:
        language = 'other'

    release_date = parse_watchmode_date(details.get('release_date'))
    if not release_date and details.get('year'):
        year = str(details['year'])[:4]
        if year.isdigit():
            release_date = f'{year}-01-01'

    poster = (
        details.get('posterLarge') or details.get('posterMedium')
        or details.get('poster') or ''
    )
    backdrop = details.get('backdrop') or ''
    if backdrop and not backdrop.startswith(('http://', 'https://')):
        backdrop = ''

    def as_float(value):
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    return {
        'title': details.get('title') or item.get('title') or 'Unknown',
        'original_title': details.get('original_title') or '',
        'content_type': content_type,
        'language': language,
        'poster_path': poster,
        'backdrop_path': backdrop,
        'overview': details.get('plot_overview') or '',
        'vote_average': min(max(as_float(details.get('user_rating')), 0.0), 10.0),
        'vote_count': 0,
        'popularity': as_float(details.get('popularity_percentile')),
        'release_date': release_date,
        'trailer_url': details.get('trailer') or '',
        'adult': False,
    }


class Command(BaseCommand):
    help = 'Bulk-sync movies/TV shows from Watchmode into local PostgreSQL.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--pages', type=int, default=2,
            help='Number of list-titles pages to sync (default: 2).',
        )
        parser.add_argument(
            '--limit', type=int, default=0,
            help='Maximum number of titles to sync (0 = no limit).',
        )
        parser.add_argument(
            '--page-size', type=int, default=50,
            help='Titles per page (default: 50).',
        )
        parser.add_argument(
            '--languages', type=str, default='',
            help='Extra comma-separated ISO 639-1 codes (e.g. ta,en). Default: tamil.',
        )
        parser.add_argument(
            '--all-languages', action='store_true',
            help='Seed all supported languages (Hindi, Tamil, Telugu, Malayalam, Kannada, English).',
        )
        for flag, code in LANGUAGE_FLAGS.items():
            names = [f'--{flag}']
            if flag == 'kannada':
                names.append('--kannadam')
            parser.add_argument(
                *names, action='append_const', const=code, dest='language_codes',
                help=f'Include {flag.title()} titles (repeatable/combinable).',
            )
        parser.add_argument(
            '--skip-cast', action='store_true',
            help='Skip cast/crew enrichment (saves credits).',
        )

    def handle(self, *args, **options):
        pages = options['pages']
        page_size = options['page_size']
        languages = resolve_language_codes(options)
        skip_cast = options['skip_cast']
        limit = options['limit']

        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Watchmode -> PostgreSQL Sync ==='))
        self.stdout.write(f'  Languages: {languages}')

        try:
            quota = watchmode.status()
        except watchmode.WatchmodeError as exc:
            raise CommandError(str(exc))
        self.stdout.write(
            '  Quota: {used}/{total} credits used this month'.format(
                used=quota.get('quotaUsed', '?'), total=quota.get('quota', '?')
            )
        )

        try:
            self._sync_genres()
        except watchmode.WatchmodeError as exc:
            raise CommandError(str(exc))

        created = updated = skipped = 0
        processed = 0
        self.people_cache = {}
        for page in range(1, pages + 1):
            try:
                data = watchmode.list_titles(
                    types='movie,tv_series,tv_miniseries',
                    languages=languages,
                    sort_by='popularity_desc',
                    page=page,
                    limit=page_size,
                )
            except watchmode.WatchmodeError as exc:
                self.stderr.write(f'  Could not fetch page {page}: {exc}')
                break

            titles = data.get('titles', [])
            self.stdout.write(f'  Page {page}: {len(titles)} titles')
            for item in titles:
                if limit and processed >= limit:
                    break
                processed += 1
                label = str(item.get('title') or '')[:38]
                self.stdout.write(
                    f'  [{processed}] {label:<38}', ending='\r'
                )
                self.stdout.flush()

                try:
                    c, u, s = self._upsert_title(item, skip_cast)
                except (watchmode.WatchmodeError, ValidationError,
                        IntegrityError, DataError) as exc:
                    # One malformed title/person must not abort the whole seed.
                    self.stderr.write(f'\n  Skipping {label}: {exc}')
                    c, u, s = 0, 0, 1
                created += c
                updated += u
                skipped += s
                # Stay below Watchmode's ~120 requests/minute limit.
                time.sleep(0.6)
            self.stdout.write('')

            if limit and processed >= limit:
                break
            if page >= data.get('total_pages', page):
                break

        self.stdout.write(self.style.SUCCESS(
            f'\nSync complete: {created} created, {updated} updated, {skipped} skipped.'
        ))

    # ------------------------------------------------------------------
    def _sync_genres(self):
        self.genre_map = {}
        for entry in watchmode.genres() or []:
            name = entry.get('name') or 'Unknown'
            tmdb_id = entry.get('tmdb_id') or None
            genre = Genre.objects.filter(name=name).first()
            if genre is None and tmdb_id is not None:
                genre = Genre.objects.filter(tmdb_id=tmdb_id).first()
            if genre is None:
                genre = Genre(name=name, tmdb_id=tmdb_id)
            genre.name = name
            if genre.tmdb_id is None and tmdb_id is not None:
                genre.tmdb_id = tmdb_id
            genre.save()
            self.genre_map[entry['id']] = genre

    # ------------------------------------------------------------------
    def _upsert_title(self, item, skip_cast):
        tmdb_id = item.get('tmdb_id')
        if not tmdb_id:
            return 0, 0, 1  # cannot use our integer PK without a TMDB ID

        try:
            details = watchmode.title_details(item['id'])
        except watchmode.WatchmodeError as exc:
            self.stderr.write(f'  Details failed for {item.get("title")}: {exc}')
            return 0, 0, 1
        if not details:
            return 0, 0, 1

        defaults = movie_defaults_from_watchmode(item, details)

        # TMDB movie IDs and TV IDs can collide; never clobber the other type.
        existing = Movie.objects.filter(tmdb_id=tmdb_id).first()
        if existing and existing.content_type != defaults['content_type']:
            return 0, 0, 1

        with transaction.atomic():
            movie, is_new = Movie.objects.update_or_create(
                tmdb_id=tmdb_id, defaults=defaults
            )
            self._link_genres(movie, details)
            if not skip_cast:
                self._sync_credits(movie, item['id'])

        return (1 if is_new else 0), (0 if is_new else 1), 0

    # ------------------------------------------------------------------
    def _link_genres(self, movie, details):
        genre_ids = details.get('genres') or []
        genres = [self.genre_map.get(gid) for gid in genre_ids]
        genres = [g for g in genres if g is not None]
        if not genres and details.get('genre_names'):
            genres = list(Genre.objects.filter(name__in=details['genre_names']))
        if genres:
            movie.genres.add(*genres)

    # ------------------------------------------------------------------
    def _sync_credits(self, movie, watchmode_id):
        try:
            credits = watchmode.title_cast_crew(watchmode_id) or []
        except watchmode.WatchmodeError:
            return

        for credit in credits:
            if credit.get('type') != 'Crew':
                continue
            role_name = str(credit.get('role') or '')
            lowered = role_name.lower()
            if role_name in ('Director', 'Creator', 'Co-Director'):
                target = 'Director'
            elif 'music' in lowered or role_name in ('Composer',):
                target = 'Music Director'
            else:
                continue
            person = self._person(credit, info={})  # name only, saves credits
            MovieCrew.objects.get_or_create(
                movie=movie, person=person, role=target
            )

        cast = [c for c in credits if c.get('type') == 'Cast']
        cast.sort(key=lambda c: c.get('order') or 999)
        has_actor = has_actress = False
        for credit in cast[:2]:
            if has_actor and has_actress:
                break
            info = self._person_info(credit['person_id'])
            gender = str(info.get('gender') or '').lower()
            if gender.startswith('f') and not has_actress:
                role, has_actress = 'Main Actress', True
            elif not has_actor:
                role, has_actor = 'Main Actor', True
            else:
                continue
            person = self._person(credit, info=info)
            MovieCrew.objects.get_or_create(
                movie=movie, person=person, role=role
            )

    # ------------------------------------------------------------------
    def _person_info(self, person_id):
        """Cache person lookups — actors recur across many titles."""
        if person_id not in self.people_cache:
            try:
                self.people_cache[person_id] = watchmode.person(person_id) or {}
            except watchmode.WatchmodeError:
                self.people_cache[person_id] = {}
            time.sleep(0.3)
        return self.people_cache[person_id]

    def _person(self, credit, info=None):
        if info is None:
            info = self._person_info(credit['person_id'])

        name = credit.get('full_name') or info.get('full_name') or 'Unknown'
        tmdb_id = info.get('tmdb_id') or None
        fields = {'name': name}
        gender = str(info.get('gender') or '').lower()
        if gender.startswith('f'):
            fields['gender'] = 1
        elif gender.startswith('m'):
            fields['gender'] = 2
        if info.get('biography'):
            fields['biography'] = info['biography']
        if info.get('place_of_birth'):
            fields['place_of_birth'] = info['place_of_birth']
        for source, target in (('date_of_birth', 'birthday'), ('date_of_death', 'deathday')):
            parsed = parse_watchmode_date(info.get(source))
            if parsed:
                fields[target] = parsed

        if tmdb_id:
            person, _ = Person.objects.update_or_create(tmdb_id=tmdb_id, defaults=fields)
        else:
            person, _ = Person.objects.get_or_create(name=name, defaults=fields)
        return person
