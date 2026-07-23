"""Tool script for generating demo input data for OrangeHRM portal."""

import asyncio
import json
import logging
from pathlib import Path

import faker
from dotenv import load_dotenv

from portals.saucedemo.runner import SauceDemoRunnerInputItem

logger = logging.getLogger(__name__)

load_dotenv()


OUTPUT_FILENAME = "input/saucedemo.json"


async def run() -> None:
    """Generate input data and store it to the saudecemo.json."""

    logging.basicConfig(level=logging.INFO)
    data: list[SauceDemoRunnerInputItem] = []

    usernames = [
        "standard_user",
        "locked_out_user",
        "problem_user",
        "performance_glitch_user",
        "error_user",
        "visual_user",
    ]

    fake = faker.Faker()

    data.extend(
        [
            SauceDemoRunnerInputItem(
                id=str(index),
                username=username,
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                postal_code=fake.postalcode(),
            )
            for index, username in enumerate(usernames)
        ],
    )

    logger.info(f"Generated {len(data)} elements")

    with Path(OUTPUT_FILENAME).open("w") as output_file:  # noqa: ASYNC230
        json.dump([element.model_dump() for element in data], output_file, indent=2)

    logger.info(f"Demo input data written to {OUTPUT_FILENAME}")


if __name__ == "__main__":
    asyncio.run(run())
