
import time
import re
import json

# Current regex in the code
CURRENT_PATTERN_STR = r'"((?:\\.|[^"\\])*)"\s*=>\s*"((?:\\.|[^"\\])*)"'

def current_parse_tags(tags):
    if not tags or tags == "nan":
        return {}
    if len(tags) > 100000:
        return {}
    try:
        return json.loads(tags)
    except Exception:
        pass
    d = {}
    try:
        # This is what's currently in the code (compiling every time)
        pattern = CURRENT_PATTERN_STR
        for match in re.finditer(pattern, tags):
            key = match.group(1).replace('\\"', '"').replace('\\\\', '\\')
            value = match.group(2).replace('\\"', '"').replace('\\\\', '\\')
            d[key] = value
        return d
    except Exception:
        return {}

# Optimized version with pre-compiled regex
HSTORE_PATTERN = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"\s*=>\s*"([^"\\]*(?:\\.[^"\\]*)*)"')

def optimized_parse_tags(tags):
    if not tags or tags == "nan":
        return {}
    if len(tags) > 100000:
        return {}
    try:
        return json.loads(tags)
    except Exception:
        pass
    d = {}
    try:
        for match in HSTORE_PATTERN.finditer(tags):
            key = match.group(1).replace('\\"', '"').replace('\\\\', '\\')
            value = match.group(2).replace('\\"', '"').replace('\\\\', '\\')
            d[key] = value
        return d
    except Exception:
        return {}

# Generate some test data
hstore_str = '"highway"=>"primary", "name"=>"Main Street", "surface"=>"asphalt", "lanes"=>"2", "oneway"=>"yes", "maxspeed"=>"50"'
test_data = [hstore_str] * 100000

def benchmark(func, data):
    start_time = time.perf_counter()
    for item in data:
        func(item)
    end_time = time.perf_counter()
    return end_time - start_time

if __name__ == "__main__":
    # Warm up re cache? re.finditer caches compiled regexes internally,
    # but there's still a lookup overhead and potential cache eviction.
    # The task rationale says "avoids repeated compilation overhead during .apply()".

    print("Benchmarking current_parse_tags (repeated compilation)...")
    current_time = benchmark(current_parse_tags, test_data)
    print(f"Current time: {current_time:.4f} seconds")

    print("Benchmarking optimized_parse_tags (pre-compiled)...")
    optimized_time = benchmark(optimized_parse_tags, test_data)
    print(f"Optimized time: {optimized_time:.4f} seconds")

    improvement = (current_time - optimized_time) / current_time * 100
    print(f"Improvement: {improvement:.2f}%")
