import tempfile
import os
from textwrap import dedent

from agent_tools.read_file import extract_top_level_imports


class TestExtractTopLevelImports:
    """Test suite for extract_top_level_imports function."""

    def create_temp_file(self, content: str) -> str:
        """Helper to create temporary file with given content."""
        fd, path = tempfile.mkstemp(suffix=".py")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(dedent(content).strip())
        except:
            os.close(fd)
            raise
        return path

    def cleanup_temp_file(self, path: str):
        """Helper to cleanup temporary file."""
        try:
            os.unlink(path)
        except OSError:
            pass

    # File Structure Tests
    def test_empty_file_returns_empty_string_and_zero(self):
        """Test that empty file returns empty string and zero."""
        path = self.create_temp_file("")
        try:
            result, line_num = extract_top_level_imports(path)
            assert result == ""
            assert line_num == 0
        finally:
            self.cleanup_temp_file(path)

    def test_file_with_no_imports_returns_empty_string_and_zero(self):
        """Test file with code but no imports."""
        content = """
        def hello():
            print("Hello, world!")

        x = 42
        """
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert result == ""
            assert line_num == 0
        finally:
            self.cleanup_temp_file(path)

    def test_file_with_only_docstring_no_imports(self):
        """Test file with only docstring and no imports."""
        content = '''
        """
        This is a module docstring.
        It spans multiple lines.
        """

        def some_function():
            pass
        '''
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert result == ""
            assert line_num == 0
        finally:
            self.cleanup_temp_file(path)

    # Import Statement Formats
    def test_single_line_import(self):
        """Test single line import statement."""
        content = """
        import os

        def main():
            pass
        """
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "import os" in result
            assert line_num == 2
            assert "1: import os" in result
        finally:
            self.cleanup_temp_file(path)

    def test_multiple_single_line_imports(self):
        """Test multiple single line imports."""
        content = """
        import os
        import sys
        import json

        def main():
            pass
        """
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "import os" in result
            assert "import sys" in result
            assert "import json" in result
            assert line_num == 4
        finally:
            self.cleanup_temp_file(path)

    def test_multiline_parenthesized_import(self):
        """Test multiline import with parentheses."""
        content = """
        from collections import (
            defaultdict,
            namedtuple,
            OrderedDict
        )

        def main():
            pass
        """
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "from collections import" in result
            assert "defaultdict" in result
            assert "namedtuple" in result
            assert "OrderedDict" in result
            assert line_num == 6
        finally:
            self.cleanup_temp_file(path)

    def test_multiline_backslash_continued_import(self):
        """Test multiline import with backslash continuation."""
        content = """
        from some.very.long.module.name import \\
            function_one, function_two, \\
            function_three

        def main():
            pass
        """
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "from some.very.long.module.name import" in result
            assert "function_one" in result
            assert line_num == 4
        finally:
            self.cleanup_temp_file(path)

    def test_inline_comment_on_import_line(self):
        """Test import with inline comment."""
        content = """
        import os  # Operating system interface
        import sys  # System-specific parameters

        def main():
            pass
        """
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "import os  # Operating system interface" in result
            assert "import sys  # System-specific parameters" in result
            assert line_num == 3
        finally:
            self.cleanup_temp_file(path)

    # Import Types
    def test_regular_import_statement(self):
        """Test regular import statement."""
        content = """
        import math
        import random

        x = 5
        """
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "import math" in result
            assert "import random" in result
            assert line_num == 3
        finally:
            self.cleanup_temp_file(path)

    def test_from_import_statement(self):
        """Test from import statement."""
        content = """
        from datetime import datetime
        from pathlib import Path

        today = datetime.now()
        """
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "from datetime import datetime" in result
            assert "from pathlib import Path" in result
            assert line_num == 3
        finally:
            self.cleanup_temp_file(path)

    def test_from_relative_import(self):
        """Test relative import statement."""
        content = """
        from .module import function
        from ..package import Class

        def main():
            pass
        """
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "from .module import function" in result
            assert "from ..package import Class" in result
            assert line_num == 3
        finally:
            self.cleanup_temp_file(path)

    def test_from_import_with_alias(self):
        """Test from import with alias."""
        content = """
        from datetime import datetime as dt
        from collections import defaultdict as dd

        now = dt.now()
        """
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "from datetime import datetime as dt" in result
            assert "from collections import defaultdict as dd" in result
            assert line_num == 3
        finally:
            self.cleanup_temp_file(path)

    def test_import_with_alias(self):
        """Test regular import with alias."""
        content = """
        import numpy as np
        import pandas as pd

        arr = np.array([1, 2, 3])
        """
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "import numpy as np" in result
            assert "import pandas as pd" in result
            assert line_num == 3
        finally:
            self.cleanup_temp_file(path)

    # Ignored Contexts
    def test_import_inside_function_ignored(self):
        """Test that imports inside functions are ignored."""
        content = """
        import os

        def some_function():
            import sys  # This should be ignored
            from datetime import datetime  # This too
            return sys.version

        x = 5
        """
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "import os" in result
            assert "import sys" not in result
            assert "from datetime import datetime" not in result
            assert line_num == 2
        finally:
            self.cleanup_temp_file(path)

    def test_import_inside_class_ignored(self):
        """Test that imports inside classes are ignored."""
        content = """
        from pathlib import Path

        class MyClass:
            import json  # This should be ignored

            def method(self):
                import re  # This should also be ignored
                return re.match(r'test', 'test')
        """
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "from pathlib import Path" in result
            assert "import json" not in result
            assert "import re" not in result
            assert line_num == 2
        finally:
            self.cleanup_temp_file(path)

    def test_import_inside_if_main_ignored(self):
        """Test that imports inside if __name__ == '__main__' are ignored."""
        content = """
        import os
        from sys import argv

        def main():
            print("Hello")

        if __name__ == '__main__':
            import argparse  # This should be ignored
            from datetime import datetime  # This too
            main()
        """
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "import os" in result
            assert "from sys import argv" in result
            assert "import argparse" not in result
            assert "from datetime import datetime" not in result
            assert line_num == 3
        finally:
            self.cleanup_temp_file(path)

    def test_function_definition_immediately_after_top_level_imports(self):
        """Test function definition immediately after imports."""
        content = """
        import os
        import sys

        def main():
            pass
        """
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "import os" in result
            assert "import sys" in result
            assert "def main():" not in result  # Should not include function
            assert line_num == 3
        finally:
            self.cleanup_temp_file(path)

    # Line-Number Tracking
    def test_last_import_on_first_line(self):
        """Test when last import is on the first line."""
        content = """import os"""
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "import os" in result
            assert line_num == 2
            assert "1: import os" in result
        finally:
            self.cleanup_temp_file(path)

    def test_last_import_on_last_line(self):
        """Test when last import is on the last line of file."""
        content = """
        def some_function():
            pass

        import os"""
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "import os" in result
            assert line_num == 5
        finally:
            self.cleanup_temp_file(path)

    def test_blank_lines_between_imports_preserved(self):
        """Test that blank lines between imports are preserved."""
        content = """
        import os

        import sys


        import json

        def main():
            pass
        """
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "import os" in result
            assert "import sys" in result
            assert "import json" in result
            # Check that blank lines are preserved in the output
            lines = result.split("\n")
            # Should have blank lines between imports
            assert any(
                line.strip() == ""
                or ":" in line
                and line.split(":", 1)[1].strip() == ""
                for line in lines
            )
            assert line_num == 7
        finally:
            self.cleanup_temp_file(path)

    # Additional Edge Cases
    def test_mixed_import_types_with_comments(self):
        """Test mixed import types with various comments."""
        content = """
        # Module imports
        import os
        import sys  # System module

        # Third-party imports
        from collections import defaultdict
        from datetime import (
            datetime,
            timedelta  # For time calculations
        )

        # Local imports
        from .local_module import local_function

        def main():
            pass
        """
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "import os" in result
            assert "import sys  # System module" in result
            assert "from collections import defaultdict" in result
            assert "datetime" in result
            assert "timedelta  # For time calculations" in result
            assert "from .local_module import local_function" in result
            assert "def main" not in result
            assert line_num == 14
        finally:
            self.cleanup_temp_file(path)

    def test_imports_with_docstring_and_module_variables(self):
        """Test imports mixed with docstring and module-level variables."""
        content = '''
        """Module docstring."""

        import os

        __version__ = "1.0.0"
        __author__ = "Test Author"

        from sys import argv

        DEBUG = True

        def main():
            pass
        '''
        path = self.create_temp_file(content)
        try:
            result, line_num = extract_top_level_imports(path)
            assert "import os" in result
            assert "from sys import argv" in result
            # Should not include docstring or variables
            assert "DEBUG" not in result
            assert line_num == 9
        finally:
            self.cleanup_temp_file(path)
