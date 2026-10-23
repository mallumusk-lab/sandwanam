"""docs/INTEGRITY.md must list every test: each backend test method under its own test file and
class, and each frontend test(…) under its own test file. A new test is not done until it has a line there."""
import re
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
BACKEND = TESTS.parent
REPO = BACKEND.parent
DOC = REPO / "docs" / "INTEGRITY.md"
FRONTEND_TESTS = REPO / "Frontend" / "tests"

# test("name", …) / it('name', …) / test(`name ${x}`, …): the name is the first argument's literal text.
FRONTEND_TEST = re.compile(r"""\b(?:test|it)\(\s*("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`[^`]*`)""")
HEADING = re.compile(r"^(#{3,4}) `([^`]+)`")
LISTED = re.compile(r"^- `([^`]+)`")


def listed() -> tuple[set[tuple[str, str, str]], set[tuple[str, str]]]:
    """(file, class, method) for backend lines and (file, name) for frontend lines in the doc."""
    backend, frontend = set(), set()
    file = cls = None
    for line in DOC.read_text(encoding="utf-8").splitlines():
        heading = HEADING.match(line)
        if heading:
            if heading.group(1) == "###":
                file, cls = heading.group(2), None
            else:
                cls = heading.group(2)
            continue
        item = LISTED.match(line)
        if item and file:
            if cls:
                backend.add((file, cls, item.group(1)))
            else:
                frontend.add((file, item.group(1)))
    return backend, frontend


def backend_tests() -> set[tuple[str, str, str]]:
    found = set()
    pending = [unittest.defaultTestLoader.discover(str(TESTS), top_level_dir=str(BACKEND))]
    while pending:
        suite = pending.pop()
        for test in suite:
            if isinstance(test, unittest.TestSuite):
                pending.append(test)
                continue
            module, cls, method = test.id().rsplit(".", 2)
            if module.startswith("unittest."):  # a module that failed to import reports its own error
                continue
            found.add((module.rsplit(".", 1)[-1] + ".py", cls, method))
    return found


def frontend_tests() -> set[tuple[str, str]]:
    found = set()
    for path in sorted(FRONTEND_TESTS.glob("*.test.js*")):
        if path.suffix not in (".js", ".jsx"):
            continue
        for match in FRONTEND_TEST.finditer(path.read_text(encoding="utf-8")):
            found.add((path.name, match.group(1)[1:-1]))
    return found


class IntegrityDoc(unittest.TestCase):
    def test_every_backend_test_is_listed(self):
        tests = backend_tests()
        self.assertGreater(len(tests), 100, "test discovery found too few backend tests")
        self.assertIn(("test_integrity_doc.py", "IntegrityDoc", "test_every_backend_test_is_listed"), tests)
        missing = sorted(tests - listed()[0])
        self.assertEqual(missing, [], f"add these backend tests to {DOC.name} under their file and class")

    def test_every_frontend_test_is_listed(self):
        tests = frontend_tests()
        self.assertGreater(len(tests), 50, "the frontend test pattern found too few tests")
        self.assertIn(("ui.test.jsx", "pagination, stepper and states"), tests)
        self.assertIn(("contrast.test.js", "${name} theme text contrast is at least 4.5:1"), tests)
        missing = sorted(tests - listed()[1])
        self.assertEqual(missing, [], f"add these frontend tests to {DOC.name} under their file")


if __name__ == "__main__":
    unittest.main()
