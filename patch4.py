with open("tests/security/test_admin_rate_limit.py", "r") as f:
    content = f.read()

# Replace manage_database with something that returns an async_sessionmaker-like context manager
# We can just use the engine directly via async_sessionmaker
fixture_str = """
@pytest.fixture
def session_factory(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def admin_app(test_settings, session_factory):
    return create_admin_app(
        settings=test_settings, session_factory=session_factory
    )
"""

content = content.replace("@pytest.fixture\ndef admin_app(test_settings, manage_database):\n    return create_admin_app(\n        settings=test_settings, session_factory=manage_database\n    )", fixture_str)

with open("tests/security/test_admin_rate_limit.py", "w") as f:
    f.write(content)
