import json
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .management.commands.sync_watchmode import (
    Command as WatchmodeCommand,
    movie_defaults_from_watchmode,
    parse_watchmode_date,
    resolve_language_codes,
)
from .models import EmotionLog, Genre, Movie, MovieGenre, Review, WatchHistory
from .services import watchmode


class ReviewApiTests(TestCase):
    def setUp(self):
        self.movie = Movie.objects.create(
            tmdb_id=1001,
            title='Test Movie',
            content_type='movie',
            language='hi',
        )
        self.url = reverse('add_review')

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_valid_review_is_saved_with_sentiment(self):
        response = self._post({
            'tmdb_id': self.movie.tmdb_id,
            'rating': 5,
            'review_text': 'This was a wonderful and delightful film.',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        review = Review.objects.get()
        self.assertEqual(review.rating, 5)
        self.assertIsNotNone(review.sentiment_score)

    def test_out_of_range_rating_is_rejected(self):
        for rating in (0, 6, -1, 99):
            response = self._post({
                'tmdb_id': self.movie.tmdb_id,
                'rating': rating,
                'review_text': 'Test',
            })
            self.assertEqual(response.status_code, 400)
        self.assertEqual(Review.objects.count(), 0)

    def test_non_integer_rating_is_rejected(self):
        response = self._post({
            'tmdb_id': self.movie.tmdb_id,
            'rating': 'not-a-number',
            'review_text': 'Test',
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Review.objects.count(), 0)

    def test_review_text_must_be_a_string(self):
        response = self._post({
            'tmdb_id': self.movie.tmdb_id,
            'rating': 5,
            'review_text': 12345,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Review.objects.count(), 0)

    def test_unknown_movie_returns_404(self):
        response = self._post({
            'tmdb_id': 999999,
            'rating': 5,
            'review_text': 'Test',
        })
        self.assertEqual(response.status_code, 404)


class SearchTests(TestCase):
    def setUp(self):
        Movie.objects.create(
            tmdb_id=2001, title='The Great Adventure',
            overview='An epic journey', poster_path='/poster.jpg',
        )

    def test_malformed_search_query_does_not_error(self):
        # The TS query parser rejects unmatched quotes, but the view must not 500.
        response = self.client.get(reverse('search_results'), {'query': '"unbalanced'})
        self.assertEqual(response.status_code, 200)

    def test_normal_search_returns_matches(self):
        response = self.client.get(reverse('search_results'), {'query': 'Adventure'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The Great Adventure')

    def test_postgres_parser_error_falls_back_to_icontains(self):
        # Simulate the PostgreSQL path and a query the TS parser rejects.
        with patch('movie.views.connection') as mock_connection:
            mock_connection.vendor = 'postgresql'
            with patch('movie.views.SearchQuery', side_effect=ValidationError('bad')):
                response = self.client.get(
                    reverse('search_results'), {'query': 'Adventure'}
                )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The Great Adventure')


class DetailViewTests(TestCase):
    def test_year_is_none_when_release_date_missing(self):
        movie = Movie.objects.create(tmdb_id=3001, title='Undated')
        self.assertIsNone(movie.year)

    def test_tv_detail_uses_tmdb_genre_id(self):
        genre = Genre.objects.create(tmdb_id=987, name='Drama')
        show = Movie.objects.create(
            tmdb_id=3002, title='Test Show', content_type='tv', language='hi'
        )
        MovieGenre.objects.create(movie=show, genre=genre)
        response = self.client.get(reverse('show_details', args=[show.tmdb_id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['genres'][0]['id'], genre.tmdb_id)
        self.assertNotEqual(response.context['genres'][0]['id'], genre.id)


class InteractionApiTests(TestCase):
    def test_watch_history_is_recorded_for_logged_in_user(self):
        from django.contrib.auth.models import User

        user = User.objects.create_user(username='viewer', password='pass12345')
        self.client.force_login(user)
        movie = Movie.objects.create(tmdb_id=4001, title='Watched Movie')
        response = self.client.post(
            reverse('add_watch_history'),
            data=json.dumps({'tmdb_id': movie.tmdb_id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WatchHistory.objects.count(), 1)

    def test_anonymous_watch_history_is_skipped(self):
        movie = Movie.objects.create(tmdb_id=4002, title='Anon Watched')
        response = self.client.post(
            reverse('add_watch_history'),
            data=json.dumps({'tmdb_id': movie.tmdb_id}),
            content_type='application/json',
        )
        self.assertEqual(response.json()['status'], 'skipped')
        self.assertEqual(WatchHistory.objects.count(), 0)

    def test_emotion_log_rejects_invalid_emotion(self):
        response = self.client.post(
            reverse('add_emotion_log'),
            data=json.dumps({'emotion': 'not-an-emotion'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(EmotionLog.objects.count(), 0)

    def test_emotion_log_accepts_valid_emotion(self):
        response = self.client.post(
            reverse('add_emotion_log'),
            data=json.dumps({'emotion': 'Happy'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(EmotionLog.objects.get().emotion, 'happy')


class WatchmodeSyncTests(TestCase):
    def test_mapping_watchmode_to_movie_defaults(self):
        defaults = movie_defaults_from_watchmode(
            {'id': 1, 'title': 'Fallback', 'tmdb_id': 123, 'type': 'movie'},
            {
                'title': 'Real Title',
                'type': 'movie',
                'original_language': 'ta',
                'release_date': '2024-05-01',
                'posterLarge': 'https://img.example/poster.jpg',
                'user_rating': 8.4,
                'popularity_percentile': 97.5,
                'plot_overview': 'A Tamil film.',
            },
        )
        self.assertEqual(defaults['title'], 'Real Title')
        self.assertEqual(defaults['content_type'], 'movie')
        self.assertEqual(defaults['language'], 'ta')
        self.assertEqual(defaults['vote_average'], 8.4)
        self.assertEqual(defaults['poster_path'], 'https://img.example/poster.jpg')

    def test_absolute_poster_url_is_passed_through(self):
        movie = Movie.objects.create(
            tmdb_id=7001, title='Poster Test',
            poster_path='https://img.example/p.jpg',
            backdrop_path='https://img.example/b.jpg',
        )
        self.assertEqual(movie.poster_url, 'https://img.example/p.jpg')
        self.assertEqual(movie.backdrop_url, 'https://img.example/b.jpg')

    def test_sync_command_upserts_movie_and_genre(self):
        details = {
            'title': 'Hindi Hit',
            'type': 'movie',
            'original_language': 'hi',
            'release_date': '2024-05-01',
            'posterLarge': 'https://img.example/p.jpg',
            'user_rating': 8.0,
            'popularity_percentile': 95.0,
            'genres': [4],
            'plot_overview': 'A story.',
        }
        with patch.object(watchmode, 'status', return_value={'quota': 2500, 'quotaUsed': 0}), \
             patch.object(watchmode, 'genres', return_value=[
                 {'id': 4, 'name': 'Comedy', 'tmdb_id': 35}
             ]), \
             patch.object(watchmode, 'list_titles', return_value={
                 'titles': [{'id': 1, 'tmdb_id': 123, 'title': 'Hindi Hit', 'type': 'movie'}],
                 'total_pages': 1,
             }), \
             patch.object(watchmode, 'title_details', return_value=details), \
             patch.object(watchmode, 'title_cast_crew', return_value=[]):
            call_command('sync_watchmode', pages=1)

        movie = Movie.objects.get(tmdb_id=123)
        self.assertEqual(movie.title, 'Hindi Hit')
        self.assertEqual(movie.language, 'hi')
        self.assertEqual(movie.poster_url, 'https://img.example/p.jpg')
        self.assertTrue(movie.genres.filter(name='Comedy').exists())

    def test_parse_watchmode_date(self):
        self.assertEqual(parse_watchmode_date('1963-12-18'), '1963-12-18')
        self.assertEqual(parse_watchmode_date('1963'), '1963-01-01')
        self.assertEqual(parse_watchmode_date('February 2, 1963'), '1963-02-02')
        self.assertIsNone(parse_watchmode_date('February 2'))
        self.assertIsNone(parse_watchmode_date('not a date'))

    def test_language_resolution_defaults_to_tamil(self):
        self.assertEqual(resolve_language_codes({}), 'ta')
        self.assertEqual(
            resolve_language_codes({'language_codes': ['ta', 'en']}), 'en,ta'
        )
        self.assertEqual(
            resolve_language_codes({
                'language_codes': ['ta'],
                'all_languages': True,
            }),
            'en,hi,kn,ml,ta,te',
        )
        self.assertEqual(resolve_language_codes({'languages': 'te,hi'}), 'hi,te')

    def test_command_defaults_to_tamil_titles(self):
        details = {'title': 'Tamil Film', 'type': 'movie', 'original_language': 'ta'}
        with patch.object(watchmode, 'status', return_value={'quota': 2500, 'quotaUsed': 0}), \
             patch.object(watchmode, 'genres', return_value=[]), \
             patch.object(watchmode, 'list_titles', return_value={
                 'titles': [{'id': 9, 'tmdb_id': 999, 'title': 'Tamil Film'}],
                 'total_pages': 1,
             }) as list_titles, \
             patch.object(watchmode, 'title_details', return_value=details), \
             patch.object(watchmode, 'title_cast_crew', return_value=[]):
            call_command('sync_watchmode', pages=1, limit=1)
        self.assertEqual(list_titles.call_args.kwargs['languages'], 'ta')

    def test_partial_person_date_does_not_crash(self):
        command = WatchmodeCommand()
        person = command._person(
            {'person_id': 1, 'full_name': 'Test Person'},
            info={'full_name': 'Test Person', 'date_of_birth': 'February 2'},
        )
        self.assertIsNone(person.birthday)

    @override_settings(WATCHMODE_API_KEY='test-key')
    def test_404_is_not_retried(self):
        response = Mock(status_code=404, headers={})
        with patch.object(watchmode.requests, 'get', return_value=response) as get:
            with self.assertRaises(watchmode.WatchmodeError):
                watchmode.title_details(123)
        self.assertEqual(get.call_count, 1)
