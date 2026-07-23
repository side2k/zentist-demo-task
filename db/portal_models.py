"""Database models for portal output items."""

import enum
import importlib
from decimal import Decimal
from types import UnionType
from typing import get_args, get_origin

import sqlalchemy
from pydantic import BaseModel

from db.models import Base


class PortalModelError(Exception):  # noqa: D101
    pass


def _sqlalchemy_type(field_type: type) -> tuple[sqlalchemy.types.TypeEngine, bool]:
    # handle enums
    try:
        if issubclass(field_type, enum.StrEnum):
            return sqlalchemy.String(), False
    except TypeError:
        pass

    origin = get_origin(field_type)  # list[...], Optional[...], etc.
    if origin is list:
        return sqlalchemy.Text(), False  # JSON

    # process nullable types, e.g. str | None
    if origin is UnionType:
        try:
            main_field_type, optional = get_args(field_type)
            if optional is type(None):
                main_field, _ = _sqlalchemy_type(main_field_type)
                return main_field, True

            raise PortalModelError(  # noqa: TRY301
                f"Optional type is {optional} (only NoneType is supported)",
            )

        except Exception as exc:
            raise PortalModelError(
                "Portal models do not support union types "
                "more complex than <type>|None ",
            ) from exc

    column_type = {
        str: sqlalchemy.String,
        int: sqlalchemy.Integer,
        Decimal: sqlalchemy.Numeric,
        bytes: sqlalchemy.LargeBinary,
    }.get(field_type)

    if column_type:
        return column_type(), False

    raise PortalModelError(f"unknown type: {field_type}")


def pydantic_model_to_sqlalchemy_table(
    model_cls: type[BaseModel],
    table_name: str,
    metadata: sqlalchemy.MetaData,
) -> sqlalchemy.Table:
    """Creates an SQLAlchemy table from the Pydantic model.

    Used to dynamically create DB tables for portal runner's output data
    """
    columns = [
        sqlalchemy.Column(
            "id",
            sqlalchemy.Integer(),
            primary_key=True,
            autoincrement=True,
        ),
    ]
    for field_name, field_info in model_cls.model_fields.items():
        if field_info.annotation is None:
            raise PortalModelError(f"Unknown field info for field {field_name}")
        field_type, is_nullable = _sqlalchemy_type(field_info.annotation)
        column_args = [field_name, field_type]

        # run_id is a special column, we need it to relate to the portal_runs.id
        if field_name == "run_id":
            is_nullable = False
            column_args.append(sqlalchemy.ForeignKey("portal_runs.id"))

        columns.append(
            sqlalchemy.Column(*column_args, nullable=is_nullable),
        )
    return sqlalchemy.Table(table_name, metadata, *columns)


# We use portal.models.Base here becase we need to link run_id
portal_output_metadata = Base.metadata


def portal_output_table_name(portal_key: str) -> str:
    """Return table name for portal output data."""
    return f"{portal_key}_output"


# Add a portal module name here makes it visible to Alembic, so
# `alembic revision --autogenerate` will be able to generate a migration
# that adds database table for that portal's output items
installed_portals = [
    "orange_hrm",
]
for portal_key in installed_portals:
    portal_module = importlib.import_module(f"portals.{portal_key}")
    portal_output_item_model = portal_module.OutputItem
    pydantic_model_to_sqlalchemy_table(
        portal_output_item_model,
        portal_output_table_name(portal_key),
        portal_output_metadata,
    )
