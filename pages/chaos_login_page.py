"""
chaos_login_page.py
Page Object for Chaos App login form.
Selectors will intentionally break — PhoenixQA heals them.
Mirrors qa-automation-framework LoginPage pattern.
"""
from pages.base_page import BasePage
from config.settings import Settings


class ChaosLoginPage(BasePage):
    URL = "/"

    # Selectors — will mutate in Chaos App (that's the whole point)
    INPUT_USERNAME = "[data-testid='username']"
    INPUT_PASSWORD = "[data-testid='password']"
    BTN_SUBMIT = "[data-testid='btn-login']"
    MSG_WELCOME = "[data-testid='welcome-message']"
    MSG_ERROR = "[data-testid='login-error']"

    def open(self):
        self.navigate(f"{self.settings.chaos_app_url}{self.URL}")

    def login(self, username: str, password: str):
        self.fill(self.INPUT_USERNAME, username, healing=True)
        self.fill(self.INPUT_PASSWORD, password, healing=True)
        self.click(self.BTN_SUBMIT, healing=True)

    def get_welcome_message(self) -> str:
        return self.get_text(self.MSG_WELCOME)

    def get_error_message(self) -> str:
        return self.get_text(self.MSG_ERROR)
