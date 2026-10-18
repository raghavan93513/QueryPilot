from app.agents import extract_sql
from app.mock_agent import generate_mock_sql


def test_fenced_sql_extraction():
    assert extract_sql('Here is SQL:\n```sql\nSELECT 1;\n```') == 'SELECT 1;'


def test_plain_sql_extraction():
    assert extract_sql('SQL: SELECT COUNT(*) FROM customers') == 'SELECT COUNT(*) FROM customers'


def test_mock_repair_does_not_hide_failed_first_attempt():
    first = generate_mock_sql('repair customer count', '', '', '')
    second = generate_mock_sql('repair customer count', '', 'nonexistent_column', first)
    assert 'nonexistent_column' in first
    assert 'COUNT(*)' in second
