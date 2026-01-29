"""
Browser automation client for Opal interactions.
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:
    import undetected_chromedriver as uc

    USE_UNDETECTED = True
except ImportError:
    USE_UNDETECTED = False

from .config import ServerConfig
from .exceptions import AuthenticationError, OpalError


class OpalClient:
    """High-level client for Opal automation"""

    def __init__(self, config: ServerConfig):
        self.config = config
        self.driver: Optional[webdriver.Chrome] = None
        self._is_authenticated = False

    async def start(self) -> None:
        """Start browser session"""
        await asyncio.get_event_loop().run_in_executor(None, self._start_browser)

    def _start_browser(self) -> None:
        """Initialize browser with proper configuration"""
        if USE_UNDETECTED:
            logger.info("Using undetected-chromedriver for Opal compatibility")

            if self.config.auth.use_persistent_session:
                profile_path = Path(self.config.auth.profile_dir).absolute()
                profile_path.mkdir(exist_ok=True)

            options = uc.ChromeOptions()
            if self.config.auth.use_persistent_session:
                options.add_argument(f"--user-data-dir={profile_path}")
            options.add_argument("--no-first-run")
            options.add_argument("--no-default-browser-check")
            options.add_argument("--disable-extensions")

            if self.config.headless:
                options.add_argument("--headless=new")

            self.driver = uc.Chrome(options=options, version_main=None)
        else:
            logger.warning("undetected-chromedriver not available, using regular Selenium")
            self._start_regular_chrome()

        if self.driver is None:
            raise RuntimeError("Failed to initialize Opal browser driver")
        self.driver.set_page_load_timeout(self.config.timeout)

    def _start_regular_chrome(self) -> None:
        """Fallback Chrome initialization"""
        opts = ChromeOptions()

        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)

        opts.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        if self.config.headless:
            opts.add_argument("--headless=new")

        self.driver = webdriver.Chrome(options=opts)

        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

    async def authenticate(self) -> bool:
        """Authenticate with Opal"""
        if not self.driver:
            raise AuthenticationError("Opal browser not started")

        return await asyncio.get_event_loop().run_in_executor(
            None, self._authenticate_sync
        )

    def _authenticate_sync(self) -> bool:
        """Synchronous authentication logic"""
        if self.driver is None:
            raise RuntimeError("Opal browser driver not initialized")

        target_url = self.config.opal.base_url
        logger.info(f"Navigating to Opal: {target_url}")
        self.driver.get(target_url)

        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            current_url = self.driver.current_url
            logger.debug(f"Opal current URL after navigation: {current_url}")

            if "signin" not in current_url and "accounts.google.com" not in current_url:
                logger.info("✅ Opal authenticated via persistent session")
                self._is_authenticated = True
                return True

            logger.warning("❌ Opal authentication required - need manual login")
            if not self.config.headless:
                logger.info("Opal browser will stay open for manual authentication")
            self._is_authenticated = False
            return False

        except TimeoutException:
            raise AuthenticationError("Page load timed out during Opal authentication")

    async def list_opals(self) -> List[Dict[str, str]]:
        """List available opals"""
        if not self.driver or not self._is_authenticated:
            raise OpalError("Opal not authenticated or browser not ready")

        return await asyncio.get_event_loop().run_in_executor(
            None, self._list_opals_sync
        )

    def _list_opals_sync(self) -> List[Dict[str, str]]:
        """Synchronous list opals"""
        if self.driver is None:
            raise RuntimeError("Opal browser driver not initialized")

        target_url = self.config.opal.list_url or self.config.opal.base_url
        self.driver.get(target_url)

        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, self.config.opal.list_selector)
                )
            )
        except TimeoutException:
            logger.warning("No opal list items found within timeout")
            return []

        items = self.driver.find_elements(By.CSS_SELECTOR, self.config.opal.list_selector)
        results: List[Dict[str, str]] = []

        for item in items:
            title = self._safe_find_text(item, self.config.opal.title_selector)
            status = self._safe_find_text(item, self.config.opal.status_selector)
            href = self._safe_find_attribute(item, "a", "href")

            payload = {
                "title": title or "",
                "status": status or "",
                "url": href or "",
            }
            results.append(payload)

        return results

    async def process_opal(self, opal_id: str) -> Dict[str, str]:
        """Trigger processing for an opal"""
        if not self.driver or not self._is_authenticated:
            raise OpalError("Opal not authenticated or browser not ready")

        return await asyncio.get_event_loop().run_in_executor(
            None, self._process_opal_sync, opal_id
        )

    def _process_opal_sync(self, opal_id: str) -> Dict[str, str]:
        """Synchronous processing trigger"""
        if self.driver is None:
            raise RuntimeError("Opal browser driver not initialized")

        target_url = self._resolve_opal_url(opal_id)
        self.driver.get(target_url)

        try:
            button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, self.config.opal.process_button_selector)
                )
            )
            button.click()
        except TimeoutException as exc:
            raise OpalError("Process button not found for Opal") from exc

        return {"status": "started", "opal_id": opal_id, "url": target_url}

    async def get_opal_result(self, opal_id: str) -> str:
        """Get the latest result for an opal"""
        if not self.driver or not self._is_authenticated:
            raise OpalError("Opal not authenticated or browser not ready")

        return await asyncio.get_event_loop().run_in_executor(
            None, self._get_opal_result_sync, opal_id
        )

    def _get_opal_result_sync(self, opal_id: str) -> str:
        """Synchronous opal result retrieval"""
        if self.driver is None:
            raise RuntimeError("Opal browser driver not initialized")

        target_url = self._resolve_opal_url(opal_id)
        self.driver.get(target_url)

        try:
            result_element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, self.config.opal.result_selector)
                )
            )
        except TimeoutException as exc:
            raise OpalError("Opal result element not found") from exc

        return result_element.text.strip()

    async def list_opal_actions(self, opal_id: str) -> List[str]:
        """List available actions for an opal"""
        if not self.driver or not self._is_authenticated:
            raise OpalError("Opal not authenticated or browser not ready")

        return await asyncio.get_event_loop().run_in_executor(
            None, self._list_opal_actions_sync, opal_id
        )

    def _list_opal_actions_sync(self, opal_id: str) -> List[str]:
        """Synchronous listing of opal actions"""
        if self.driver is None:
            raise RuntimeError("Opal browser driver not initialized")

        target_url = self._resolve_opal_url(opal_id)
        self.driver.get(target_url)

        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        actions = self.driver.find_elements(
            By.CSS_SELECTOR, self.config.opal.action_selector
        )
        results: List[str] = []

        for action in actions:
            label = action.get_attribute("data-action") or action.text
            label = (label or "").strip()
            if label:
                results.append(label)

        return results

    async def close(self) -> None:
        """Close browser session"""
        if self.driver:
            await asyncio.get_event_loop().run_in_executor(None, self.driver.quit)
            self.driver = None
            self._is_authenticated = False

    def _resolve_opal_url(self, opal_id: str) -> str:
        """Resolve opal identifier into a navigable URL"""
        if opal_id.startswith("http://") or opal_id.startswith("https://"):
            return opal_id
        if self.config.opal.detail_url_template:
            return self.config.opal.detail_url_template.format(opal_id=opal_id)
        return f"{self.config.opal.base_url.rstrip('/')}/opal/{opal_id}"

    @staticmethod
    def _safe_find_text(element: webdriver.remote.webelement.WebElement, selector: str) -> str:
        """Safely extract text from child elements"""
        try:
            found = element.find_element(By.CSS_SELECTOR, selector)
            return found.text.strip()
        except Exception:
            return ""

    @staticmethod
    def _safe_find_attribute(
        element: webdriver.remote.webelement.WebElement,
        selector: str,
        attribute: str,
    ) -> str:
        """Safely extract attribute from child elements"""
        try:
            found = element.find_element(By.CSS_SELECTOR, selector)
            return (found.get_attribute(attribute) or "").strip()
        except Exception:
            return ""
