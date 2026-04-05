import pytest

from src.config.schema import NeutrinoSettings
from src.tui.app import NeutrinoApp


@pytest.mark.asyncio
async def test_app_mounts() -> None:
    settings = NeutrinoSettings()
    app = NeutrinoApp(settings)
    async with app.run_test(size=(100, 40)) as pilot:
        assert app.query_one("#prompt-input") is not None
        await pilot.pause()
