from __future__ import annotations

from typing import Optional

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.sessions.backends.base import SessionBase
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory

from visitors.decorators import user_is_visitor
from visitors.models import Visitor, VisitorLog


@pytest.fixture
def visitor() -> Visitor:
    return Visitor.objects.create(email="fred@example.com", scope="foo")


@pytest.fixture
def user() -> User:
    return User.objects.create(username="Fred")


@pytest.mark.django_db
class TestDecorators:
    def _request(
        self, user: Optional[User] = None, visitor: Optional[Visitor] = None
    ) -> HttpRequest:
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user or AnonymousUser()
        request.visitor = visitor
        request.user.is_visitor = visitor is not None
        request.session = SessionBase()
        return request

    def test_no_access(self) -> None:
        request = self._request()

        @user_is_visitor(scope="foo")
        def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("OK")

        with pytest.raises(PermissionDenied):
            _ = view(request)

    def test_incorrect_scope(self, visitor: Visitor) -> None:
        request = self._request(visitor=visitor)

        @user_is_visitor(scope="bar")
        def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("OK")

        with pytest.raises(PermissionDenied):
            _ = view(request)

    def test_correct_scope(self, visitor: Visitor) -> None:
        request = self._request(visitor=visitor)

        @user_is_visitor(scope="foo")
        def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("OK")

        response = view(request)
        assert response.status_code == 200
        assert response.content == b"OK"

    def test_any_scope(self, visitor: Visitor) -> None:
        request = self._request(visitor=visitor)

        @user_is_visitor(scope="*")
        def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("OK")

        response = view(request)
        assert response.status_code == 200
        assert response.content == b"OK"

    def test_bypass__True(self, user: User) -> None:
        """Check that the bypass param works."""
        request = self._request(user=user)

        @user_is_visitor(scope="foo", bypass_func=lambda r: True)
        def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("OK")

        response = view(request)
        assert response.status_code == 200
        assert response.content == b"OK"

    def test_bypass__False(self, user: User) -> None:
        request = self._request(user=user)

        @user_is_visitor(scope="foo", bypass_func=lambda r: False)
        def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("OK")

        with pytest.raises(PermissionDenied):
            _ = view(request)

    def test_logging(self, visitor: Visitor) -> None:
        request = self._request(visitor=visitor)

        @user_is_visitor(scope="foo")
        def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("OK")

        response = view(request)
        log: VisitorLog = VisitorLog.objects.get()
        assert response.status_code == 200
        assert log.status_code == 200

    def test_logging__False(self, visitor: Visitor) -> None:
        request = self._request(visitor=visitor)

        @user_is_visitor(scope="foo", log_visit=False)
        def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("OK")

        _ = view(request)
        assert VisitorLog.objects.count() == 0

    # able to access when max visits not reached is covered by other tests implicitly

    def test_when_maximum_visits_reached_then_permission_denied(
        self, visitor: Visitor
    ) -> None:
        visitor.max_number_of_visits = 2
        visitor.save()
        request = self._request(visitor=visitor)

        @user_is_visitor(scope="foo")
        def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("OK")

        response_1 = view(request)
        response_2 = view(request)

        for response in [response_1, response_2]:
            assert response.status_code == 200
            assert response.content == b"OK"

        # assert throws on the 3rd attempt to access
        with pytest.raises(PermissionDenied):
            _ = view(request)

    def test_when_maximum_visits_exceeded_then_permission_denied(
        self, visitor: Visitor
    ) -> None:
        visitor.max_number_of_visits = 1
        visitor.save()
        request = self._request(visitor=visitor)

        @user_is_visitor(scope="foo")
        def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("OK")

        response = view(request)

        with pytest.raises(PermissionDenied):
            _ = view(request)

        # assert throws on subsequent attempts to access
        with pytest.raises(PermissionDenied):
            _ = view(request)

    # Would parameterise these better to test muliple different "max_number_of_visits"
    # and large numbers of attempts to access
