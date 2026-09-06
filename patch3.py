with open("tests/security/test_admin_rate_limit.py", "r") as f:
    content = f.read()

content = content.replace("@pytest.mark.asyncio", "@pytest.mark.anyio")

with open("tests/security/test_admin_rate_limit.py", "w") as f:
    f.write(content)
