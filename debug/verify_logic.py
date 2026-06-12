
import re
import json

# HSTORE-like format regex: "key"=>"value", handles backslash-escaped quotes
# Uses an "unrolled loop" pattern for performance and ReDoS protection
HSTORE_PATTERN = re.compile(
    r'"([^"\\]*(?:\\.[^"\\]*)*)"\s*=>\s*"([^"\\]*(?:\\.[^"\\]*)*)"'
)

def parse_tags(tags):
    """Safe parser for OSM tags in JSON or HSTORE-like format."""
    if not tags or tags == "nan":
        return {}

    # Limit string length to prevent resource exhaustion
    if len(tags) > 100000:
        return {}

    # 1. Try JSON format
    try:
        return json.loads(tags)
    except (json.JSONDecodeError, RecursionError):
        pass

    # 2. Try HSTORE-like format: "key"=>"value", "key2"=>"value2"
    d = {}
    try:
        for match in HSTORE_PATTERN.finditer(tags):
            key = match.group(1).replace('\\"', '"').replace('\\\\', '\\')
            value = match.group(2).replace('\\"', '"').replace('\\\\', '\\')
            d[key] = value
        return d
    except Exception:
        return {}

def test_parse_tags():
    # Test JSON
    assert parse_tags('{"highway": "primary"}') == {"highway": "primary"}

    # Test HSTORE
    hstore = '"highway"=>"primary", "name"=>"Main Street"'
    assert parse_tags(hstore) == {"highway": "primary", "name": "Main Street"}

    # Test HSTORE with escapes
    hstore_escaped = r'"name"=>"The \"Real\" Deal", "path"=>"C:\\Windows"'
    expected = {"name": 'The "Real" Deal', "path": 'C:\\Windows'}
    assert parse_tags(hstore_escaped) == expected

    # Test empty/nan
    assert parse_tags("") == {}
    assert parse_tags("nan") == {}

    print("All tests passed!")

if __name__ == "__main__":
    test_parse_tags()
