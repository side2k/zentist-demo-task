"""Portal runner implementation for SauceDemo portal."""

from __future__ import annotations

import base64
import random
import re
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.async_api import expect
from pydantic import BaseModel

from portals import (
    BaseItemProcessingResult,
    BasePortalRunner,
    BasePortalRunnerConfig,
    BasePortalRunnerInputItem,
)
from portals.errors import UnrecoverablePortalError

if TYPE_CHECKING:
    from playwright.async_api import Browser, ConsoleMessage, Page


class SauceDemoPortalConfig(BasePortalRunnerConfig):  # noqa: D101
    headless: bool = True


class SauceDemoRunnerInputItem(BasePortalRunnerInputItem):  # noqa: D101
    username: str
    first_name: str
    last_name: str
    postal_code: str


class InventoryItem(BaseModel):
    """A good in the shop."""

    title: str
    price: Decimal


class OrderData(BaseModel):  # noqa: D101
    total: Decimal
    tax: Decimal
    subtotal: Decimal
    shipping_info: str
    payment_info: str


class SauceDemoItemProcessingResult(BaseItemProcessingResult):  # noqa: D101
    order_items: list[InventoryItem]
    order_subtotal: Decimal
    order_total: Decimal
    order_tax: Decimal
    order_shipping_info: str
    order_payment_info: str
    receipt_filename: str
    receipt_body: str  # base64-encoded

    @classmethod
    def construct(  # noqa: D102
        cls,
        items: list[InventoryItem],
        order: OrderData,
        receipt_filename: str,
        receipt_body: bytes,
    ) -> SauceDemoItemProcessingResult:
        return SauceDemoItemProcessingResult(
            order_items=items,
            order_subtotal=order.subtotal,
            order_total=order.total,
            order_tax=order.tax,
            order_shipping_info=order.shipping_info,
            order_payment_info=order.payment_info,
            receipt_filename=receipt_filename,
            receipt_body=base64.b64encode(receipt_body).decode("ascii"),
        )

    def __str__(self) -> str:
        """Nice representation for logs."""
        return f"Order[{len(self.order_items)} items, ${self.order_total}]"


class SauceDemoPortalRunner(
    BasePortalRunner[
        SauceDemoPortalConfig,
        SauceDemoRunnerInputItem,
        SauceDemoItemProcessingResult,
    ],
):
    """Portal runner for SauceDemo portal.

    https://www.saucedemo.com/
    """

    base_url = "https://www.saucedemo.com/"

    Config = SauceDemoPortalConfig
    InputItem = SauceDemoRunnerInputItem
    OutputItem = SauceDemoItemProcessingResult

    async def before_run(self) -> None:  # noqa: D102
        # Import is here to avoid playwright dependency
        # propagated for the rest of the code
        from playwright.async_api import async_playwright  # noqa: PLC0415

        await super().before_run()
        self._playwright_context = async_playwright()
        self._playwright = await self._playwright_context.__aenter__()

    async def after_run(self) -> None:  # noqa: D102
        await super().after_run()
        await self._playwright_context.__aexit__()

    async def process_batch_item(
        self,
        item: SauceDemoRunnerInputItem,
    ) -> SauceDemoItemProcessingResult:
        """Perform portal actions, using item.username.

        - Log in, using password displayed on the login page.
        """

        self.logger.info(f"Processing {item=}")
        browser = await self._playwright.chromium.launch(headless=self.config.headless)

        try:
            return await self.perform_user_actions(item, browser)
        finally:
            await browser.close()

    async def perform_user_actions(  # noqa: D102
        self,
        item: SauceDemoRunnerInputItem,
        browser: Browser,
    ) -> SauceDemoItemProcessingResult:
        page = await browser.new_page()
        self.errors = []

        async def on_console_message(msg: ConsoleMessage) -> None:
            if msg.type == "error":
                self.errors.append(msg)
                self.logger.warning(f"Browser console error: {msg.text}")
            elif msg.type == "warning":
                self.logger.warning(f"Browser console warning: {msg.text}")

        page.on("console", on_console_message)

        await page.goto(self.base_url)

        # login
        login_error = await self._login(page, item)
        if login_error:
            raise UnrecoverablePortalError(f"Login error: {login_error}")

        self.logger.debug("Logged in")

        # add items to cart
        items_added = await self._add_items_to_cart(page)

        # check items in cart
        await page.locator('a[data-test="shopping-cart-link"]').click()
        await page.wait_for_url("**/cart.html")

        await self._check_cart(page, items_added)

        # do checkout
        await page.get_by_role("button", name="Checkout").click()
        await page.wait_for_url("**/checkout-step-one.html")

        await self._checkout(page, item)

        # order confirmation
        await page.get_by_role("button", name="Continue").click()
        await page.wait_for_url("**/checkout-step-two.html")

        order_data = await self._confirm_order(page, items_added)

        # download order receipt in PDF
        await page.get_by_role("button", name="Finish").click()
        await page.wait_for_url("**/checkout-complete.html")

        receipt_name, receipt_body = await self._download_receipt(page)
        self.logger.debug(
            f"Downloaded PDF receipt {receipt_name} ({len(receipt_body) // 1024} kb)",
        )

        return SauceDemoItemProcessingResult.construct(
            items_added,
            order_data,
            f"{receipt_name}.pdf",
            receipt_body,
        )

    async def _get_password(self, home_page: Page) -> str:
        """Simple helper to fetch password from the home page."""
        password_raw = await home_page.locator(
            '[data-test="login-password"]',
        ).inner_text()
        return password_raw.split("\n")[-1].strip()

    async def _login(
        self,
        home_page: Page,
        item: SauceDemoRunnerInputItem,
    ) -> str | None:
        url_before = home_page.url
        password = await self._get_password(home_page)
        await home_page.locator('input[data-test="username"]').fill(item.username)
        await home_page.locator('input[data-test="password"]').fill(password)
        await home_page.locator('input[data-test="login-button"]').click()
        await home_page.wait_for_load_state("networkidle")

        if home_page.url == url_before:
            return await home_page.locator('h3[data-test="error"]').inner_text()

        return None

    async def _add_items_to_cart(self, inventory_page: Page) -> list[InventoryItem]:
        """On inventory page adds 3 random item to the cart.

        Returns list of added item title.
        """

        await inventory_page.wait_for_load_state("domcontentloaded")

        inventory_items = await inventory_page.locator(
            'div.inventory_item[data-test="inventory-item"]',
        ).all()

        items_added = []

        for item_container in random.sample(inventory_items, 3):
            item_title = await item_container.locator(
                '[data-test="inventory-item-name"]',
            ).inner_text()
            item_price_raw = await item_container.locator(
                '[data-test="inventory-item-price"]',
            ).inner_text()

            self.logger.debug(
                f"Adding inventory item [{item_title}, {item_price_raw}] to cart",
            )
            item = InventoryItem(
                title=item_title,
                price=Decimal(item_price_raw.lstrip("$")),
            )
            await item_container.get_by_role(
                "button",
                name="Add to cart",
                exact=True,
            ).click()

            await inventory_page.wait_for_load_state("domcontentloaded")

            if await item_container.get_by_role("button", name="Remove").count() != 1:
                raise UnrecoverablePortalError(
                    f"Add to cart button for item [{item_title}] didn't work properly",
                )

            await expect(
                inventory_page.locator(
                    'span[data-test="shopping-cart-badge"]',
                ).first,
            ).to_have_text(str(len(items_added) + 1))
            items_added.append(item)
        return items_added

    async def _check_cart(
        self,
        cart_page: Page,
        expected_items: list[InventoryItem],
    ) -> None:
        """Checks items in cart."""

        await cart_page.wait_for_load_state("domcontentloaded")

        cart_size = await cart_page.locator(
            'div.cart_item[data-test="inventory-item"]',
        ).count()
        if cart_size != len(expected_items):
            raise UnrecoverablePortalError(
                f"Unexpected number of items in cart: {cart_size}",
            )

        for item_container in await cart_page.locator(
            'div.cart_item[data-test="inventory-item"]',
        ).all():
            item_title = await item_container.locator(
                '[data-test="inventory-item-name"]',
            ).inner_text()
            item_price_raw = await item_container.locator(
                '[data-test="inventory-item-price"]',
            ).inner_text()
            item = InventoryItem(
                title=item_title,
                price=Decimal(item_price_raw.lstrip("$")),
            )
            if item not in expected_items:
                raise UnrecoverablePortalError(f"unexpected item in cart: {item}")

        self.logger.debug("Items in cart match added items")

    async def _checkout(
        self,
        checkout_page: Page,
        input_item: SauceDemoRunnerInputItem,
    ) -> None:
        """Do a checkout."""

        await checkout_page.wait_for_load_state("domcontentloaded")

        await checkout_page.locator('input[data-test="firstName"]').fill(
            input_item.first_name,
        )
        await checkout_page.locator('input[data-test="lastName"]').fill(
            input_item.last_name,
        )
        await checkout_page.locator('input[data-test="postalCode"]').fill(
            input_item.postal_code,
        )

    async def _confirm_order(
        self,
        confirm_page: Page,
        expected_items: list[InventoryItem],
    ) -> OrderData:

        await confirm_page.wait_for_load_state("domcontentloaded")

        payment_info = await confirm_page.locator(
            'div.summary_info [data-test="payment-info-value"]',
        ).inner_text()
        shipping_info = await confirm_page.locator(
            'div.summary_info [data-test="shipping-info-value"]',
        ).inner_text()
        subtotal_raw = await confirm_page.locator(
            'div.summary_info [data-test="subtotal-label"]',
        ).inner_text()

        tax_raw = await confirm_page.locator(
            'div.summary_info [data-test="tax-label"]',
        ).inner_text()
        total_raw = await confirm_page.locator(
            'div.summary_info [data-test="total-label"]',
        ).inner_text()

        self.logger.debug(
            f"{payment_info=}, {shipping_info=}, {subtotal_raw=}, "
            f"{tax_raw=}, {total_raw=}",
        )

        subtotal = Decimal(re.sub(r"^.*: +\$ *", "", subtotal_raw))
        tax = Decimal(re.sub(r"^.*: +\$ *", "", tax_raw))
        total = Decimal(re.sub(r"^.*: +\$ *", "", total_raw))

        expected_sum = sum([item.price for item in expected_items])
        if subtotal != expected_sum:
            raise UnrecoverablePortalError(
                f"Order subtotal of ${subtotal} doesn't match "
                f"expected sum of ${expected_sum}",
            )

        return OrderData(
            total=total,
            subtotal=subtotal,
            tax=tax,
            shipping_info=shipping_info,
            payment_info=payment_info,
        )

    async def _download_receipt(self, success_page: Page) -> tuple[str, bytes]:
        await success_page.wait_for_load_state("domcontentloaded")
        if await success_page.get_by_text("Thank you for your order!").count() != 1:
            raise UnrecoverablePortalError("Unexpected order success page")

        async with success_page.expect_download() as download_info:
            await success_page.get_by_role("button", name="Generate PDF order").click()

        download = await download_info.value

        try:
            # This is a blocking IO operation! For production, better use another way,
            # for example asyncio.to_thread()
            path = Path(await download.path())
            return path.name, path.read_bytes()  # noqa: ASYNC240
        finally:
            await download.delete()
