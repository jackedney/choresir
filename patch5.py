with open("tests/security/test_admin_rate_limit.py", "r") as f:
    content = f.read()

# Replace the fixture definitions completely
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

import re
content = re.sub(r'@pytest\.fixture\ndef admin_app\(test_settings, manage_database\):.*?return create_admin_app\(.*?settings=test_settings, session_factory=manage_database.*?\)', fixture_str.strip(), content, flags=re.DOTALL)

with open("tests/security/test_admin_rate_limit.py", "w") as f:
    f.write(content)
