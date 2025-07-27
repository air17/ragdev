import pytest
from unittest.mock import patch, MagicMock, mock_open
import json

from find_usages.finder import find_usages, UsageRecord


@pytest.fixture
def mock_index_data():
    return [
        {
            "name": "TestClass",
            "fqn": "module.TestClass",
            "file": "test.py",
            "line": 10,
            "column": 6,
        },
        {
            "name": "other_func",
            "fqn": "module.other_func",
            "file": "other.py",
            "line": 5,
            "column": 4,
        },
    ]


@pytest.fixture
def mock_jedi_script():
    script_mock = MagicMock()
    with patch("jedi.Script", return_value=script_mock):
        yield script_mock


@pytest.fixture
def mock_jedi_project():
    with patch("jedi.Project") as mock:
        yield mock


class TestFindUsages:
    @patch("os.path.isfile")
    @patch("builtins.open", new_callable=mock_open)
    def test_find_usages_file_not_found(self, mock_file, mock_isfile):
        # Setup mock for index file not found
        mock_isfile.return_value = False

        # Call the function and verify it raises FileNotFoundError
        with pytest.raises(FileNotFoundError):
            find_usages("root_dir", "TestClass")

    @patch("os.path.isfile")
    @patch("builtins.open")
    def test_find_usages_no_matching_definitions(
        self, mock_open, mock_isfile, mock_index_data
    ):
        # Setup mocks
        mock_isfile.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
            mock_index_data
        )

        # Call the function with a target that doesn't match any definitions
        result = find_usages("root_dir", "NonExistentClass")

        # Verify empty result
        assert result == []

    @patch("os.path.isfile")
    @patch("builtins.open")
    def test_find_usages_by_simple_name(
        self,
        mock_open,
        mock_isfile,
        mock_index_data,
        mock_jedi_script,
        mock_jedi_project,
    ):
        # Setup mocks
        mock_isfile.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
            mock_index_data
        )

        # Setup mock references
        ref1 = MagicMock()
        ref1.module_path = "test.py"
        ref1.line = 10
        ref1.column = 6

        ref2 = MagicMock()
        ref2.module_path = "other.py"
        ref2.line = 15
        ref2.column = 8

        mock_jedi_script.get_references.return_value = [ref1, ref2]

        # Call the function
        result = find_usages("root_dir", "TestClass")

        # Verify jedi script was created and references were fetched
        mock_jedi_project.assert_called_once_with(path="root_dir")
        mock_jedi_script.get_references.assert_called_once_with(
            line=10, column=6, include_builtins=False
        )

        # Verify results
        assert len(result) == 2
        assert result[0] == UsageRecord(
            path="test.py", line=10, column=6, fqn="module.TestClass"
        )
        assert result[1] == UsageRecord(
            path="other.py", line=15, column=8, fqn="module.TestClass"
        )

    @patch("os.path.isfile")
    @patch("builtins.open")
    def test_find_usages_by_fqn(
        self,
        mock_open,
        mock_isfile,
        mock_index_data,
        mock_jedi_script,
        mock_jedi_project,
    ):
        # Setup mocks
        mock_isfile.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
            mock_index_data
        )

        # Setup mock references
        ref = MagicMock()
        ref.module_path = "other.py"
        ref.line = 5
        ref.column = 4

        mock_jedi_script.get_references.return_value = [ref]

        # Call the function with fully qualified name
        result = find_usages("root_dir", "module.other_func")

        # Verify results
        assert len(result) == 1
        assert result[0] == UsageRecord(
            path="other.py", line=5, column=4, fqn="module.other_func"
        )

    @patch("os.path.isfile")
    @patch("builtins.open")
    def test_find_usages_deduplication(
        self,
        mock_open,
        mock_isfile,
        mock_index_data,
        mock_jedi_script,
        mock_jedi_project,
    ):
        # Setup mocks
        mock_isfile.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
            mock_index_data
        )

        # Setup mock references with duplicate location
        ref1 = MagicMock()
        ref1.module_path = "test.py"
        ref1.line = 10
        ref1.column = 6

        ref2 = MagicMock()  # Duplicate of ref1
        ref2.module_path = "test.py"
        ref2.line = 10
        ref2.column = 6

        mock_jedi_script.get_references.return_value = [ref1, ref2]

        # Call the function
        result = find_usages("root_dir", "TestClass")

        # Verify results - duplicates should be removed
        assert len(result) == 1
        assert result[0] == UsageRecord(
            path="test.py", line=10, column=6, fqn="module.TestClass"
        )

    @patch("os.path.isfile")
    @patch("builtins.open")
    @patch("jedi.Script")
    def test_find_usages_jedi_exception(
        self, mock_jedi_script, mock_open, mock_isfile, mock_index_data
    ):
        # Setup mocks
        mock_isfile.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
            mock_index_data
        )

        # Make jedi.Script raise an exception
        mock_jedi_script.side_effect = Exception("Jedi error")

        # Call the function
        result = find_usages("root_dir", "TestClass")

        # Verify empty result due to exception
        assert result == []
