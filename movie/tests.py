import json

from django.test import TestCase
from django.urls import reverse

from .models import EmotionLog, Genre, Movie, MovieGenre, Review, WatchHistory


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
    def test_watch_history_is_recorded(self):
        movie = Movie.objects.create(tmdb_id=4001, title='Watched Movie')
        response = self.client.post(
            reverse('add_watch_history'),
            data=json.dumps({'tmdb_id': movie.tmdb_id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WatchHistory.objects.count(), 1)

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
