import pytest
from unittest.mock import patch, MagicMock, mock_open

from find_usages.indexer import (
    index_project,
    is_test_directory,
    is_test_file,
    is_python_file,
    get_module_path,
    parse_file,
    create_index_entry,
    write_index_to_file,
)
from find_usages.file_list import create_file_tree


@pytest.fixture
def mock_jedi_script():
    script_mock = MagicMock()
    with patch("jedi.Script", return_value=script_mock):
        yield script_mock


@pytest.fixture
def mock_jedi_project():
    with patch("jedi.Project") as mock:
        yield mock


class TestIndexerUtils:
    def test_is_test_directory(self):
        assert is_test_directory("tests") is True
        assert is_test_directory("test_dir") is True
        assert is_test_directory("unittests") is True
        assert is_test_directory("src") is False
        assert is_test_directory("utils") is False

    def test_is_test_file(self):
        assert is_test_file("test_module.py") is True
        assert is_test_file("module_test.py") is True
        assert is_test_file("utils.py") is False

    def test_is_python_file(self):
        assert is_python_file("module.py") is True
        assert is_python_file("script.PY") is False  # Case sensitive
        assert is_python_file("module.txt") is False

    @patch("os.path.relpath")
    def test_get_module_path(self, mock_relpath):
        # Setup mock
        mock_relpath.return_value = "package/module.py"

        # Call the function
        result = get_module_path("/root/package/module.py", "/root")

        # Verify result
        assert result == "package.module"
        mock_relpath.assert_called_once_with("/root/package/module.py", "/root")


class TestParsing:
    def test_parse_file(self, mock_jedi_script, mock_jedi_project):
        # Setup mock
        mock_names = [MagicMock(), MagicMock()]
        mock_jedi_script.get_names.return_value = mock_names

        # Call the function
        result = parse_file("test.py", mock_jedi_project)

        # Verify result
        assert result == mock_names
        mock_jedi_script.get_names.assert_called_once_with(
            all_scopes=True, definitions=True
        )

    def test_parse_file_exception(self, mock_jedi_project):
        # Setup mock to raise exception
        with patch("jedi.Script", side_effect=Exception("Parse error")):
            # Call the function
            result = parse_file("test.py", mock_jedi_project)

            # Verify result is None on error
            assert result is None

    def test_create_index_entry_valid(self):
        # Create mock name object
        name = MagicMock()
        name.name = "TestClass"
        name.type = "class"
        name.line = 10
        name.column = 6
        name.get_definition_end_position.return_value = (20, 0)  # (line, column)

        # Call the function
        result = create_index_entry(name, "module", "test.py")

        # Verify result
        assert result == {
            "name": "TestClass",
            "fqn": "module.TestClass",
            "module": "module",
            "file": "test.py",
            "line": 10,
            "end_line": 20,
            "column": 6,
            "type": "class",
        }

    def test_create_index_entry_invalid_type(self):
        # Create mock name object with invalid type
        name = MagicMock()
        name.type = "keyword"  # Not in valid_types

        # Call the function
        result = create_index_entry(name, "module", "test.py")

        # Verify result is None for invalid type
        assert result is None

    def test_create_index_entry_no_end_position(self):
        # Create mock name object with no end position
        name = MagicMock()
        name.name = "variable"
        name.type = "param"
        name.line = 10
        name.column = 6
        name.get_definition_end_position.return_value = None

        # Call the function
        result = create_index_entry(name, "module", "test.py")

        # Verify result uses line as end_line
        assert result["end_line"] == 10


class TestIndexWriting:
    @patch("builtins.open", new_callable=mock_open)
    def test_write_index_to_file(self, mock_file):
        # Create test index data
        index_data = [
            {"name": "TestClass", "fqn": "module.TestClass", "file": "test.py"},
            {"name": "test_func", "fqn": "module.test_func", "file": "test.py"},
        ]

        # Call the function
        write_index_to_file(index_data, "index.json")

        # Verify file was opened correctly
        mock_file.assert_called_once_with("index.json", "w", encoding="utf-8")

        # Verify json.dump was called with the data
        file_handle = mock_file()
        file_handle.write.assert_called()


@patch("find_usages.indexer.write_index_to_file")
@patch("find_usages.indexer.parse_file")
@patch("find_usages.indexer.create_index_entry")
@patch("os.walk")
@patch("jedi.Project")
class TestIndexProject:
    def test_index_project(
        self, mock_project, mock_walk, mock_create_entry, mock_parse, mock_write
    ):
        # Setup mocks
        project_instance = MagicMock()
        mock_project.return_value = project_instance

        # Mock file structure
        mock_walk.return_value = [
            ("/root", ["src", "tests"], []),
            ("/root/src", [], ["module.py", "other.py", "README.txt"]),
            ("/root/tests", [], ["test_module.py"]),  # Should be ignored
        ]

        # Mock parsing
        name1 = MagicMock()
        name2 = MagicMock()
        mock_parse.return_value = [name1, name2]

        # Mock entry creation
        entry1 = {"name": "Class1", "fqn": "src.module.Class1"}
        entry2 = {"name": "func1", "fqn": "src.module.func1"}
        # Need to provide enough return values for all calls (2 names × 2 files)
        # Only two entries should be added to the index, so make the other two None
        mock_create_entry.side_effect = [entry1, entry2, None, None]

        # Call the function
        index_project("/root")

        # Verify test directories were filtered out
        assert any(
            "/root/tests" not in args[0] for args, _ in mock_parse.call_args_list
        )

        # Verify only Python files were parsed
        assert mock_parse.call_count == 2  # module.py and other.py

        # Verify index was written
        mock_write.assert_called_once()
        # Check the data that was written
        args, _ = mock_write.call_args
        assert args[0] == [entry1, entry2]


@patch("os.walk")
class TestCreateFileTree:
    def test_create_file_tree(self, mock_walk):
        # Setup mock directory structure
        mock_walk.return_value = [
            (".", [".git", "src", "tests", "docs"], ["README.md", "setup.py"]),
            ("./src", ["utils"], ["main.py", "helper.py"]),
            (
                "./src/utils",
                [],
                ["common.py", "data.bin"],
            ),  # data.bin should be ignored
            ("./docs", [], ["index.html", "test_main.txt"]),
        ]

        # Call the function
        result = create_file_tree()

        # Verify result
        assert "README.md" in result
        assert "utils" in result
        assert "data.bin" not in result
        assert "test_main.txt" in result

        # Verify hidden and test directories were skipped
        assert ".git" not in result

    def test_create_file_tree_with_depth(self, mock_walk):
        # Setup mock directory structure with multiple depth levels
        mock_walk.return_value = [
            (".", ["level1"], ["root.py"]),
            ("./level1", ["level2"], ["level1.py"]),
            ("./level1/level2", ["level3"], ["level2.py"]),
            ("./level1/level2/level3", ["level4"], ["level3.py"]),
            ("./level1/level2/level3/level4", [], ["level4.py"]),
        ]

        # Test with depth=1 (only root and level1)
        result_depth1 = create_file_tree(depth=1)

        # Verify level1 is included but level2 is not
        assert "level1" in result_depth1
        assert "level1.py" in result_depth1
        assert "level2" not in result_depth1
        assert "level2.py" not in result_depth1

        # Test with depth=2 (root, level1, and level2)
        result_depth2 = create_file_tree(depth=2)

        # Verify level2 is included but level3 is not
        assert "level1" in result_depth2
        assert "level2" in result_depth2
        assert "level2.py" in result_depth2
        assert "level3" not in result_depth2
        assert "level3.py" not in result_depth2

        # Test with depth=0 (only root)
        result_depth0 = create_file_tree(depth=0)

        # Verify only root level is included
        assert "root.py" in result_depth0
        assert "level1" not in result_depth0
        assert "level1.py" not in result_depth0
