import pytest
from django.conf import settings
from django.urls import path, reverse
from django.utils import translation

from django_restql.mixins import DynamicFieldsMixin, OptimizedEagerLoadingMixin
from model_bakery import baker
from rest_framework import serializers, status
from rest_framework.generics import ListAPIView

from tests.testapp.models import SamplePlace, SampleEvent
from tests.testapp.tests.helpers import get_fields_queried


class SamplePlaceSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = SamplePlace
        fields = ("id", "name", "address", "slug")


class SampleEventSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    place = SamplePlaceSerializer()

    class Meta:
        model = SampleEvent
        fields = ("id", "title", "description", "place", "type")


class SampleEventViewSet(
    OptimizedEagerLoadingMixin,
    ListAPIView,
):
    queryset = SampleEvent.objects.all()
    serializer_class = SampleEventSerializer
    permission_classes = []
    select_related = {"place": "place"}
    pagination_class = None
    always_apply_only = True


urlpatterns = [path("", SampleEventViewSet.as_view(), name="view")]


@pytest.mark.django_db
class TestTranslatedFieldsInEagerLoading:
    @pytest.fixture
    def instance(self):
        return baker.make(SampleEvent)

    @pytest.fixture
    def url(self):
        return reverse("view")

    @pytest.mark.parametrize(
        "language", [language for language, _ in settings.LANGUAGES]
    )
    @pytest.mark.urls(__name__)
    def test_translated_fields(
        self, client, django_assert_max_num_queries, instance, url, language
    ):
        with django_assert_max_num_queries(1) as x:
            with translation.override(language):
                response = client.get(
                    url, {"query": "{title,type}"}
                )

            assert response.status_code == status.HTTP_200_OK
            expected_fields = {
                "sampleevent.id",
                f"sampleevent.title_{language}",
                "sampleevent.type",
            }
            assert expected_fields == get_fields_queried(x)

    @pytest.mark.parametrize(
        "language", [language for language, _ in settings.LANGUAGES]
    )
    @pytest.mark.urls(__name__)
    def test_translated_fields_with_fk(
        self, client, django_assert_max_num_queries, instance, url, language
    ):
        with django_assert_max_num_queries(1) as x:
            with translation.override(language):
                response = client.get(
                    url,
                    {"query": "{title,type,place{address, name}}"},
                    HTTP_ACCEPT_LANGUAGE=language,
                )
            assert response.status_code == status.HTTP_200_OK
            expected_fields = {
                "sampleevent.id",
                f"sampleevent.title_{language}",
                "sampleevent.type",
                "sampleevent.place_id",
                "sampleplace.id",
                f"sampleplace.name_{language}",
                "sampleplace.address",
            }
            assert expected_fields == get_fields_queried(x)

    @pytest.mark.urls(__name__)
    def test_all_fields(self, client, django_assert_max_num_queries, instance, url):
        with django_assert_max_num_queries(1) as x:
            response = client.get(url)
            assert response.status_code == status.HTTP_200_OK
            expected_fields = {
                "sampleevent.id",
                "sampleevent.title_pl",
                "sampleevent.description_pl",
                "sampleevent.type",
                "sampleevent.place_id",
                "sampleplace.id",
                "sampleplace.name_pl",
                "sampleplace.name_en",
                "sampleplace.address",
                "sampleplace.slug",
            }
            assert expected_fields == get_fields_queried(x)
