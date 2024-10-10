import pytest
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import QuerySet, Value
from django.db.models.functions import Concat
from django.urls import path, reverse
from django_restql.mixins import DynamicFieldsMixin, OptimizedEagerLoadingMixin
from model_bakery import baker
from rest_framework import serializers, status
from rest_framework.generics import ListAPIView, UpdateAPIView

from tests.testapp.models import SampleAuthor, SamplePost, SampleTag
from tests.testapp.tests.helpers import get_fields_queried


class SampleAuthorSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = SampleAuthor
        fields = ("id", "first_name", "last_name")


class ShortSamplePostSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = SamplePost
        fields = ("id", "text")


class SampleAuthorFullSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    posts = ShortSamplePostSerializer(many=True)

    class Meta:
        model = SampleAuthor
        fields = ("id", "first_name", "last_name", "posts")


class SamplePostSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    author = SampleAuthorSerializer(required=False)
    first_letter = serializers.SerializerMethodField()
    author_str = serializers.StringRelatedField(source="author")

    class Meta:
        model = SamplePost
        fields = ("id", "text", "title", "author", "first_letter", "author_str")
        read_only_fields = fields

    def get_first_letter(self, obj):
        return obj.title[0]

class SamplePostWithAnnotationSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    author_full_name = serializers.CharField()

    class Meta:
        model = SamplePost
        fields = ("id", "author_full_name")
        read_only_fields = fields


class SampleTagSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = SampleTag
        fields = "__all__"


class SamplePostSerializerAllFieldsSerializer(SamplePostSerializer):
    tags = SampleTagSerializer(many=True)

    class Meta:
        model = SamplePost
        fields = "__all__"


class SamplePostSmallSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = SamplePost
        fields = ("id", "text")


class SampleViewSet(
    OptimizedEagerLoadingMixin,
    UpdateAPIView,
    ListAPIView,
):
    queryset = SamplePost.objects.all()
    serializer_class = SamplePostSerializer
    permission_classes = []
    select_related = {"author": "author"}
    prefetch_related = {}
    only = {
        "first_letter": ["title"],
        "author_str": "author__first_name",
    }
    pagination_class = None
    always_apply_only = True


class SamplePostWithAnnotationView(
    OptimizedEagerLoadingMixin, UpdateAPIView, ListAPIView
):
    queryset = SamplePost.objects.all()
    serializer_class = SamplePostWithAnnotationSerializer
    permission_classes = []
    only = {"author_full_name": []}
    pagination_class = None
    always_apply_only = True
    annotated_fields = ("author_full_name",)

    @staticmethod
    def annotate_author_full_name(queryset: QuerySet[SamplePost]):
        return queryset.annotate(
            author_full_name=Concat(
                "author__first_name", Value(" "), "author__last_name",
                output_field=models.CharField(),
            ),
        )


class SampleAuthorViewSet(
    OptimizedEagerLoadingMixin,
    ListAPIView,
):
    queryset = SampleAuthor.objects.all()
    serializer_class = SampleAuthorFullSerializer
    permission_classes = []
    select_related = {}
    prefetch_related = {"posts": "posts"}
    pagination_class = None
    always_apply_only = True


urlpatterns = [
    path("", SampleViewSet.as_view(), name="view"),
    path("<int:pk>", SampleViewSet.as_view(), name="view-update"),
    path("authors/", SampleAuthorViewSet.as_view(), name="authors-view"),
    path(
        "posts-with-annotation/",
        SamplePostWithAnnotationView.as_view(),
        name="posts-annotation-view",
    ),
]


@pytest.mark.django_db
@pytest.mark.urls(__name__)
class TestOnlyInEagerLoading:
    @pytest.fixture
    def instance(self):
        return baker.make(SamplePost)

    @pytest.fixture
    def url(self):
        return reverse("view")

    def test_fields_correctly_selected(
        self, client, django_assert_max_num_queries, instance, url
    ):
        with django_assert_max_num_queries(1) as x:
            client.get(url, {"query": "{title,author{id}}"})
            expected_fields = {
                "samplepost.id",
                "samplepost.author_id",
                "samplepost.title",
                "sampleauthor.id",
            }
            assert expected_fields == get_fields_queried(x)

    def test_multiple_records(self, client, django_assert_max_num_queries, url):
        baker.make(SamplePost, _quantity=10)
        with django_assert_max_num_queries(1):
            client.get(url, {"query": "{title,author{id}}"})

    def test_no_query(self, client, django_assert_max_num_queries, instance, url):
        with django_assert_max_num_queries(1) as x:
            response = client.get(url)
            assert response.status_code == status.HTTP_200_OK
            expected_fields = {
                "samplepost.id",
                "samplepost.title",
                "samplepost.author_id",
                "samplepost.text",
                "sampleauthor.id",
                "sampleauthor.first_name",
                "sampleauthor.last_name",
            }
            assert expected_fields == get_fields_queried(x)

    def test_using_all_fields(
        self, client, django_assert_max_num_queries, instance, url
    ):
        with django_assert_max_num_queries(1) as x:
            client.get(url, {"query": "{*}"})
            expected_fields = {
                "samplepost.id",
                "samplepost.title",
                "samplepost.author_id",
                "samplepost.text",
                "sampleauthor.id",
                "sampleauthor.first_name",
                "sampleauthor.last_name",
            }
            assert expected_fields == get_fields_queried(x)

    def test_custom_only(self, client, django_assert_max_num_queries, instance, url):
        with django_assert_max_num_queries(1) as x:
            client.get(url, {"query": "{first_letter}"})
            expected_fields = {
                "samplepost.id",
                "samplepost.title",
            }
            assert expected_fields == get_fields_queried(x)

    def test_custom_only_in_foreign_key(
        self, client, django_assert_max_num_queries, instance, url
    ):
        with django_assert_max_num_queries(1) as x:
            client.get(url, {"query": "{author_str}"})
            expected_fields = {
                "samplepost.id",
                "samplepost.author_id",
                "sampleauthor.first_name",
                "sampleauthor.id",
            }
            assert expected_fields == get_fields_queried(x)

    def test_using_nested_all_fields(
        self, client, django_assert_max_num_queries, instance, url
    ):
        with django_assert_max_num_queries(1) as x:
            client.get(url, {"query": "{author{*}}"})
            expected_fields = {
                "samplepost.id",
                "samplepost.author_id",
                "sampleauthor.id",
                "sampleauthor.first_name",
                "sampleauthor.last_name",
            }
            assert expected_fields == get_fields_queried(x)

    def test_using_exclude_operator(
        self, client, django_assert_max_num_queries, instance, url
    ):
        with django_assert_max_num_queries(1) as x:
            response = client.get(url, {"query": "{-text, author{-first_name}}"})
            assert response.status_code == status.HTTP_200_OK
            expected_fields = {
                "samplepost.id",
                "samplepost.title",
                "samplepost.author_id",
                "samplepost.text",
                "sampleauthor.id",
                "sampleauthor.first_name",
                "sampleauthor.last_name",
            }
            assert expected_fields == get_fields_queried(x)

    def test_incorrect_view(
        self, client, django_assert_max_num_queries, instance, url, monkeypatch
    ):
        monkeypatch.setattr(SampleViewSet, "only", {"author_str": "author__first_name"})
        with pytest.raises(FieldDoesNotExist):
            client.get(url)

    def test_m2m_field(
        self, client, django_assert_max_num_queries, instance, url, monkeypatch
    ):
        monkeypatch.setattr(SampleViewSet, "prefetch_related", {"tags": "tags"})
        monkeypatch.setattr(
            SampleViewSet,
            "serializer_class",
            SamplePostSerializerAllFieldsSerializer,
        )
        tag = baker.make(SampleTag)
        instance.tags.add(tag)

        with django_assert_max_num_queries(2) as x:
            response = client.get(url, {"query": "{text, tags{name}}"})
            assert response.status_code == status.HTTP_200_OK
            expected_fields = {
                "samplepost.text",
                "samplepost.id",
            }
            assert expected_fields == get_fields_queried(x)

    def test_m2m_field_no_query(
        self, client, django_assert_max_num_queries, instance, url, monkeypatch
    ):
        monkeypatch.setattr(SampleViewSet, "prefetch_related", {"tags": "tags"})
        monkeypatch.setattr(
            SampleViewSet,
            "serializer_class",
            SamplePostSerializerAllFieldsSerializer,
        )
        tag = baker.make(SampleTag)
        instance.tags.add(tag)

        with django_assert_max_num_queries(2) as x:
            response = client.get(url)
            assert response.status_code == status.HTTP_200_OK
            expected_fields = {
                "samplepost.id",
                "samplepost.text",
                "samplepost.title",
                "samplepost.author_id",
                "sampleauthor.id",
                "sampleauthor.first_name",
                "sampleauthor.last_name",
            }
            assert expected_fields == get_fields_queried(x)

    def test_no_query_only_serializer_fields(
        self, client, django_assert_max_num_queries, instance, url, monkeypatch
    ):
        monkeypatch.setattr(
            SampleViewSet, "serializer_class", SamplePostSmallSerializer
        )
        monkeypatch.setattr(SampleViewSet, "select_related", {})
        monkeypatch.setattr(SampleViewSet, "only", {})

        with django_assert_max_num_queries(1) as x:
            client.get(url)
            expected_fields = {
                "samplepost.id",
                "samplepost.text",
            }
            assert expected_fields == get_fields_queried(x)

    def test_force_query_usage(
        self, client, instance, url, settings
    ):
        settings.RESTQL = {"FORCE_QUERY_USAGE": True}

        response = client.get(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        response = client.get(url, {"query": "{text}"})
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.parametrize(
        ("settings_force_flag", "view_force_flag", "status_code"),
        (
            (False, True, status.HTTP_400_BAD_REQUEST),
            (False, False, status.HTTP_200_OK),
            (True, True, status.HTTP_400_BAD_REQUEST),
            (True, False, status.HTTP_200_OK),
        )
    )
    def test_force_query_usage_defined_in_view(
        self,
        client,
        instance,
        settings,
        settings_force_flag,
        monkeypatch,
        url,
        view_force_flag,
        status_code,
    ):
        monkeypatch.setattr(SampleViewSet, "force_query_usage", view_force_flag)
        settings.RESTQL = {"FORCE_QUERY_USAGE": settings_force_flag}

        response = client.get(url)
        assert response.status_code == status_code

    def test_dont_force_query_usage_on_put_method(
        self, client, instance, url, settings
    ):
        settings.RESTQL = {"FORCE_QUERY_USAGE": True}
        url = reverse("view-update", args=(instance.id,))

        response = client.put(url)
        assert response.status_code == status.HTTP_200_OK

    def test_using_aliases(
        self, client, django_assert_max_num_queries, instance, url, settings
    ):
        with django_assert_max_num_queries(1) as x:
            response = client.get(
                url, {"query": "{postTitle: title, author{firstName: first_name}}"}
            )
            assert response.status_code == status.HTTP_200_OK
            expected_fields = {
                "samplepost.id",
                "samplepost.title",
                "samplepost.author_id",
                "sampleauthor.first_name",
                "sampleauthor.id",
            }
            assert expected_fields == get_fields_queried(x)

    def test_incorrect_parameters(
        self, client, django_assert_max_num_queries, instance, url, settings
    ):
        with django_assert_max_num_queries(1) as x:
            response = client.get(
                url, {"query": "{title, incorrect, author{first_name, test}}"}
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            expected_fields = {
                "samplepost.id",
                "samplepost.title",
                "samplepost.author_id",
                "sampleauthor.first_name",
                "sampleauthor.id",
            }
            assert expected_fields == get_fields_queried(x)


    def test_many_to_one_rel_ignored_when_no_query(
        self, client, django_assert_max_num_queries, instance
    ):
        url = reverse("authors-view")

        with django_assert_max_num_queries(2) as x:
            response = client.get(url, {"query": "{first_name,posts{id}}"})
            assert response.status_code == status.HTTP_200_OK
            expected_fields = {
                "sampleauthor.first_name",
                "sampleauthor.id",
            }
            assert expected_fields == get_fields_queried(x)

@pytest.mark.django_db
@pytest.mark.urls(__name__)
class TestSamplePostWithAnnotationView:
    @pytest.fixture
    def url(self):
        return reverse("posts-annotation-view")

    def test_annotated_author_full_name(self, client, url):
        baker.make(SamplePost, author__first_name="John", author__last_name="Doe")

        response = client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data[0]["author_full_name"] == "John Doe"

    def test_query_author_full_name(self, client, url):
        baker.make(SamplePost, author__first_name="John", author__last_name="Doe")

        response = client.get(url, {"query": "{author_full_name}"})

        assert response.status_code == status.HTTP_200_OK
        assert response.data[0]["author_full_name"] == "John Doe"

    def test_author_full_name_not_queried(self, client, url, django_assert_max_num_queries):
        baker.make(SamplePost, author__first_name="John", author__last_name="Doe")

        with django_assert_max_num_queries(1) as x:
            client.get(url, {"query": "{id}"})
            expected_fields = {
                "samplepost.id",
            }
            assert expected_fields == get_fields_queried(x)