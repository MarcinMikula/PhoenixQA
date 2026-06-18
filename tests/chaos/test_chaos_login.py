"""
test_chaos_login.py
Baseline tests for Chaos App login form.
These tests WILL fail without healing — that's the point.
With PhoenixQA healing active, they self-repair.
"""
import pytest
from pages.chaos_login_page import ChaosLoginPage
from config.settings import Settings


@pytest.mark.chaos
class TestChaosLogin:
    def test_successful_login(self, page):
        """Happy path — valid credentials, expect welcome message."""
        login_page = ChaosLoginPage(page, Settings())
        login_page.open()
        login_page.login("admin", "secret")
        assert login_page.is_visible(login_page.MSG_WELCOME)

    def test_invalid_credentials(self, page):
        """Sad path — wrong password, expect error message."""
        login_page = ChaosLoginPage(page, Settings())
        login_page.open()
        login_page.login("admin", "wrongpassword")
        assert login_page.is_visible(login_page.MSG_ERROR)
