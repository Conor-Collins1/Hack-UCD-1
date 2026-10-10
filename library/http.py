"""Shared request parsing and response helpers."""
from fastapi import Body

async def json_body(data: dict = Body(default={})):
    return data


def response(*args, **kwargs):
    return args[0] if args else kwargs
